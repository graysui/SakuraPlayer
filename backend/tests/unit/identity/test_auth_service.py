from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.identity.models import AdminUser, Base, RefreshSession
from sakuraplayer.identity.service import (
    AuthenticationError,
    AuthService,
    BootstrapAlreadyCompleted,
    BootstrapTokenInvalid,
    IdentityValidationError,
    InvalidCredentials,
    PasswordManager,
    RefreshTokenInvalid,
    RefreshTokenReused,
    SessionRevoked,
    TokenManager,
)


def test_password_is_stored_as_argon2id_hash_and_wrong_password_is_rejected() -> None:
    passwords = PasswordManager()

    password_hash = passwords.hash("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert "correct horse battery staple" not in password_hash
    assert passwords.verify(password_hash, "correct horse battery staple") is True
    assert passwords.verify(password_hash, "wrong password") is False
    assert passwords.verify("not-an-argon2-hash", "wrong password") is False


def test_unicode_password_is_not_normalized_or_stored_verbatim() -> None:
    passwords = PasswordManager()
    password = "安全密码Cafe\u0301-123"

    password_hash = passwords.hash(password)

    assert password not in password_hash
    assert passwords.verify(password_hash, password) is True
    assert passwords.verify(password_hash, "安全密码Café-123") is False


def test_access_token_is_short_lived_and_bound_to_session_epoch() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    admin_id = uuid.uuid4()
    session_id = uuid.uuid4()
    tokens = TokenManager(b"t" * 32, now=lambda: now)

    access_token, expires_at = tokens.issue_access(
        admin_id=admin_id,
        session_id=session_id,
        session_epoch=7,
    )
    claims = tokens.decode_access(access_token)

    assert expires_at == now + timedelta(minutes=15)
    assert claims.admin_id == admin_id
    assert claims.session_id == session_id
    assert claims.session_epoch == 7


def test_expired_access_token_is_rejected_with_stable_error() -> None:
    issued_at = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    current_time = [issued_at]
    tokens = TokenManager(b"t" * 32, now=lambda: current_time[0])
    access_token, _ = tokens.issue_access(
        admin_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        session_epoch=0,
    )
    current_time[0] = issued_at + timedelta(minutes=16)

    with pytest.raises(AuthenticationError) as error:
        tokens.decode_access(access_token)

    assert error.value.code == "authentication_required"


def test_refresh_token_is_signed_typed_and_has_absolute_expiry() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    tokens = TokenManager(b"t" * 32, now=lambda: now)
    admin_id = uuid.uuid4()
    session_id = uuid.uuid4()

    refresh_token, expires_at = tokens.issue_refresh(
        admin_id=admin_id,
        session_id=session_id,
        expires_at=now + timedelta(days=30),
    )
    claims = tokens.decode_refresh(refresh_token)

    assert expires_at == now + timedelta(days=30)
    assert claims.admin_id == admin_id
    assert claims.session_id == session_id
    with pytest.raises(AuthenticationError):
        tokens.decode_access(refresh_token)

    access_token, _ = tokens.issue_access(
        admin_id=admin_id,
        session_id=session_id,
        session_epoch=0,
    )
    with pytest.raises(AuthenticationError):
        tokens.decode_refresh(access_token)


def test_access_token_rejects_bad_signature_and_none_algorithm() -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    tokens = TokenManager(b"t" * 32, now=lambda: now)
    access_token, _ = tokens.issue_access(
        admin_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        session_epoch=0,
    )
    header, payload, _ = access_token.split(".")
    bad_signature = f"{header}.{payload}.{'A' * 43}"
    unsigned = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "sid": str(uuid.uuid4()),
            "epoch": 0,
            "typ": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "jti": str(uuid.uuid4()),
        },
        key="",
        algorithm="none",
    )

    with pytest.raises(AuthenticationError):
        tokens.decode_access(bad_signature)
    with pytest.raises(AuthenticationError):
        tokens.decode_access(unsigned)


