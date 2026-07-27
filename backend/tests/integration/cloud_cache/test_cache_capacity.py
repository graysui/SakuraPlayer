from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.binding_service import BindingService
from sakuraplayer.cloud_cache.capacity import (
    CacheCapacityService,
    CacheCapacityUnavailable,
    active_cache_jobs,
)
from sakuraplayer.cloud_cache.domain.cache_job import CacheJobStatus
from sakuraplayer.cloud_cache.models import CacheJob, CachePlayRequest, Cloud115Binding
from sakuraplayer.cloud_cache.play_request import CacheProblem, PlayRequestService
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import ResourceSource
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import SourceSubmissionService
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 27, 13, 30, tzinfo=timezone.utc)


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task103_cache_{uuid.uuid4().hex}"
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
def context(database_url: str):
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
        "fixture.zip",
        tuple(_row(index) for index in range(1, 16)),
    )
    service = PlayRequestService(
        factory,
        SourceSubmissionService(factory, cipher=cipher),
        now=lambda: NOW,
    )
    try:
        yield factory, service, secrets
    finally:
        engine.dispose()


def test_postgres_concurrent_requests_never_oversell_fixed_capacity(context) -> None:
    factory, service, _ = context
    sources = _sources(factory)[:14]

    def create(index_and_source):
        index, (movie_id, source_id) = index_and_source
        try:
            result = service.create(
                movie_id=movie_id,
                source_id=source_id,
                idempotency_key=f"parallel-key-{index:04d}",
            )
            return result.disposition, result.job.id
        except CacheProblem as error:
            return error.code, None

    with ThreadPoolExecutor(max_workers=14) as executor:
        outcomes = list(executor.map(create, enumerate(sources, start=1)))

    dispositions = [disposition for disposition, _ in outcomes]
    assert dispositions.count("started") == 2
    assert dispositions.count("queued") == 10
    assert dispositions.count("cache_queue_full") == 2
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(CacheJob.id)).where(
                    CacheJob.capacity_class == "running"
                )
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count(CacheJob.id)).where(
                    CacheJob.capacity_class == "queued"
                )
            )
            == 10
        )

        running_id = session.scalar(
            select(CacheJob.id).where(CacheJob.capacity_class == "running")
        )
        queued_ids = tuple(
            session.scalars(
                select(CacheJob.id).where(CacheJob.capacity_class == "queued").limit(2)
            )
        )
    assert running_id is not None
    capacity = CacheCapacityService(factory, now=lambda: NOW)
    capacity.transition(running_id, CacheJobStatus.FAILED)

    def start_queued(job_id):
        try:
            capacity.transition(job_id, CacheJobStatus.SUBMITTING)
            return "started"
        except CacheCapacityUnavailable:
            return "capacity_full"

    with ThreadPoolExecutor(max_workers=2) as executor:
        transition_outcomes = list(executor.map(start_queued, queued_ids))
    assert sorted(transition_outcomes) == ["capacity_full", "started"]
    snapshot = capacity.snapshot()
    assert (snapshot.running, snapshot.queued) == (2, 9)


def test_postgres_concurrent_idempotency_reuse_and_binding_history(context) -> None:
    factory, service, secrets = context
    movie_id, source_id = _sources(factory)[0]

    def same_key(_index):
        return service.create(
            movie_id=movie_id,
            source_id=source_id,
            idempotency_key="same-request-key-0001",
        ).job.id

    with ThreadPoolExecutor(max_workers=8) as executor:
        job_ids = list(executor.map(same_key, range(8)))
    assert len(set(job_ids)) == 1

    other_keys = ("other-request-key-01", "other-request-key-02")
    with ThreadPoolExecutor(max_workers=2) as executor:
        reused_ids = list(
            executor.map(
                lambda key: (
                    service.create(
                        movie_id=movie_id,
                        source_id=source_id,
                        idempotency_key=key,
                    ).job.id
                ),
                other_keys,
            )
        )
    assert set(reused_ids) == {job_ids[0]}
    with factory() as session:
        assert session.scalar(select(func.count(CacheJob.id))) == 1
        assert session.scalar(select(func.count(CachePlayRequest.idempotency_key))) == 3

    CacheCapacityService(factory, now=lambda: NOW).transition(
        job_ids[0], CacheJobStatus.FAILED
    )

    @asynccontextmanager
    async def unused_cloud_scope(_cookies):
        yield None

    BindingService(
        factory,
        secrets,
        unused_cloud_scope,
        active_cache_jobs=active_cache_jobs,
        now=lambda: NOW,
    ).remove()
    with factory() as session:
        job = session.get(CacheJob, job_ids[0])
        assert job is not None
        assert job.binding_id is None
        assert job.account_key == "account-fixture"
        assert job.cache_root_cid == "root-fixture"


def _sources(factory) -> list[tuple[uuid.UUID, uuid.UUID]]:
    with factory() as session:
        rows = list(
            session.execute(
                select(ResourceSource.movie_id, ResourceSource.id).order_by(
                    ResourceSource.external_post_id
                )
            )
        )
    return [(movie_id, source_id) for movie_id, source_id in rows if movie_id]


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
