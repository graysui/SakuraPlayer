from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.cleanup import CleanupProblem, CleanupQueue, CleanupWorker
from sakuraplayer.cloud_cache.models import (
    CacheCleanupAttempt,
    CacheJob,
    CacheJobMediaSelection,
    Cloud115Binding,
    RemoteMedia,
)
from sakuraplayer.cloud_cache.play_request import PlayRequestService
from sakuraplayer.cloud_cache.ports.cloud115 import DirectoryBreadcrumb, DirectoryInfo
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import AdminUser
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.playback.lease import PlaybackLeaseService
from sakuraplayer.playback.models import PlaybackSession
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import SourceSubmissionService
from sakuraplayer.shared.migration import upgrade_database
from tests.fakes.cloud115 import FakeCloud115

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def context():
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task107_cleanup_{uuid.uuid4().hex}"
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
        cipher = SecretCipher(
            InMemorySecretKeyProvider(
                active_key_id="test-v1",
                keys={"test-v1": b"k" * 32},
            )
        )
        secrets = EncryptedSettingRepository(factory, cipher, now=lambda: NOW)
        version = secrets.create_secret(
            "cloud115.cookie", b"credential-fixture"
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
                    cache_root_cid="root-cid",
                    status="active",
                    credential_version=version,
                    last_verified_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            session.add(
                AdminUser(
                    id=uuid.uuid4(),
                    singleton_key=True,
                    username="admin",
                    password_hash="$argon2id$fixture",
                    session_epoch=0,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        SourceImporter(factory, cipher=cipher, now=lambda: NOW).import_batch(
            "fixture.zip", (_row(),)
        )
        play = PlayRequestService(
            factory,
            SourceSubmissionService(factory, cipher=cipher),
            now=lambda: NOW,
        )
        yield factory, play
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


def test_postgres_lease_blocks_then_safe_cleanup_releases_capacity(context) -> None:
    factory, play = context
    with factory() as session:
        source = session.execute(
            text("SELECT movie_id, id FROM resource_source LIMIT 1")
        ).one()
    result = play.create(
        movie_id=source.movie_id,
        source_id=source.id,
        idempotency_key="task107-cleanup-request",
    )
    job_id = result.job.id
    media_id = uuid.uuid4()
    task_dir_name: str
    with factory.begin() as session:
        job = session.get(CacheJob, job_id, with_for_update=True)
        assert job is not None
        job.status = "ready"
        job.capacity_class = "ready"
        job.task_dir_cid = "task-cid"
        job.remote_percent = 100
        job.ready_at = NOW - timedelta(days=2)
        job.last_accessed_at = NOW - timedelta(days=2)
        job.expires_at = NOW - timedelta(days=1)
        job.updated_at = NOW
        task_dir_name = job.task_dir_name
        session.add(
            RemoteMedia(
                id=media_id,
                cache_job_id=job.id,
                file_id="media-file",
                pickcode="media-pickcode",
                parent_cid="task-cid",
                name="IPX-001.mkv",
                size_bytes=300_000_000,
                duration_seconds=600,
                candidate_id=uuid.uuid4(),
                sequence_no=0,
                selection_score=100,
                selection_evidence=[],
                is_valid=True,
                created_at=NOW,
            )
        )
        session.flush()
        session.add(
            CacheJobMediaSelection(
                cache_job_id=job.id,
                sequence_no=0,
                media_id=media_id,
            )
        )
        admin_id = session.scalar(select(AdminUser.id))
        assert admin_id is not None
        playback_id = uuid.uuid4()
        session.add(
            PlaybackSession(
                id=playback_id,
                admin_id=admin_id,
                session_epoch=0,
                movie_id=job.movie_id,
                cache_job_id=job.id,
                media_id=media_id,
                mode="original",
                platform="windows",
                user_agent_hash="a" * 64,
                issued_at=NOW,
                expires_at=NOW + timedelta(hours=12),
                revoked_at=None,
            )
        )
    client_id = uuid.uuid4()
    leases = PlaybackLeaseService(factory, now=lambda: NOW)
    leases.acquire(
        playback_session_id=playback_id,
        client_instance_id=client_id,
    )
    queue = CleanupQueue(factory, now=lambda: NOW)
    with pytest.raises(CleanupProblem) as raised:
        queue.request(job_id)
    assert raised.value.code == "cache_active_lease"

    leases.end(playback_session_id=playback_id, client_instance_id=client_id)
    assert queue.request(job_id).status == "cleaning"
    fake = FakeCloud115(
        directory_infos=[_root(), _task(task_dir_name)],
        delete_results=[None],
    )

    @asynccontextmanager
    async def cloud_scope(_claim):
        yield fake

    assert (
        CleanupWorker(queue, cloud_scope).run_once(worker_id="cleanup-pg") == "worked"
    )
    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None and job.status == "cleaned"
        assert job.capacity_class == "released"
        assert session.scalar(select(func.count(RemoteMedia.id))) == 0
        attempt = session.scalar(
            select(CacheCleanupAttempt).where(
                CacheCleanupAttempt.cache_job_id == job_id
            )
        )
        assert attempt is not None and attempt.status == "succeeded"


def _root() -> DirectoryInfo:
    return DirectoryInfo(
        cid="root-cid",
        parent_cid="0",
        name="SakuraPlayer-Cache",
        path=(DirectoryBreadcrumb("0", "root"),),
    )


def _task(task_dir_name: str) -> DirectoryInfo:
    return DirectoryInfo(
        cid="task-cid",
        parent_cid="root-cid",
        name=task_dir_name,
        path=(DirectoryBreadcrumb("root-cid", "SakuraPlayer-Cache"),),
    )


def _row() -> dict[str, object]:
    return {
        "website": "sehuatang",
        "tid": 107,
        "magnet": "task107-source-fixture",
        "title": "IPX-001",
        "number": "IPX-001",
        "size": 1024,
        "publish_date": date(2026, 7, 20),
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/thread-task107.htm",
        "section": "亚洲有码",
        "category": None,
        "create_time": NOW,
        "update_time": NOW,
    }
