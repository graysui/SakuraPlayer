from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
from threading import Barrier, BrokenBarrierError
import uuid

import pytest
from sqlalchemy import create_engine, func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import (
    MetadataQueue,
    MetadataQueueProblem,
)
from sakuraplayer.catalog import metadata_seeder as metadata_seeder_module
from sakuraplayer.catalog.metadata_seeder import MetadataQueueSeeder, SeedOutcome
from sakuraplayer.catalog.models import MetadataJob, MetadataQueueState, MetadataStage
from sakuraplayer.resources.initial_scope import InitialScopeSelector
from sakuraplayer.resources.models import Movie, ResourceSource
from sakuraplayer.shared.migration import upgrade_database
from sakuraplayer.worker.metadata_supervisor import MetadataSupervisor


pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc)


@dataclass
class MutableNow:
    value: datetime = NOW

    def __call__(self) -> datetime:
        return self.value


@dataclass
class MutableMonotonic:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value


class BlockingProcess:
    def __init__(self) -> None:
        self.exit_code: int | None = None
        self.terminated = False

    @property
    def pid(self) -> int:
        return 1

    def poll(self) -> int | None:
        return self.exit_code

    def terminate_group(self) -> None:
        self.terminated = True
        self.exit_code = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        assert self.exit_code is not None
        return self.exit_code


class RecordingLauncher:
    def __init__(self) -> None:
        self.processes: dict[uuid.UUID, BlockingProcess] = {}
        self.claims = {}

    def is_available(self) -> bool:
        return True

    def start(self, claim) -> BlockingProcess:
        process = BlockingProcess()
        self.processes[claim.job_id] = process
        self.claims[claim.job_id] = claim
        return process


class QueueProbe:
    def __init__(self, delegate: MetadataQueue, *, barrier: Barrier | None = None) -> None:
        self.delegate = delegate
        self.barrier = barrier
        self.calls: list[uuid.UUID] = []

    def enqueue(self, **kwargs):
        self.calls.append(kwargs["movie_id"])
        if self.barrier is not None and len(self.calls) <= self.barrier.parties:
            try:
                self.barrier.wait(timeout=0.25)
            except BrokenBarrierError:
                pass
        return self.delegate.enqueue(**kwargs)


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task007_{uuid.uuid4().hex}"
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
def queue_context(database_url: str):
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    clock = MutableNow()
    try:
        yield MetadataQueue(factory, now=clock), factory, clock, engine
    finally:
        engine.dispose()


def add_movie(factory: sessionmaker, number: str) -> Movie:
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add(movie)
    return movie


def add_source(factory: sessionmaker, movie: Movie, tid: int, publish_date: date) -> None:
    with factory.begin() as session:
        session.add(
            ResourceSource(
                id=uuid.uuid4(),
                website="sehuatang",
                external_post_id=tid,
                movie_id=movie.id,
                raw_number=movie.normalized_number,
                normalized_number=movie.normalized_number,
                title=movie.normalized_number,
                publish_date=publish_date,
                section="亚洲有码",
                category=None,
                resource_size_mb=None,
                detail_url=None,
                preview_urls=[],
                magnet_key_id=None,
                magnet_nonce=None,
                magnet_ciphertext=None,
                identification_status="identified",
                source_created_at=None,
                source_updated_at=None,
                imported_at=NOW,
            )
        )


def add_failed_metadata_job(
    factory: sessionmaker,
    movie: Movie,
    *,
    sort_date: date,
) -> None:
    with factory.begin() as session:
        session.add(
            MetadataJob(
                id=uuid.uuid4(),
                movie_id=movie.id,
                normalized_number=movie.normalized_number,
                priority=40,
                reason="initial",
                sort_date=sort_date,
                retry_mode="full",
                requested_stages=[],
                status="failed",
                attempt_no=1,
                parent_job_id=None,
                claim_owner=None,
                claim_expires_at=None,
                started_at=NOW,
                finished_at=NOW,
                elapsed_ms=0,
                failure_code="fixture_failure",
                failure_detail="fixture_failure",
                created_at=NOW,
            )
        )


def test_migration_creates_metadata_constraints_and_indexes(queue_context) -> None:
    _, _, _, engine = queue_context
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert {"metadata_job", "metadata_stage"}.issubset(
            inspector.get_table_names()
        )
        indexes = {item["name"]: item for item in inspector.get_indexes("metadata_job")}
        assert indexes["uq_metadata_job_active_number"]["unique"] is True
        assert "ix_metadata_job_claim" in indexes
        foreign_keys = inspector.get_foreign_keys("metadata_stage")
        assert foreign_keys[0]["referred_table"] == "metadata_job"


