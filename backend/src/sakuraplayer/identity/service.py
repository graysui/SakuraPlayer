from __future__ import annotations

import hashlib
import hmac
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sakuraplayer.identity.domain import (
    AccessClaims,
    AuthenticationError,
    BootstrapAlreadyCompleted,
    BootstrapTokenInvalid,
    ClientCleanupSignal,
    CurrentAdmin,
    IdentityValidationError,
    InvalidCredentials,
    RefreshClaims,
    RefreshTokenInvalid,
    RefreshTokenReused,
    SessionRevoked,
    TokenPair,
)
from sakuraplayer.identity.models import AdminUser, RefreshSession


class PasswordManager:
    def __init__(self) -> None:
        self._hasher = PasswordHasher(type=Type.ID)

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError):
            return False


class TokenManager:
    access_lifetime = timedelta(minutes=15)

    def __init__(
        self,
        signing_key: bytes,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._signing_key = signing_key
        self._now = now or (lambda: datetime.now(timezone.utc))

    def issue_access(
        self,
        *,
        admin_id: uuid.UUID,
        session_id: uuid.UUID,
        session_epoch: int,
    ) -> tuple[str, datetime]:
        issued_at = self._now().replace(microsecond=0)
        expires_at = issued_at + self.access_lifetime
        token = jwt.encode(
            {
                "sub": str(admin_id),
                "sid": str(session_id),
                "epoch": session_epoch,
                "typ": "access",
                "iat": issued_at,
                "exp": expires_at,
                "jti": str(uuid.uuid4()),
            },
            self._signing_key,
            algorithm="HS256",
        )
        return token, expires_at

    def decode_access(self, token: str) -> AccessClaims:
        try:
            payload, issued_at, expires_at = self._decode(
                token,
                required=["sub", "sid", "epoch", "typ", "iat", "exp", "jti"],
            )
            epoch = payload["epoch"]
            if (
                payload["typ"] != "access"
                or not isinstance(epoch, int)
                or isinstance(epoch, bool)
                or epoch < 0
                or expires_at - issued_at != self.access_lifetime
            ):
                raise ValueError
            return AccessClaims(
                admin_id=self._uuid_claim(payload, "sub"),
                session_id=self._uuid_claim(payload, "sid"),
                session_epoch=epoch,
                expires_at=expires_at,
            )
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError, OverflowError):
            raise AuthenticationError from None

    def issue_refresh(
        self,
        *,
        admin_id: uuid.UUID,
        session_id: uuid.UUID,
        expires_at: datetime,
    ) -> tuple[str, datetime]:
        issued_at = self._now().replace(microsecond=0)
        expires_at = expires_at.replace(microsecond=0)
        token = jwt.encode(
            {
                "sub": str(admin_id),
                "sid": str(session_id),
                "typ": "refresh",
                "iat": issued_at,
                "exp": expires_at,
                "jti": str(uuid.uuid4()),
            },
            self._signing_key,
            algorithm="HS256",
        )
        return token, expires_at

    def decode_refresh(self, token: str) -> RefreshClaims:
        try:
            payload, issued_at, expires_at = self._decode(
                token,
                required=["sub", "sid", "typ", "iat", "exp", "jti"],
            )
            if payload["typ"] != "refresh":
                raise ValueError
            return RefreshClaims(
                admin_id=self._uuid_claim(payload, "sub"),
                session_id=self._uuid_claim(payload, "sid"),
                issued_at=issued_at,
                expires_at=expires_at,
            )
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError, OverflowError):
            raise AuthenticationError from None

    def _decode(
        self,
        token: str,
        *,
        required: list[str],
    ) -> tuple[dict[str, object], datetime, datetime]:
        payload = jwt.decode(
            token,
            self._signing_key,
            algorithms=["HS256"],
            options={
                "verify_exp": False,
                "verify_iat": False,
                "require": required,
            },
        )
        issued_raw = payload["iat"]
        expires_raw = payload["exp"]
        if (
            not isinstance(issued_raw, int)
            or isinstance(issued_raw, bool)
            or not isinstance(expires_raw, int)
            or isinstance(expires_raw, bool)
        ):
            raise ValueError
        issued_at = datetime.fromtimestamp(issued_raw, tz=timezone.utc)
        expires_at = datetime.fromtimestamp(expires_raw, tz=timezone.utc)
        now = self._now()
        if issued_at > now or expires_at <= now or expires_at <= issued_at:
            raise ValueError
        self._uuid_claim(payload, "jti")
        return payload, issued_at, expires_at

    @staticmethod
    def _uuid_claim(payload: dict[str, object], name: str) -> uuid.UUID:
        value = payload[name]
        if not isinstance(value, str):
            raise ValueError
        return uuid.UUID(value)


