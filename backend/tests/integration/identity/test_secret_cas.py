from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import EncryptedSetting
from sakuraplayer.identity.secrets import (
    ConcurrentSettingUpdate,
    EncryptedSettingRepository,
)
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task003_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()

    test_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
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
def repository(database_url: str) -> tuple[EncryptedSettingRepository, object]:
    upgrade_database(database_url, ALEMBIC_INI)
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"k" * 32},
        )
    )
    repo = EncryptedSettingRepository(
        factory,
        cipher,
        now=lambda: datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc),
    )
    try:
        yield repo, factory
    finally:
        engine.dispose()


def test_secret_is_encrypted_and_status_never_returns_recoverable_data(
    repository: tuple[EncryptedSettingRepository, object],
) -> None:
    repo, factory = repository
    plaintext = b"UID=private-cookie"

    created = repo.create_secret("cloud115.cookie", plaintext)
    loaded = repo.get_secret("cloud115.cookie")
    status = repo.get_status("cloud115.cookie")

    assert created.version == 1
    assert loaded is not None and loaded.value == plaintext
    assert status is not None
    assert status.configured is True
    assert status.version == 1
    assert not hasattr(status, "value")
    with factory() as session:
        stored = session.scalar(
            select(EncryptedSetting).where(EncryptedSetting.key == "cloud115.cookie")
        )
        assert stored is not None
        assert stored.key_id == "test-v1"
        assert len(stored.nonce) == 12
        assert plaintext not in stored.ciphertext


def test_two_concurrent_cas_writes_allow_only_one_latest_version(
    repository: tuple[EncryptedSettingRepository, object],
) -> None:
    repo, _ = repository
    repo.create_secret("cloud115.cookie", b"initial-cookie")
    barrier = Barrier(2)

    def update(value: bytes) -> tuple[str, bytes]:
        barrier.wait()
        try:
            saved = repo.compare_and_set_secret(
                "cloud115.cookie",
                expected_version=1,
                value=value,
            )
            return "saved", saved.value
        except ConcurrentSettingUpdate:
            return "stale", value

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, [b"new-cookie-a", b"new-cookie-b"]))

    assert sorted(status for status, _ in results) == ["saved", "stale"]
    winner = next(value for status, value in results if status == "saved")
    loaded = repo.get_secret("cloud115.cookie")
    assert loaded is not None
    assert loaded.version == 2
    assert loaded.value == winner

    with pytest.raises(ConcurrentSettingUpdate) as error:
        repo.compare_and_set_secret(
            "cloud115.cookie",
            expected_version=1,
            value=b"old-request-cookie",
        )
    assert error.value.code == "setting_version_conflict"
    assert repo.get_secret("cloud115.cookie").value == winner


def test_two_concurrent_initial_writes_allow_only_one_creation(
    repository: tuple[EncryptedSettingRepository, object],
) -> None:
    repo, _ = repository
    barrier = Barrier(2)

    def create(value: bytes) -> tuple[str, bytes]:
        barrier.wait()
        try:
            saved = repo.create_or_compare_and_set_secret(
                "ai.api_key",
                expected_version=0,
                value=value,
            )
            return "saved", saved.value
        except ConcurrentSettingUpdate:
            return "stale", value

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, [b"private-key-a", b"private-key-b"]))

    assert sorted(status for status, _ in results) == ["saved", "stale"]
    winner = next(value for status, value in results if status == "saved")
    loaded = repo.get_secret("ai.api_key")
    assert loaded is not None
    assert loaded.version == 1
    assert loaded.value == winner