def test_persistent_seeder_freezes_initial_scope_then_streams_history(
    queue_context,
) -> None:
    queue, factory, clock, _ = queue_context
    recent = [add_movie(factory, f"ABP-{value:03d}") for value in range(70, 73)]
    old = add_movie(factory, "ABP-073")
    for offset, movie in enumerate(recent):
        add_source(factory, movie, 700 + offset, date(2026, 7, 24 - offset))
    add_source(factory, old, 703, date(2026, 1, 1))
    seeder = MetadataQueueSeeder(
        factory,
        queue=queue,
        selector=InitialScopeSelector(factory),
        now=clock,
        source_ready=lambda: True,
    )

    first = seeder.seed_once()
    second = seeder.seed_once()
    late = add_movie(factory, "ABP-074")
    add_source(factory, late, 704, date(2026, 7, 25))
    third = seeder.seed_once()

    assert first.initial == 3
    assert second.history == 1
    assert third.history == 1
    with factory() as session:
        reasons = {
            job.normalized_number: job.reason
            for job in session.scalars(select(MetadataJob))
        }
        state = session.get(MetadataQueueState, True)
    assert state is not None and state.initial_completed_at == NOW
    assert {reasons[movie.normalized_number] for movie in recent} == {"initial"}
    assert reasons[old.normalized_number] == "history"
    assert reasons[late.normalized_number] == "history"


def test_seeder_scans_past_a_full_batch_of_failed_movies(queue_context) -> None:
    queue, factory, clock, _ = queue_context
    queue_probe = QueueProbe(queue)
    publish_date = date(2026, 7, 25)
    for value in range(100):
        movie = add_movie(factory, f"ABP-{value:03d}")
        add_source(factory, movie, 800 + value, publish_date)
        add_failed_metadata_job(factory, movie, sort_date=publish_date)
    fresh = add_movie(factory, "ABP-100")
    add_source(factory, fresh, 900, publish_date)
    seeder = MetadataQueueSeeder(
        factory,
        queue=queue_probe,  # type: ignore[arg-type]
        selector=InitialScopeSelector(factory),
        now=clock,
        source_ready=lambda: True,
    )

    outcome = seeder.seed_once()

    assert outcome.initial == 1
    assert queue_probe.calls == [fresh.id]
    with factory() as session:
        created = session.scalar(
            select(MetadataJob).where(MetadataJob.movie_id == fresh.id)
        )
    assert created is not None


def test_concurrent_seeders_initialize_one_persistent_state(queue_context) -> None:
    queue, factory, clock, _ = queue_context
    barrier = Barrier(2)

    def seed() -> SeedOutcome:
        def synchronized_source_ready() -> bool:
            barrier.wait()
            return True

        return MetadataQueueSeeder(
            factory,
            queue=queue,
            selector=InitialScopeSelector(factory),
            now=clock,
            source_ready=synchronized_source_ready,
        ).seed_once()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: seed(), range(2)))

    assert outcomes == [SeedOutcome(), SeedOutcome()]
    with factory() as session:
        states = list(session.scalars(select(MetadataQueueState)))
    assert len(states) == 1


def test_concurrent_seeders_cannot_exceed_the_initial_movie_limit(
    queue_context,
    monkeypatch,
) -> None:
    queue, factory, clock, _ = queue_context
    monkeypatch.setattr(metadata_seeder_module, "INITIAL_LIMIT", 1)
    for value in range(2):
        movie = add_movie(factory, f"IPX-{value:03d}")
        add_source(factory, movie, 950 + value, date(2026, 7, 25))
    source_barrier = Barrier(2)
    queue_probe = QueueProbe(queue, barrier=Barrier(2))

    def seed() -> SeedOutcome:
        def source_ready() -> bool:
            source_barrier.wait()
            return True

        return MetadataQueueSeeder(
            factory,
            queue=queue_probe,  # type: ignore[arg-type]
            selector=InitialScopeSelector(factory),
            now=clock,
            source_ready=source_ready,
        ).seed_once()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: seed(), range(2)))

    with factory() as session:
        initial_movies = session.scalar(
            select(func.count(func.distinct(MetadataJob.movie_id))).where(
                MetadataJob.reason == "initial"
            )
        )
    assert initial_movies == 1


