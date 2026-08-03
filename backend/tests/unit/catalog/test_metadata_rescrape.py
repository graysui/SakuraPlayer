import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataQueue, MetadataQueueProblem
from sakuraplayer.catalog.models import MetadataJob, MetadataStage
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    queue = MetadataQueue(factory, now=lambda: NOW)
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number="ABP-227",
        raw_numbers=["ABP-227"],
        catalog_state="core_ready",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add(movie)
    try:
        yield factory, queue, movie
    finally:
        engine.dispose()


def test_rescrape_creates_manual_full_attempt_for_movie_id(context) -> None:
    factory, queue, movie = context

    outcome = queue.rescrape_movie(movie.id)

    with factory() as session:
        job = session.get(MetadataJob, outcome.job_id)
        assert job is not None
        stages = list(
            session.scalars(
                select(MetadataStage)
                .where(MetadataStage.job_id == job.id)
                .order_by(MetadataStage.stage)
            )
        )
    assert outcome.state == "queued"
    assert outcome.created is True
    assert (job.priority, job.reason, job.retry_mode) == (
        10,
        "manual_or_search",
        "full",
    )
    assert (job.attempt_no, job.parent_job_id) == (1, None)
    assert {stage.status for stage in stages} == {"pending"}


def test_rescrape_keeps_terminal_parent_immutable_and_increments_attempt(
    context,
) -> None:
    factory, queue, movie = context
    first = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 8, 1),
        reason="history",
    )
    claim = queue.claim_next("rescrape-worker", lease_duration=timedelta(seconds=30))
    assert claim is not None
    queue.fail(claim, code="javdb_upstream_error", detail="fixture")

    outcome = queue.rescrape_movie(movie.id)

    with factory() as session:
        parent = session.get(MetadataJob, first.job_id)
        child = session.get(MetadataJob, outcome.job_id)
        assert parent is not None and child is not None
    assert (parent.status, parent.failure_code, parent.attempt_no) == (
        "failed",
        "javdb_upstream_error",
        1,
    )
    assert (child.attempt_no, child.parent_job_id, child.priority) == (
        2,
        parent.id,
        10,
    )


def test_rescrape_promotes_queued_full_and_reuses_running_full(context) -> None:
    factory, queue, movie = context
    queued = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 8, 1),
        reason="history",
    )

    promoted = queue.rescrape_movie(movie.id)
    with factory() as session:
        job = session.get(MetadataJob, queued.job_id)
        assert job is not None
        assert (job.priority, job.reason) == (10, "manual_or_search")
    claim = queue.claim_next("rescrape-worker", lease_duration=timedelta(seconds=30))
    assert claim is not None
    running = queue.rescrape_movie(movie.id)

    assert promoted.job_id == running.job_id == queued.job_id
    assert promoted == type(promoted)(queued.job_id, state="queued", created=False)
    assert running == type(running)(queued.job_id, state="running", created=False)


def test_rescrape_rejects_active_enrichment_attempt(context) -> None:
    factory, queue, movie = context
    queued = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 8, 1),
        reason="manual_or_search",
    )
    with factory.begin() as session:
        job = session.get(MetadataJob, queued.job_id, with_for_update=True)
        assert job is not None
        job.retry_mode = "missing_enrichment"
        job.requested_stages = ["dmm"]

    with pytest.raises(MetadataQueueProblem) as error:
        queue.rescrape_movie(movie.id)

    assert (error.value.status_code, error.value.code) == (
        409,
        "metadata_job_already_active",
    )
    with factory() as session:
        assert session.scalar(
            select(MetadataJob).where(MetadataJob.movie_id == movie.id)
        )
        assert (
            session.scalar(
                select(MetadataJob).where(MetadataJob.movie_id == movie.id)
            ).retry_mode
            == "missing_enrichment"
        )


def test_rescrape_rejects_unknown_movie(context) -> None:
    _, queue, _ = context

    with pytest.raises(MetadataQueueProblem) as error:
        queue.rescrape_movie(uuid.uuid4())

    assert (error.value.status_code, error.value.code) == (404, "resource_not_found")