class AuthService:
    refresh_lifetime = timedelta(days=30)
    _bootstrap_lock_key = 0x53414B555241

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        token_key: bytes,
        bootstrap_token: bytes,
        now: Callable[[], datetime] | None = None,
        secret_compare: Callable[[bytes, bytes], bool] = hmac.compare_digest,
    ) -> None:
        self._session_factory = session_factory
        self._passwords = PasswordManager()
        self._dummy_password_hash = self._passwords.hash("not-a-real-admin-password")
        self._tokens = TokenManager(token_key, now=now)
        self._bootstrap_digest = self._digest_bootstrap(bootstrap_token)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._secret_compare = secret_compare

    def bootstrap(
        self,
        *,
        username: str | None,
        password: str | None,
        client_instance_id: uuid.UUID | None,
        provided_bootstrap_token: str | None,
    ) -> TokenPair:
        with self._session_factory() as session:
            self._lock_bootstrap(session)
            if session.scalar(select(AdminUser.id).limit(1)) is not None:
                raise BootstrapAlreadyCompleted
            self._require_bootstrap_token(provided_bootstrap_token)
            if (
                username is None
                or password is None
                or client_instance_id is None
                or not 1 <= len(username) <= 64
                or not 12 <= len(password) <= 256
            ):
                raise IdentityValidationError

            now = self._now()
            admin = AdminUser(
                id=uuid.uuid4(),
                username=username,
                password_hash=self._passwords.hash(password),
                session_epoch=0,
                created_at=now,
                updated_at=now,
            )
            session.add(admin)
            pair = self._create_session(
                session,
                admin=admin,
                client_instance_id=client_instance_id,
                now=now,
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise BootstrapAlreadyCompleted from None
            return pair

    def authorize_bootstrap_token(
        self,
        provided_bootstrap_token: str | None,
    ) -> None:
        with self._session_factory() as session:
            self._lock_bootstrap(session)
            if session.scalar(select(AdminUser.id).limit(1)) is not None:
                raise BootstrapAlreadyCompleted
            self._require_bootstrap_token(provided_bootstrap_token)

    def is_initialized(self) -> bool:
        with self._session_factory() as session:
            return session.scalar(select(AdminUser.id).limit(1)) is not None

    def login(
        self,
        *,
        username: str,
        password: str,
        client_instance_id: uuid.UUID,
    ) -> TokenPair:
        with self._session_factory() as session:
            admin = session.scalar(
                select(AdminUser).where(AdminUser.username == username)
            )
            password_hash = (
                admin.password_hash if admin is not None else self._dummy_password_hash
            )
            if not self._passwords.verify(password_hash, password) or admin is None:
                raise InvalidCredentials

            now = self._now()
            self._lock_client_session(session, admin.id, client_instance_id)
            active_sessions = session.scalars(
                select(RefreshSession)
                .where(
                    RefreshSession.admin_id == admin.id,
                    RefreshSession.client_instance_id == client_instance_id,
                    RefreshSession.revoked_at.is_(None),
                )
                .with_for_update()
            )
            for active_session in active_sessions:
                active_session.revoked_at = now
            pair = self._create_session(
                session,
                admin=admin,
                client_instance_id=client_instance_id,
                now=now,
            )
            session.commit()
            return pair

    def refresh(self, refresh_token: str) -> TokenPair:
        try:
            claims = self._tokens.decode_refresh(refresh_token)
        except AuthenticationError:
            raise RefreshTokenInvalid from None

        with self._session_factory() as session:
            refresh_session = session.scalar(
                select(RefreshSession)
                .where(RefreshSession.id == claims.session_id)
                .with_for_update()
            )
            if refresh_session is None or refresh_session.admin_id != claims.admin_id:
                raise RefreshTokenInvalid
            admin = session.get(AdminUser, claims.admin_id)
            now = self._now()
            if (
                admin is None
                or refresh_session.revoked_at is not None
                or self._as_utc(refresh_session.expires_at) <= now
                or self._as_utc(refresh_session.expires_at) != claims.expires_at
            ):
                raise RefreshTokenInvalid
            if not hmac.compare_digest(
                refresh_session.token_hash,
                self._hash_refresh(refresh_token),
            ):
                refresh_session.revoked_at = now
                session.commit()
                raise RefreshTokenReused

            rotated_token, refresh_expires_at = self._tokens.issue_refresh(
                admin_id=admin.id,
                session_id=refresh_session.id,
                expires_at=self._as_utc(refresh_session.expires_at),
            )
            refresh_session.token_hash = self._hash_refresh(rotated_token)
            refresh_session.last_used_at = now
            access_token, access_expires_at = self._tokens.issue_access(
                admin_id=admin.id,
                session_id=refresh_session.id,
                session_epoch=admin.session_epoch,
            )
            session.commit()
            return TokenPair(
                access_token=access_token,
                refresh_token=rotated_token,
                access_expires_at=access_expires_at,
                refresh_expires_at=refresh_expires_at,
            )

    def authenticate_access(self, access_token: str) -> CurrentAdmin:
        claims = self._tokens.decode_access(access_token)
        with self._session_factory() as session:
            refresh_session = session.get(RefreshSession, claims.session_id)
            admin = session.get(AdminUser, claims.admin_id)
            if (
                refresh_session is None
                or admin is None
                or refresh_session.admin_id != admin.id
                or refresh_session.revoked_at is not None
            ):
                raise SessionRevoked
            if claims.session_epoch != admin.session_epoch:
                raise AuthenticationError
            return CurrentAdmin(
                admin_id=admin.id,
                username=admin.username,
                session_id=refresh_session.id,
                client_instance_id=refresh_session.client_instance_id,
                session_epoch=admin.session_epoch,
            )

    def logout(self, access_token: str) -> ClientCleanupSignal:
        claims = self._tokens.decode_access(access_token)
        with self._session_factory() as session:
            refresh_session = session.scalar(
                select(RefreshSession)
                .where(RefreshSession.id == claims.session_id)
                .with_for_update()
            )
            admin = session.scalar(
                select(AdminUser)
                .where(AdminUser.id == claims.admin_id)
                .with_for_update()
            )
            if (
                refresh_session is None
                or admin is None
                or refresh_session.admin_id != admin.id
                or refresh_session.revoked_at is not None
            ):
                raise SessionRevoked
            if claims.session_epoch != admin.session_epoch:
                raise AuthenticationError

            now = self._now()
            refresh_session.revoked_at = now
            admin.session_epoch += 1
            admin.updated_at = now
            client_instance_id = refresh_session.client_instance_id
            session.commit()
            return ClientCleanupSignal(client_instance_id=client_instance_id)

    def _lock_bootstrap(self, session: Session) -> None:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": self._bootstrap_lock_key},
            )

    def _require_bootstrap_token(self, provided_token: str | None) -> None:
        provided = (provided_token or "").encode("utf-8")
        provided_digest = self._digest_bootstrap(provided)
        if not self._secret_compare(self._bootstrap_digest, provided_digest):
            raise BootstrapTokenInvalid

    @staticmethod
    def _digest_bootstrap(value: bytes) -> bytes:
        return hashlib.sha256(b"sakuraplayer.bootstrap.v1\0" + value).digest()

    def _lock_client_session(
        self,
        session: Session,
        admin_id: uuid.UUID,
        client_instance_id: uuid.UUID,
    ) -> None:
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            return
        material = admin_id.bytes + client_instance_id.bytes
        lock_key = int.from_bytes(
            hashlib.sha256(material).digest()[:8],
            byteorder="big",
            signed=True,
        )
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def _create_session(
        self,
        session: Session,
        *,
        admin: AdminUser,
        client_instance_id: uuid.UUID,
        now: datetime,
    ) -> TokenPair:
        session_id = uuid.uuid4()
        refresh_expires_at = (now + self.refresh_lifetime).replace(microsecond=0)
        refresh_token, _ = self._tokens.issue_refresh(
            admin_id=admin.id,
            session_id=session_id,
            expires_at=refresh_expires_at,
        )
        session.add(
            RefreshSession(
                id=session_id,
                admin=admin,
                token_hash=self._hash_refresh(refresh_token),
                client_instance_id=client_instance_id,
                expires_at=refresh_expires_at,
            )
        )
        access_token, access_expires_at = self._tokens.issue_access(
            admin_id=admin.id,
            session_id=session_id,
            session_epoch=admin.session_epoch,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
        )

    @staticmethod
    def _hash_refresh(refresh_token: str) -> bytes:
        return hashlib.sha256(refresh_token.encode("ascii")).digest()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