def test_priority_date_order_and_fixed_database_slots(queue_context) -> None:
    queue, factory, _, _ = queue_context
    candidates = [
        ("ABP-001", "history", date(2026, 7, 25)),
        ("ABP-002", "daily", None),
        ("ABP-003", "daily", date(2026, 7, 20)),
        ("ABP-004", "daily", date(2026, 7, 24)),
        ("ABP-005", "ranking", date(2026, 7, 1)),
    ]
    outcomes = []
    for number, reason, sort_date in candidates:
        movie = add_movie(factory, number)
        outcomes.append(
            queue.enqueue(
                movie_id=movie.id,
                normalized_number=number,
                sort_date=sort_date,
                reason=reason,
            )
        )

    claims = [
        queue.claim_next("worker-a", lease_duration=timedelta(seconds=30))
        for _ in range(4)
    ]

    assert [item.normalized_number for item in claims[:3] if item] == [
        "ABP-005",
        "ABP-004",
        "ABP-003",
    ]
    assert claims[3] is None
    with factory() as session:
        assert list(
            session.scalars(
                select(MetadataJob.status).order_by(MetadataJob.normalized_number)
            )
        ).count("running") == 3
    assert all(outcome.created for outcome in outcomes)


def test_concurrent_enqueue_creates_one_active_attempt(queue_context) -> None:
    queue, factory, _, _ = queue_context
    movie = add_movie(factory, "ABP-010")
    barrier = Barrier(2)

    def enqueue() -> bool:
        barrier.wait()
        return queue.enqueue(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 25),
            reason="initial",
        ).created

    with ThreadPoolExecutor(max_workers=2) as executor:
        created = list(executor.map(lambda _: enqueue(), range(2)))

    assert sorted(created) == [False, True]
    with factory() as session:
        jobs = list(session.scalars(select(MetadataJob)))
        stages = list(session.scalars(select(MetadataStage)))
    assert len(jobs) == 1
    assert jobs[0].attempt_no == 1
    assert len(stages) == 6


def test_two_supervisors_share_the_same_three_database_slots(queue_context) -> None:
    queue, factory, clock, _ = queue_context
    for value in range(10, 15):
        movie = add_movie(factory, f"IPX-{value:03d}")
        queue.enqueue(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, value),
            reason="daily",
        )
    barrier = Barrier(2)

    def claim_two(worker_id: str):
        local_queue = MetadataQueue(factory, now=clock)
        barrier.wait()
        return [
            local_queue.claim_next(
                worker_id,
                lease_duration=timedelta(seconds=30),
            )
            for _ in range(2)
        ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim_two, ("worker-a", "worker-b")))

    claims = [claim for group in results for claim in group if claim is not None]
    assert len(claims) == 3
    with factory() as session:
        running = session.scalar(
            select(func.count(MetadataJob.id)).where(MetadataJob.status == "running")
        )
    assert running == 3


def test_expired_claim_is_recovered_without_new_attempt(queue_context) -> None:
    queue, factory, clock, _ = queue_context
    movie = add_movie(factory, "ABP-020")
    outcome = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 25),
        reason="initial",
    )
    first = queue.claim_next("worker-old", lease_duration=timedelta(seconds=30))
    assert first is not None
    queue.start_stage(first, "javdb_core")
    clock.value += timedelta(seconds=31)

    restarted = MetadataQueue(factory, now=clock)
    second = restarted.claim_next(
        "worker-new",
        lease_duration=timedelta(seconds=30),
    )

    assert second is not None
    assert second.job_id == outcome.job_id == first.job_id
    assert second.claim_owner != first.claim_owner
    with factory() as session:
        job = session.get(MetadataJob, outcome.job_id)
        stage = session.get(MetadataStage, (outcome.job_id, "javdb_core"))
    assert job is not None and stage is not None
    assert job.attempt_no == 1
    assert job.status == "running"
    assert stage.status == "pending"
    with pytest.raises(MetadataQueueProblem) as stale:
        restarted.fail(first, code="metadata_timeout", detail="metadata_timeout")
    assert stale.value.code == "metadata_claim_lost"


def test_expired_child_cannot_fail_attempt_before_it_is_reclaimed(
    queue_context,
) -> None:
    queue, factory, clock, _ = queue_context
    movie = add_movie(factory, "ABP-021")
    queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 25),
        reason="initial",
    )
    claim = queue.claim_next("worker-old", lease_duration=timedelta(seconds=30))
    assert claim is not None
    clock.value += timedelta(seconds=31)

    with pytest.raises(MetadataQueueProblem) as expired:
        queue.fail(claim, code="metadata_child_failed", detail="metadata_child_failed")

    assert expired.value.code == "metadata_claim_lost"
    with factory() as session:
        job = session.get(MetadataJob, claim.job_id)
    assert job is not None and job.status == "running"


