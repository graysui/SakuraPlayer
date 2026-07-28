from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.models import CacheJob, Cloud115Binding
from sakuraplayer.cloud_cache.play_request import PlayRequestService
from sakuraplayer.cloud_cache.ports.cloud115 import (
    DirectoryBreadcrumb,
    DirectoryInfo,
    RemoteFile,
)
from sakuraplayer.cloud_cache.source_rejection_client import SourceRejectionClient
from sakuraplayer.cloud_cache.worker.claim import CacheJobClaimQueue
from sakuraplayer.cloud_cache.worker.resolution import CacheMediaResolver
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import ResourceSource, SourceRejection
from sakuraplayer.resources.rejection import SourceRejectionService
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import SourceSubmissionService
from sakuraplayer.shared.migration import upgrade_database
from tests.fakes.cloud115 import FakeCloud115

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def context():
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task106_rejection_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()
    database_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    engine = None
    try:
        upgrade_database(database_url, ALEMBIC_INI)
        engine = create_engine(database_url, hide_parameters=True)
        factory = sessionmaker(engine, expire_on_commit=False)
        cipher = _cipher()
        secrets = EncryptedSettingRepository(factory, cipher, now=lambda: NOW)
        version = secrets.create_secret(
            "cloud115.cookie", b"synthetic-test-secret"
        ).version
        with factory.begin() as session:
            session.add(
                Cloud115Binding(
                    id=uuid.uuid4(),
                    singleton_key=True,
                    account_key="account-fixture",
                    display_name=None,
                    cookie_setting_key="cloud115.cookie",
                    login_app="alipaymini",
                    cache_root_cid="root",
                    status="active",
                    credential_version=version,
                    last_verified_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        importer = SourceImporter(factory, cipher=cipher, now=lambda: NOW)
        importer.import_batch("30D_202607280300.zip", (_row(),))
        source_port = SourceSubmissionService(factory, cipher=cipher)
        play = PlayRequestService(factory, source_port, now=lambda: NOW)
        yield factory, importer, source_port, play
    finally:
        if engine is not None:
            engine.dispose()
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


def test_blocked_file_rejects_source_and_both_import_modes_keep_it_rejected(
    context,
) -> None:
    factory, importer, source_port, play = context
    with factory() as session:
        movie_id, source_id = session.execute(
            select(ResourceSource.movie_id, ResourceSource.id)
        ).one()
    result = play.create(
        movie_id=movie_id,
        source_id=source_id,
        idempotency_key=f"task106-blocked-{source_id.hex}",
    )
    job_id = result.job.id
    with factory.begin() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        job.status = "resolving"
        job.task_dir_cid = "task"
        job.remote_percent = 100
        task_dir_name = job.task_dir_name

    fake = FakeCloud115(
        directory_infos=[_directory(task_dir_name)] * 2,
        file_batches=[(_blocked_file(),)],
    )
    rejection_client = SourceRejectionClient(
        source_port,
        SourceRejectionService(factory, now=lambda: NOW),
    )

    assert (
        _resolver(factory, rejection_client, fake).run_once(worker_id="resolver-pg")
        == "worked"
    )

    for asset_name in (
        "30D_202607280400.zip",
        "All_sehuatang_100_202607280500.zip",
    ):
        stats = importer.import_batch(asset_name, (_row(magnet_suffix=asset_name),))
        assert stats.skipped == 1

    with factory() as session:
        job = session.get(CacheJob, job_id)
        source = session.get(ResourceSource, source_id)
        rejection = session.scalar(select(SourceRejection))
        event = session.scalar(select(DomainEvent))
        assert session.scalar(select(func.count(SourceRejection.id))) == 1
        assert session.scalar(select(func.count(DomainEvent.event_id))) == 1

    assert job is not None
    assert (job.status, job.failure_code) == ("failed", "cloud115_source_blocked")
    assert source is not None and source.identification_status == "rejected"
    assert source.magnet_envelope is None
    assert rejection is not None
    assert (
        rejection.website,
        rejection.external_post_id,
        rejection.reason_code,
    ) == ("sehuatang", 106, "cloud115_source_blocked")
    assert event is not None
    assert event.payload == {
        "id": str(job_id),
        "status": "failed",
        "error_code": "cloud115_source_blocked",
        "rejected_source": True,
    }
    persisted = repr((job.failure_detail, event.payload, rejection.reason_code)).lower()
    assert "magnet:" not in persisted
    assert "upstream body" not in persisted


def _resolver(factory, rejection_client, fake):
    @asynccontextmanager
    async def cloud_scope(_claim):
        yield fake

    return CacheMediaResolver(
        CacheJobClaimQueue(factory, now=lambda: NOW),
        rejection_client,
        cloud_scope,
        now=lambda: NOW,
    )


def _directory(task_name: str) -> DirectoryInfo:
    return DirectoryInfo(
        cid="task",
        parent_cid="root",
        name=task_name,
        path=(DirectoryBreadcrumb("root", "SakuraPlayer-Cache"),),
    )


def _blocked_file() -> RemoteFile:
    return RemoteFile(
        file_id="blocked",
        parent_cid="task",
        name="IPX-106.mkv",
        size_bytes=2_000_000_000,
        pickcode="pick-blocked",
        sha1=None,
        is_directory=False,
        is_video=True,
        duration_seconds=7200,
        blocked=True,
    )


def _cipher() -> SecretCipher:
    return SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"k" * 32},
        )
    )


def _row(*, magnet_suffix: str = "initial") -> dict[str, object]:
    return {
        "tid": 106,
        "number": "IPX-106",
        "title": "Fixture",
        "publish_date": date(2026, 7, 28),
        "magnet": f"magnet:?xt=urn:btih:{magnet_suffix}",
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/thread-fixture.htm",
        "size": 1024,
        "section": "亚洲有码",
        "category": None,
        "website": "sehuatang",
        "create_time": NOW,
        "update_time": NOW,
    }