@pytest.mark.parametrize(
    "payload_update,algorithm",
    [
        ({"typ": "refresh"}, "HS256"),
        (
            {"iat": int(datetime(2026, 7, 24, 8, 1, tzinfo=timezone.utc).timestamp())},
            "HS256",
        ),
        ({"jti": None}, "HS256"),
        ({"jti": 123}, "HS256"),
        ({"sid": 123}, "HS256"),
        ({"sub": {}}, "HS256"),
        ({"epoch": -1}, "HS256"),
        ({"iat": "not-a-time"}, "HS256"),
        ({"exp": True}, "HS256"),
        (
            {
                "iat": int(
                    datetime(2025, 7, 24, 8, 0, tzinfo=timezone.utc).timestamp()
                ),
                "exp": int(
                    datetime(2026, 7, 24, 8, 1, tzinfo=timezone.utc).timestamp()
                ),
            },
            "HS256",
        ),
        ({}, "HS384"),
    ],
)
def test_access_token_rejects_wrong_type_time_claims_and_algorithm(
    payload_update: dict[str, object],
    algorithm: str,
) -> None:
    now = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    tokens = TokenManager(b"t" * 32, now=lambda: now)
    payload: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "epoch": 0,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    payload.update(payload_update)
    if payload.get("jti") is None:
        payload.pop("jti")
    token = jwt.encode(payload, b"t" * 32, algorithm=algorithm)

    with pytest.raises(AuthenticationError):
        tokens.decode_access(token)


@pytest.fixture
def auth_store() -> tuple[sessionmaker[Session], datetime]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    return factory, now


def build_auth_service(
    auth_store: tuple[sessionmaker[Session], datetime],
    **overrides: object,
) -> AuthService:
    factory, now = auth_store
    bootstrap_token = overrides.pop(
        "bootstrap_token",
        b"bootstrap-token-with-at-least-32-bytes",
    )
    return AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=bootstrap_token,
        now=lambda: now,
        **overrides,
    )


@pytest.mark.parametrize(
    "provided",
    [
        None,
        "wrong-bootstrap-token",
        "x",
        "x" * 4096,
        "错误初始化口令",
    ],
)
def test_bootstrap_rejects_missing_or_wrong_token(
    auth_store: tuple[sessionmaker[Session], datetime],
    provided: str | None,
) -> None:
    service = build_auth_service(auth_store)

    with pytest.raises(BootstrapTokenInvalid) as error:
        service.bootstrap(
            username="admin",
            password="correct horse battery staple",
            client_instance_id=uuid.uuid4(),
            provided_bootstrap_token=provided,
        )

    assert error.value.code == "bootstrap_token_invalid"
    with auth_store[0]() as session:
        assert session.scalar(select(AdminUser)) is None


def test_bootstrap_creates_one_admin_and_stores_only_hashes(
    auth_store: tuple[sessionmaker[Session], datetime],
) -> None:
    service = build_auth_service(auth_store)
    client_instance_id = uuid.uuid4()

    pair = service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=client_instance_id,
        provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
    )

    assert pair.token_type == "Bearer"
    assert pair.access_token
    assert pair.refresh_token
    with auth_store[0]() as session:
        admin = session.scalar(select(AdminUser))
        refresh = session.scalar(select(RefreshSession))
        assert admin is not None
        assert admin.username == "admin"
        assert admin.password_hash.startswith("$argon2id$")
        assert "correct horse battery staple" not in admin.password_hash
        assert refresh is not None
        assert refresh.client_instance_id == client_instance_id
        assert (
            refresh.token_hash
            == hashlib.sha256(pair.refresh_token.encode("ascii")).digest()
        )
        assert not hasattr(admin, "bootstrap_token")


def test_existing_admin_is_rejected_without_comparing_bootstrap_secret(
    auth_store: tuple[sessionmaker[Session], datetime],
) -> None:
    service = build_auth_service(auth_store)
    service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=uuid.uuid4(),
        provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
    )

    def forbidden_compare(left: bytes, right: bytes) -> bool:
        del left, right
        raise AssertionError("bootstrap secret must not be compared")

    service_after_rotation = build_auth_service(
        auth_store,
        bootstrap_token=b"rotated-bootstrap-token-at-least-32-bytes",
        secret_compare=forbidden_compare,
    )

    with pytest.raises(BootstrapAlreadyCompleted) as error:
        service_after_rotation.bootstrap(
            username="replacement",
            password="different password value",
            client_instance_id=uuid.uuid4(),
            provided_bootstrap_token=None,
        )

    assert error.value.code == "bootstrap_already_completed"


@pytest.mark.parametrize("password", ["x" * 11, "x" * 257])
def test_bootstrap_rejects_password_outside_frozen_length_boundary(
    auth_store: tuple[sessionmaker[Session], datetime],
    password: str,
) -> None:
    service = build_auth_service(auth_store)

    with pytest.raises(IdentityValidationError) as error:
        service.bootstrap(
            username="admin",
            password=password,
            client_instance_id=uuid.uuid4(),
            provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
        )

    assert error.value.code == "validation_failed"