def test_failed_job_only_retries_through_explicit_new_attempt(queue_context) -> None:
    queue, factory, _, _ = queue_context
    movie = add_movie(factory, "ABP-030")
    first = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 20),
        reason="history",
    )
    claim = queue.claim_next("worker-a", lease_duration=timedelta(seconds=30))
    assert claim is not None
    queue.fail(claim, code="javdb_upstream_error", detail="safe_fixture")

    automatic = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 25),
        reason="manual_or_search",
    )
    retry = queue.manual_retry(first.job_id)

    assert automatic.job_id == first.job_id
    assert automatic.created is False
    assert retry.created is True
    with factory() as session:
        jobs = list(
            session.scalars(
                select(MetadataJob).order_by(MetadataJob.attempt_no)
            )
        )
    assert [(job.status, job.attempt_no) for job in jobs] == [
        ("failed", 1),
        ("queued", 2),
    ]
    assert jobs[1].parent_job_id == jobs[0].id
    assert jobs[1].priority == 10
    assert jobs[1].sort_date == jobs[0].sort_date
    assert jobs[0].failure_code == "javdb_upstream_error"

    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.execute(
                update(MetadataJob)
                .where(MetadataJob.id == jobs[0].id)
                .values(
                    status="queued",
                    started_at=None,
                    finished_at=None,
                    elapsed_ms=None,
                    failure_code=None,
                    failure_detail=None,
                )
            )


def test_enrichment_retry_whitelists_only_warning_or_missing_stages(
    queue_context,
) -> None:
    queue, factory, _, _ = queue_context
    movie = add_movie(factory, "ABP-040")
    first = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 21),
        reason="initial",
    )
    claim = queue.claim_next("worker-a", lease_duration=timedelta(seconds=30))
    assert claim is not None
    queue.start_stage(claim, "javdb_core")
    with factory.begin() as session:
        persisted_movie = session.get(Movie, movie.id, with_for_update=True)
        assert persisted_movie is not None
        persisted_movie.catalog_state = "core_ready"
    queue.finish_stage(claim, "javdb_core", status="succeeded")
    for stage in ("images", "dmm", "actor_map", "gfriends", "translation"):
        queue.start_stage(claim, stage)
        queue.finish_stage(
            claim,
            stage,
            status="warning" if stage == "images" else "succeeded",
            failure_code="image_download_failed" if stage == "images" else None,
        )
    queue.complete(claim, with_warnings=True)

    retry = queue.retry_enrichment(first.job_id, stages=("images",))

    with factory() as session:
        job = session.get(MetadataJob, retry.job_id)
        stages = {
            item.stage: item.status
            for item in session.scalars(
                select(MetadataStage).where(MetadataStage.job_id == retry.job_id)
            )
        }
    assert job is not None
    assert job.retry_mode == "missing_enrichment"
    assert job.requested_stages == ["images"]
    assert job.parent_job_id == first.job_id
    assert stages["images"] == "pending"
    assert all(
        status == "skipped" for stage, status in stages.items() if stage != "images"
    )
    with pytest.raises(MetadataQueueProblem) as invalid:
        queue.retry_enrichment(first.job_id, stages=("translation",))
    assert invalid.value.code == "metadata_job_no_retryable_enrichment"

    retry_claim = queue.claim_next(
        "worker-retry",
        lease_duration=timedelta(seconds=30),
    )
    assert retry_claim is not None and retry_claim.job_id == retry.job_id
    queue.start_stage(retry_claim, "images")
    queue.finish_stage(
        retry_claim,
        "images",
        status="warning",
        failure_code="image_download_failed",
    )
    queue.complete(retry_claim, with_warnings=True)
    with pytest.raises(MetadataQueueProblem) as chained:
        queue.retry_enrichment(retry.job_id, stages=("translation",))
    assert chained.value.code == "metadata_job_no_retryable_enrichment"


def test_failed_core_ready_attempt_can_retry_only_explicit_missing_enrichment(
    queue_context,
) -> None:
    queue, factory, _, _ = queue_context
    movie = add_movie(factory, "ABP-041")
    first = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 25),
        reason="initial",
    )
    claim = queue.claim_next("worker-a", lease_duration=timedelta(seconds=30))
    assert claim is not None
    queue.start_stage(claim, "javdb_core")
    with factory.begin() as session:
        persisted = session.get(Movie, movie.id, with_for_update=True)
        assert persisted is not None
        persisted.catalog_state = "core_ready"
    queue.finish_stage(claim, "javdb_core", status="succeeded")
    queue.start_stage(claim, "images")
    queue.fail_after_termination(
        claim,
        code="metadata_timeout",
        detail="metadata_timeout",
    )

    retry = queue.retry_enrichment(first.job_id, stages=("images", "dmm"))

    with factory() as session:
        job = session.get(MetadataJob, retry.job_id)
    assert job is not None
    assert job.retry_mode == "missing_enrichment"
    assert job.requested_stages == ["images", "dmm"]
    assert "translation" not in job.requested_stages


