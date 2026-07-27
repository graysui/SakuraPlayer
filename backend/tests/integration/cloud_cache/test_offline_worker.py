from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Thread

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.cancellation import CancellationService
from sakuraplayer.cloud_cache.domain.cache_job import CacheJobStatus
from sakuraplayer.cloud_cache.models import CacheJob, Cloud115Binding
from sakuraplayer.cloud_cache.play_request import PlayRequestService
from sakuraplayer.cloud_cache.worker.claim import (
    CacheJobClaimLost,
    CacheJobClaimQueue,
)
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import ResourceSource
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import SourceSubmissionService
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 27, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def context():
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task104_offline_{uuid.uuid4().hex}"
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
        version = secrets.create_secret("cloud115.cookie", b"UID=fixture").version
        with factory.begin() as session:
            session.add(
                Cloud115Binding(
                    id=uuid.uuid4(),
                    singleton_key=True,
                    account_key="account-fixture",
                    display_name=None,
                    cookie_setting_key="cloud115.cookie",
                    login_app="alipaymini",
                    cache_root_cid="root-fixture",
                    status="active",
                    credential_version=version,
                    last_verified_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        SourceImporter(factory, cipher=cipher, now=lambda: NOW).import_batch(
            "fixture.zip", tuple(_row(index) for index in range(1, 16))
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


def test_postgres_rejects_invalid_claim_and_submission_shapes(context) -> None:
    factory, play = context
    job_id = _create_jobs(factory, play, 1)[0]

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.execute(
                text("UPDATE cache_job SET claim_owner = 'partial' WHERE id = :id"),
                {"id": job_id},
            )

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.execute(
                text(
                    "UPDATE cache_job SET status = 'submit_uncertain', "
                    "failure_code = 'cloud115_submit_uncertain' WHERE id = :id"
                ),
                {"id": job_id},
            )


def test_postgres_claim_skips_row_locked_by_another_worker(context) -> None:
    factory, play = context
    job_ids = _create_jobs(factory, play, 2)
    result = []
    errors = []
    finished = Event()

    def claim() -> None:
        try:
            result.append(
                CacheJobClaimQueue(factory, now=lambda: NOW).claim_next(
                    worker_id="worker-b"
                )
            )
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    with factory.begin() as session:
        locked_id = session.scalar(
            select(CacheJob.id)
            .where(CacheJob.id.in_(job_ids))
            .order_by(CacheJob.created_at, CacheJob.id)
            .with_for_update()
            .limit(1)
        )
        thread = Thread(target=claim)
        thread.start()
        completed_while_locked = finished.wait(2)
    thread.join(5)

    assert not errors
    assert completed_while_locked is True
    assert result[0] is not None and result[0].job_id != locked_id


def test_postgres_expired_claim_replacement_fences_old_token(context) -> None:
    factory, play = context
    _create_jobs(factory, play, 1)
    clock = {"now": NOW}
    queue = CacheJobClaimQueue(
        factory,
        now=lambda: clock["now"],
        lease=timedelta(seconds=30),
    )
    old = queue.claim_next(worker_id="worker-old")
    assert old is not None
    clock["now"] += timedelta(seconds=31)
    replacement = queue.claim_next(worker_id="worker-new")

    assert replacement is not None
    assert replacement.claim_token != old.claim_token
    with pytest.raises(CacheJobClaimLost):
        queue.save_task_directory(old, "stale-directory")


def test_postgres_concurrent_queue_promotion_respects_two_running_slots(
    context,
) -> None:
    factory, play = context
    job_ids = _create_jobs(factory, play, 12)
    with factory.begin() as session:
        running = tuple(
            session.scalars(
                select(CacheJob).where(CacheJob.capacity_class == "running")
            )
        )
        assert len(running) == 2
        for job in running:
            job.status = CacheJobStatus.FAILED.value
            job.capacity_class = "released"

    def claim(index: int):
        return CacheJobClaimQueue(factory, now=lambda: NOW).claim_next(
            worker_id=f"promoter-{index}"
        )

    with ThreadPoolExecutor(max_workers=3) as executor:
        claims = list(executor.map(claim, range(3)))

    assert sum(item is not None for item in claims) == 2
    assert {item.job_id for item in claims if item is not None}.issubset(set(job_ids))
    with factory() as session:
        running_jobs = tuple(
            session.scalars(
                select(CacheJob).where(CacheJob.capacity_class == "running")
            )
        )
        assert len(running_jobs) == 2


def test_postgres_cancel_preserves_claim_during_mkdir_side_effect(context) -> None:
    factory, play = context
    job_id = _create_jobs(factory, play, 1)[0]
    queue = CacheJobClaimQueue(factory, now=lambda: NOW)
    claim = queue.claim_next(worker_id="worker-a")
    assert claim is not None

    result = CancellationService(factory, now=lambda: NOW).request(
        job_id, confirmed=True
    )

    assert result.status == "cancelling"
    current = queue.save_task_directory(claim, "task-directory")
    assert current.status is CacheJobStatus.CANCELLING
    queue.complete_cancel(current)
    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        assert (job.status, job.task_dir_cid) == ("cleaning", "task-directory")


def _create_jobs(factory, play, count: int) -> list[uuid.UUID]:
    with factory() as session:
        sources = tuple(
            session.execute(
                select(ResourceSource.movie_id, ResourceSource.id)
                .where(ResourceSource.movie_id.is_not(None))
                .order_by(ResourceSource.external_post_id)
                .limit(count)
            )
        )
    return [
        play.create(
            movie_id=movie_id,
            source_id=source_id,
            idempotency_key=f"task104-postgres-{index:04d}",
        ).job.id
        for index, (movie_id, source_id) in enumerate(sources, start=1)
    ]


def _row(index: int) -> dict[str, object]:
    return {
        "tid": index,
        "number": f"IPX-{index:03d}",
        "title": f"Title {index}",
        "publish_date": date(2026, 7, 27),
        "magnet": f"magnet:?xt=urn:btih:fixture-{index}",
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/thread-fixture.htm",
        "size": 1024,
        "section": "亚洲有码",
        "category": None,
        "website": "sehuatang",
        "create_time": NOW,
        "update_time": NOW,
    }
