from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.identity.domain import (
    BootstrapAlreadyCompleted,
    RefreshTokenReused,
    SessionRevoked,
    TokenPair,
)
from sakuraplayer.identity.models import AdminUser, RefreshSession
from sakuraplayer.identity.service import AuthService
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
BOOTSTRAP_TOKEN = "task002-bootstrap-token-at-least-32-bytes"


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task002_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()

    test_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        upgrade_database(test_url, ALEMBIC_INI)
        yield test_url
    finally:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin_engine.dispose()


@pytest.fixture
def auth_service(database_url: str) -> tuple[AuthService, sessionmaker[Session]]:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    service = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN.encode("ascii"),
        now=lambda: datetime.now(timezone.utc),
    )
    return service, factory


def test_concurrent_bootstrap_creates_exactly_one_admin_and_initial_session(
    auth_service: tuple[AuthService, sessionmaker[Session]],
) -> None:
    service, factory = auth_service
    barrier = threading.Barrier(2)

    def attempt() -> str:
        barrier.wait()
        try:
            service.bootstrap(
                username="admin",
                password="correct horse battery staple",
                client_instance_id=uuid.uuid4(),
                provided_bootstrap_token=BOOTSTRAP_TOKEN,
            )
        except BootstrapAlreadyCompleted:
            return "conflict"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))

    assert sorted(results) == ["conflict", "created"]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AdminUser)) == 1
        assert session.scalar(select(func.count()).select_from(RefreshSession)) == 1
        admin = session.scalar(select(AdminUser))
        refresh = session.scalar(select(RefreshSession))
        assert admin is not None and admin.password_hash.startswith("$argon2id$")
        assert refresh is not None and len(refresh.token_hash) == 32
        assert BOOTSTRAP_TOKEN not in admin.password_hash
        assert BOOTSTRAP_TOKEN.encode("ascii") != refresh.token_hash


def test_concurrent_refresh_has_one_success_and_replay_revokes_session(
    auth_service: tuple[AuthService, sessionmaker[Session]],
) -> None:
    service, factory = auth_service
    pair = service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=uuid.uuid4(),
        provided_bootstrap_token=BOOTSTRAP_TOKEN,
    )
    barrier = threading.Barrier(2)

    def attempt() -> str:
        barrier.wait()
        try:
            service.refresh(pair.refresh_token)
        except RefreshTokenReused:
            return "reused"
        return "rotated"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))

    assert sorted(results) == ["reused", "rotated"]
    with factory() as session:
        refresh = session.scalar(select(RefreshSession))
        assert refresh is not None
        assert refresh.revoked_at is not None


def test_concurrent_login_for_new_client_is_serialized_without_server_error(
    auth_service: tuple[AuthService, sessionmaker[Session]],
) -> None:
    service, factory = auth_service
    service.bootstrap(
        username="admin",
        password="correct horse battery staple",
        client_instance_id=uuid.uuid4(),
        provided_bootstrap_token=BOOTSTRAP_TOKEN,
    )
    client_instance_id = uuid.uuid4()
    select_barrier = threading.Barrier(2)
    engine = factory.kw["bind"]

    def align_empty_session_selects(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        if "FROM refresh_session" in statement and "revoked_at IS NULL" in statement:
            try:
                select_barrier.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass

    event.listen(engine, "after_cursor_execute", align_empty_session_selects)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            pairs = list(
                executor.map(
                    lambda _: service.login(
                        username="admin",
                        password="correct horse battery staple",
                        client_instance_id=client_instance_id,
                    ),
                    range(2),
                )
            )
    finally:
        event.remove(engine, "after_cursor_execute", align_empty_session_selects)

    assert all(isinstance(pair, TokenPair) for pair in pairs)
    with factory() as session:
        active_count = session.scalar(
            select(func.count())
            .select_from(RefreshSession)
            .where(RefreshSession.revoked_at.is_(None))
        )
        assert active_count == 2  # bootstrap client plus one concurrent-login client

    outcomes: list[str] = []
    for pair in pairs:
        try:
            service.authenticate_access(pair.access_token)
        except SessionRevoked:
            outcomes.append("revoked")
        else:
            outcomes.append("active")
    assert sorted(outcomes) == ["active", "revoked"]