@pytest.mark.parametrize("password", ["x" * 12, "x" * 256])
def test_bootstrap_accepts_password_at_frozen_length_boundary(
    auth_store: tuple[sessionmaker[Session], datetime],
    password: str,
) -> None:
    service = build_auth_service(auth_store)

    pair = service.bootstrap(
        username="admin",
        password=password,
        client_instance_id=uuid.uuid4(),
        provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
    )

    assert pair.access_token


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("missing", "correct horse battery staple"),
        ("admin", "wrong password value"),
    ],
)
def test_login_rejects_wrong_credentials_with_one_stable_error(
    auth_store: tuple[sessionmaker[Session], datetime],
    username: str,
    password: str,
) -> None:
    service = build_auth_service(auth_store)
    service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=uuid.uuid4(),
        provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
    )

    with pytest.raises(InvalidCredentials) as error:
        service.login(
            username=username,
            password=password,
            client_instance_id=uuid.uuid4(),
        )

    assert error.value.code == "invalid_credentials"


def test_login_replaces_active_session_for_same_client_instance(
    auth_store: tuple[sessionmaker[Session], datetime],
) -> None:
    service = build_auth_service(auth_store)
    client_instance_id = uuid.uuid4()
    old_pair = service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=client_instance_id,
        provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
    )

    new_pair = service.login(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=client_instance_id,
    )

    assert new_pair.refresh_token != old_pair.refresh_token
    with pytest.raises(SessionRevoked):
        service.authenticate_access(old_pair.access_token)
    with pytest.raises(RefreshTokenInvalid):
        service.refresh(old_pair.refresh_token)
    current = service.authenticate_access(new_pair.access_token)
    assert current.client_instance_id == client_instance_id


def test_refresh_rotates_token_without_extending_absolute_expiry(
    auth_store: tuple[sessionmaker[Session], datetime],
) -> None:
    service = build_auth_service(auth_store)
    pair = service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=uuid.uuid4(),
        provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
    )

    rotated = service.refresh(pair.refresh_token)

    assert rotated.refresh_token != pair.refresh_token
    assert rotated.refresh_expires_at == pair.refresh_expires_at
    assert service.authenticate_access(rotated.access_token).username == "admin"


def test_refresh_expiry_does_not_shorten_already_issued_access_token(
    auth_store: tuple[sessionmaker[Session], datetime],
) -> None:
    factory, initial_time = auth_store
    current_time = [initial_time]
    service = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=b"bootstrap-token-with-at-least-32-bytes",
        now=lambda: current_time[0],
    )
    pair = service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=uuid.uuid4(),
        provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
    )
    current_time[0] = pair.refresh_expires_at - timedelta(minutes=1)
    rotated = service.refresh(pair.refresh_token)
    current_time[0] = pair.refresh_expires_at + timedelta(minutes=1)

    assert service.authenticate_access(rotated.access_token).username == "admin"
    with pytest.raises(RefreshTokenInvalid) as error:
        service.refresh(rotated.refresh_token)

    assert error.value.code == "refresh_token_invalid"


def test_refresh_replay_revokes_the_rotated_client_session(
    auth_store: tuple[sessionmaker[Session], datetime],
) -> None:
    service = build_auth_service(auth_store)
    pair = service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=uuid.uuid4(),
        provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
    )
    rotated = service.refresh(pair.refresh_token)

    with pytest.raises(RefreshTokenReused) as error:
        service.refresh(pair.refresh_token)

    assert error.value.code == "refresh_token_reused"
    with pytest.raises(RefreshTokenInvalid):
        service.refresh(rotated.refresh_token)
    with pytest.raises(SessionRevoked):
        service.authenticate_access(rotated.access_token)


def test_logout_revokes_current_client_and_other_client_can_refresh_new_epoch(
    auth_store: tuple[sessionmaker[Session], datetime],
) -> None:
    service = build_auth_service(auth_store)
    first_client = uuid.uuid4()
    second_client = uuid.uuid4()
    first_pair = service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=first_client,
        provided_bootstrap_token="bootstrap-token-with-at-least-32-bytes",
    )
    second_pair = service.login(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=second_client,
    )

    cleanup = service.logout(first_pair.access_token)

    assert cleanup.client_instance_id == first_client
    assert cleanup.clear_tokens is True
    assert cleanup.clear_subtitle_cache is True
    with pytest.raises(SessionRevoked):
        service.authenticate_access(first_pair.access_token)
    with pytest.raises(RefreshTokenInvalid):
        service.refresh(first_pair.refresh_token)
    with pytest.raises(AuthenticationError):
        service.authenticate_access(second_pair.access_token)

    recovered = service.refresh(second_pair.refresh_token)
    assert (
        service.authenticate_access(recovered.access_token).client_instance_id
        == second_client
    )
