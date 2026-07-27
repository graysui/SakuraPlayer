from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.binding_service import BindingService
from sakuraplayer.cloud_cache.models import Cloud115Binding
from sakuraplayer.cloud_cache.ports.cloud115 import (
    CloudCredentialStatus,
    CredentialProbe,
    QrLoginResult,
    RemoteDirectory,
)
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import EncryptedSetting
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.shared.migration import upgrade_database
from tests.fakes.cloud115 import FakeCloud115

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task102_cas_{uuid.uuid4().hex}"
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


def _repository(database_url: str):
    upgrade_database(database_url, ALEMBIC_INI)
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    secrets = EncryptedSettingRepository(
        factory,
        SecretCipher(
            InMemorySecretKeyProvider(
                active_key_id="test-v1", keys={"test-v1": b"k" * 32}
            )
        ),
        now=lambda: NOW,
    )
    return engine, factory, secrets


@pytest.mark.asyncio
async def test_rebind_and_secret_version_commit_atomically(database_url: str) -> None:
    engine, factory, secrets = _repository(database_url)
    fakes = iter(
        [
            FakeCloud115(
                directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
            ),
            FakeCloud115(
                directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
            ),
        ]
    )

    @asynccontextmanager
    async def cloud_factory(_cookies: str | None):
        yield next(fakes)

    service = BindingService(factory, secrets, cloud_factory, now=lambda: NOW)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old-cookie"))
        await service.bind(QrLoginResult("account-1", "UID=new-cookie"))
        with factory() as session:
            binding = session.scalar(select(Cloud115Binding))
            setting = session.get(EncryptedSetting, "cloud115.cookie")
            assert binding is not None and setting is not None
            assert binding.credential_version == setting.version == 2
            assert b"old-cookie" not in setting.ciphertext
            assert b"new-cookie" not in setting.ciphertext
        assert secrets.get_secret("cloud115.cookie").value == b"UID=new-cookie"
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_old_probe_cas_loses_to_concurrent_rescan(database_url: str) -> None:
    engine, factory, secrets = _repository(database_url)
    started = asyncio.Event()
    release = asyncio.Event()

    class DelayedProbe(FakeCloud115):
        async def probe_credentials(self) -> CredentialProbe:
            started.set()
            await release.wait()
            return CredentialProbe(
                CloudCredentialStatus.UNAVAILABLE, "UID=stale-refresh"
            )

    fakes = iter(
        [
            FakeCloud115(
                directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
            ),
            DelayedProbe(),
            FakeCloud115(
                directories=[RemoteDirectory("root-1", "0", "SakuraPlayer-Cache")]
            ),
        ]
    )

    @asynccontextmanager
    async def cloud_factory(_cookies: str | None):
        yield next(fakes)

    service = BindingService(factory, secrets, cloud_factory, now=lambda: NOW)
    try:
        await service.bind(QrLoginResult("account-1", "UID=old-cookie"))
        probe = asyncio.create_task(service.probe())
        await started.wait()
        await service.bind(QrLoginResult("account-1", "UID=new-scan"))
        release.set()
        result = await probe
        assert result.status == "active"
        assert secrets.get_secret("cloud115.cookie").value == b"UID=new-scan"
    finally:
        engine.dispose()


def test_database_rejects_more_than_one_binding_row(database_url: str) -> None:
    engine, factory, secrets = _repository(database_url)
    secrets.create_secret("cloud115.cookie", b"UID=encrypted")
    try:
        with pytest.raises(IntegrityError):
            with factory.begin() as session:
                for account in ("one", "two"):
                    session.add(
                        Cloud115Binding(
                            id=uuid.uuid4(),
                            singleton_key=True,
                            account_key=account,
                            display_name=None,
                            cookie_setting_key="cloud115.cookie",
                            login_app="alipaymini",
                            cache_root_cid=f"root-{account}",
                            status="active",
                            credential_version=1,
                            last_verified_at=NOW,
                            created_at=NOW,
                            updated_at=NOW,
                        )
                    )
    finally:
        engine.dispose()
