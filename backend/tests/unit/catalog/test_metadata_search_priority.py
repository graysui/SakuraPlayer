import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import MetadataJob
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 26, 7, 0, tzinfo=timezone.utc)


def _context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    queue = MetadataQueue(factory, now=lambda: NOW)
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number="ABP-100",
        raw_numbers=["ABP-100"],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add(movie)
    return engine, factory, queue, movie


def test_search_promotes_queued_job_and_reuses_running_job() -> None:
    engine, factory, queue, movie = _context()
    try:
        queued = queue.enqueue(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 25),
            reason="history",
        )

        promoted = queue.ensure_search_priority(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 25),
        )
        with factory() as session:
            persisted = session.get(MetadataJob, queued.job_id)
            assert persisted is not None
            assert (persisted.priority, persisted.reason) == (10, "manual_or_search")
        claim = queue.claim_next("search-worker", lease_duration=timedelta(seconds=30))
        running = queue.ensure_search_priority(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 25),
        )
        with factory.begin() as session:
            persisted_movie = session.get(Movie, movie.id, with_for_update=True)
            assert persisted_movie is not None
            persisted_movie.catalog_state = "core_ready"
        completed = queue.ensure_search_priority(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 25),
        )

        assert promoted.job_id == queued.job_id
        assert running.job_id == queued.job_id
        assert promoted.state == "queued"
        assert claim is not None
        assert running.state == "running"
        assert completed.state == "completed"
    finally:
        engine.dispose()


def test_search_does_not_retry_failed_attempt() -> None:
    engine, _, queue, movie = _context()
    try:
        queued = queue.enqueue(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 25),
            reason="history",
        )
        claim = queue.claim_next("search-worker", lease_duration=timedelta(seconds=30))
        assert claim is not None
        queue.fail(claim, code="javdb_movie_not_found", detail="fixture")

        outcome = queue.ensure_search_priority(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 25),
        )

        assert outcome.job_id == queued.job_id
        assert outcome.state == "failed"
    finally:
        engine.dispose()