def test_failed_full_retry_without_current_core_success_cannot_retry_enrichment(
    queue_context,
) -> None:
    queue, factory, _, _ = queue_context
    movie = add_movie(factory, "ABP-042")
    first = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 25),
        reason="initial",
    )
    first_claim = queue.claim_next(
        "worker-first",
        lease_duration=timedelta(seconds=30),
    )
    assert first_claim is not None
    queue.start_stage(first_claim, "javdb_core")
    with factory.begin() as session:
        persisted = session.get(Movie, movie.id, with_for_update=True)
        assert persisted is not None
        persisted.catalog_state = "core_ready"
    queue.finish_stage(first_claim, "javdb_core", status="succeeded")
    queue.start_stage(first_claim, "images")
    queue.fail(first_claim, code="metadata_child_failed", detail="safe_fixture")
    second = queue.manual_retry(first.job_id)
    second_claim = queue.claim_next(
        "worker-second",
        lease_duration=timedelta(seconds=30),
    )
    assert second_claim is not None and second_claim.job_id == second.job_id
    queue.start_stage(second_claim, "javdb_core")
    queue.fail(second_claim, code="javdb_upstream_error", detail="safe_fixture")

    with pytest.raises(MetadataQueueProblem) as invalid:
        queue.retry_enrichment(second.job_id, stages=("images",))

    assert invalid.value.code == "metadata_job_no_retryable_enrichment"


def test_supervisor_timeout_kills_group_and_preserves_committed_core(
    queue_context,
) -> None:
    queue, factory, wall_clock, _ = queue_context
    movie = add_movie(factory, "ABP-050")
    outcome = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 25),
        reason="initial",
    )
    launcher = RecordingLauncher()
    monotonic_clock = MutableMonotonic()
    supervisor = MetadataSupervisor(
        queue=queue,
        launcher=launcher,
        clock=monotonic_clock,
    )
    supervisor.tick(worker_id="worker-timeout")
    claim = launcher.claims[outcome.job_id]
    queue.start_stage(claim, "javdb_core")
    with factory.begin() as session:
        persisted = session.get(Movie, movie.id, with_for_update=True)
        assert persisted is not None
        persisted.catalog_state = "core_ready"
    queue.finish_stage(claim, "javdb_core", status="succeeded")
    queue.start_stage(claim, "images")
    wall_clock.value += timedelta(seconds=600)
    monotonic_clock.value = 600

    snapshot = supervisor.tick(worker_id="worker-timeout")

    assert snapshot.running == 0
    assert launcher.processes[outcome.job_id].terminated is True
    with factory() as session:
        job = session.get(MetadataJob, outcome.job_id)
        persisted = session.get(Movie, movie.id)
        image_stage = session.get(MetadataStage, (outcome.job_id, "images"))
    assert job is not None and persisted is not None and image_stage is not None
    assert job.status == "failed"
    assert job.failure_code == "metadata_timeout"
    assert job.elapsed_ms == 600_000
    assert persisted.catalog_state == "core_ready"
    assert image_stage.status == "failed"


def test_supervisor_shutdown_recovers_same_attempt_after_restart(queue_context) -> None:
    queue, factory, wall_clock, _ = queue_context
    movie = add_movie(factory, "ABP-060")
    outcome = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 25),
        reason="initial",
    )
    launcher = RecordingLauncher()
    supervisor = MetadataSupervisor(
        queue=queue,
        launcher=launcher,
        clock=MutableMonotonic(),
    )
    supervisor.tick(worker_id="worker-old")

    supervisor.shutdown()
    wall_clock.value += timedelta(microseconds=1)
    recovered = MetadataQueue(factory, now=wall_clock).claim_next(
        "worker-new",
        lease_duration=timedelta(seconds=30),
    )

    assert recovered is not None
    assert recovered.job_id == outcome.job_id
    with factory() as session:
        jobs = list(session.scalars(select(MetadataJob)))
    assert len(jobs) == 1
    assert jobs[0].attempt_no == 1
