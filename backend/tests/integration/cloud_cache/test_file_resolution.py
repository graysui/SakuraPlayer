from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.cancellation import CancellationService
from sakuraplayer.cloud_cache.media_selection import plan_media_selection
from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    Cloud115Binding,
    RemoteMedia,
    RemoteSubtitle,
)
from sakuraplayer.cloud_cache.play_request import PlayRequestService
from sakuraplayer.cloud_cache.ports.cloud115 import (
    DirectoryBreadcrumb,
    DirectoryInfo,
    RemoteFile,
)
from sakuraplayer.cloud_cache.source_rejection_client import SourceRejectionClient
from sakuraplayer.cloud_cache.worker.claim import (
    CacheJobClaimLost,
    CacheJobClaimQueue,
)
from sakuraplayer.cloud_cache.worker.resolution import CacheMediaResolver
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import ResourceSource
from sakuraplayer.resources.rejection import SourceRejectionService
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import SourceSubmissionService
from sakuraplayer.shared.migration import upgrade_database
from tests.fakes.cloud115 import FakeCloud115

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 27, 19, 0, tzinfo=timezone.utc)


@pytest.fixture
def context():
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task105_media_{uuid.uuid4().hex}"
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
        SourceImporter(factory, cipher=cipher, now=lambda: NOW).import_batch(
            "fixture.zip", (_row(1), _row(2))
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


def test_postgres_resolution_and_ready_selection_guards(context) -> None:
    factory, play = context
    first_job, second_job = _jobs(factory, play)
    _mark_resolving(factory, first_job)
    task_name = _job_task_name(factory, first_job)
    fake = FakeCloud115(
        directory_infos=[_directory(task_name), _directory(task_name)],
        file_batches=[(_file("main", "IPX-001.mkv"),)],
    )

    assert _resolver(factory, fake).run_once(worker_id="resolver-pg") == "worked"
    with factory() as session:
        first = session.get(CacheJob, first_job)
        media = session.scalar(
            select(RemoteMedia).where(RemoteMedia.cache_job_id == first_job)
        )
        assert first is not None and first.status == "ready"
        assert media is not None
        assert (
            session.scalar(
                select(func.count(CacheJobMediaSelection.media_id)).where(
                    CacheJobMediaSelection.cache_job_id == first_job
                )
            )
            == 1
        )

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.execute(
                delete(CacheJobMediaSelection).where(
                    CacheJobMediaSelection.cache_job_id == first_job
                )
            )

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(
                CacheJobMediaSelection(
                    cache_job_id=second_job,
                    sequence_no=0,
                    media_id=media.id,
                )
            )

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(
                RemoteSubtitle(
                    id=uuid.uuid4(),
                    cache_job_id=second_job,
                    media_id=media.id,
                    file_id="cross-job-subtitle",
                    pickcode="pick-cross-job-subtitle",
                    parent_cid="task",
                    name="IPX-001.srt",
                    extension="srt",
                    size_bytes=1000,
                    match_score=100,
                    match_evidence=["exact_stem"],
                    created_at=NOW,
                )
            )

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            job = session.get(CacheJob, second_job)
            assert job is not None
            job.status = "ready"
            job.capacity_class = "ready"


def test_postgres_cancellation_fences_late_resolution_write(context) -> None:
    factory, play = context
    job_id, _ = _jobs(factory, play)
    _mark_resolving(factory, job_id)
    queue = CacheJobClaimQueue(factory, now=lambda: NOW)
    claim = queue.claim_resolving(worker_id="resolver-cancelled")
    assert claim is not None
    plan = plan_media_selection((_file("late", "IPX-001.mkv"),), movie_number="IPX-001")

    cancelled = CancellationService(factory, now=lambda: NOW).request(
        job_id,
        confirmed=True,
    )
    assert cancelled.status == "cleaning"
    with pytest.raises(CacheJobClaimLost):
        queue.complete_resolution(claim, plan, ())

    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None and job.status == "cleaning"
        assert session.scalar(select(func.count(RemoteMedia.id))) == 0


def _jobs(factory, play) -> tuple[uuid.UUID, uuid.UUID]:
    with factory() as session:
        sources = tuple(
            session.execute(
                select(ResourceSource.movie_id, ResourceSource.id)
                .where(ResourceSource.movie_id.is_not(None))
                .order_by(ResourceSource.external_post_id)
            )
        )
    job_ids = tuple(
        play.create(
            movie_id=movie_id,
            source_id=source_id,
            idempotency_key=f"task105-postgres-{index:04d}",
        ).job.id
        for index, (movie_id, source_id) in enumerate(sources, start=1)
    )
    assert len(job_ids) == 2
    return job_ids[0], job_ids[1]


def _mark_resolving(factory, job_id: uuid.UUID) -> None:
    with factory.begin() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        job.status = "resolving"
        job.task_dir_cid = "task"
        job.remote_percent = 100


def _resolver(factory, fake):
    @asynccontextmanager
    async def cloud_scope(_claim):
        yield fake

    source_port = SourceSubmissionService(factory, cipher=_cipher())
    return CacheMediaResolver(
        CacheJobClaimQueue(factory, now=lambda: NOW),
        SourceRejectionClient(
            source_port,
            SourceRejectionService(factory, now=lambda: NOW),
        ),
        cloud_scope,
        now=lambda: NOW,
    )


def _cipher() -> SecretCipher:
    return SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"k" * 32},
        )
    )


def _directory(task_name: str) -> DirectoryInfo:
    return DirectoryInfo(
        cid="task",
        parent_cid="root",
        name=task_name,
        path=(DirectoryBreadcrumb("root", "SakuraPlayer-Cache"),),
    )


def _job_task_name(factory, job_id: uuid.UUID) -> str:
    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        return job.task_dir_name


def _file(file_id: str, name: str) -> RemoteFile:
    return RemoteFile(
        file_id=file_id,
        parent_cid="task",
        name=name,
        size_bytes=2_000_000_000,
        pickcode=f"pick-{file_id}",
        sha1=None,
        is_directory=False,
        is_video=True,
        duration_seconds=7200,
        blocked=False,
    )


def _row(index: int) -> dict[str, object]:
    return {
        "tid": index,
        "number": f"IPX-{index:03d}",
        "title": f"Title {index}",
        "publish_date": date(2026, 7, 27),
        "magnet": ":".join(("magnet", f"?xt=urn:btih:fixture-{index}")),
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/thread-fixture.htm",
        "size": 1024,
        "section": "亚洲有码",
        "category": None,
        "website": "sehuatang",
        "create_time": NOW,
        "update_time": NOW,
    }
