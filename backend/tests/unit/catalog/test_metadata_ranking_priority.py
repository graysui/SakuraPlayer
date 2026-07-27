import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import MetadataJob
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 26, 7, 0, tzinfo=timezone.utc)
SORT_DATE = date(2026, 7, 25)


def _context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    queue = MetadataQueue(factory, now=lambda: NOW)
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number="ABP-200",
        raw_numbers=["ABP-200"],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add(movie)
    return engine, factory, queue, movie


def _ensure(queue: MetadataQueue, movie: Movie):
    return queue.ensure_ranking_priority(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=SORT_DATE,
    )


def test_ranking_creates_priority_20_and_promotes_lower_priority_queue() -> None:
    engine, factory, queue, movie = _context()
    try:
        created = _ensure(queue, movie)
        with factory() as session:
            persisted = session.get(MetadataJob, created.job_id)
            assert persisted is not None
            assert (persisted.priority, persisted.reason) == (20, "ranking")

        second_engine, second_factory, second_queue, second_movie = _context()
        try:
            history = second_queue.enqueue(
                movie_id=second_movie.id,
                normalized_number=second_movie.normalized_number,
                sort_date=None,
                reason="history",
            )
            promoted = _ensure(second_queue, second_movie)
            with second_factory() as session:
                persisted = session.get(MetadataJob, history.job_id)
                assert persisted is not None
                assert (persisted.priority, persisted.reason) == (20, "ranking")
                assert persisted.sort_date == SORT_DATE
            assert promoted.job_id == history.job_id
            assert promoted.state == "queued"
        finally:
            second_engine.dispose()
    finally:
        engine.dispose()


def test_ranking_preserves_priority_10_and_reuses_running_job() -> None:
    engine, factory, queue, movie = _context()
    try:
        manual = queue.enqueue(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=SORT_DATE,
            reason="manual_or_search",
        )
        queued = _ensure(queue, movie)
        with factory() as session:
            persisted = session.get(MetadataJob, manual.job_id)
            assert persisted is not None
            assert (persisted.priority, persisted.reason) == (10, "manual_or_search")

        claim = queue.claim_next(
            "ranking-worker",
            lease_duration=timedelta(seconds=30),
        )
        running = _ensure(queue, movie)

        assert claim is not None
        assert queued.job_id == running.job_id == manual.job_id
        assert queued.state == "queued"
        assert running.state == "running"
    finally:
        engine.dispose()


def test_ranking_does_not_retry_failed_and_reports_completed_core() -> None:
    engine, factory, queue, movie = _context()
    try:
        original = _ensure(queue, movie)
        claim = queue.claim_next(
            "ranking-worker",
            lease_duration=timedelta(seconds=30),
        )
        assert claim is not None
        queue.fail(claim, code="javdb_movie_not_found", detail="fixture")

        failed = _ensure(queue, movie)
        with factory() as session:
            assert session.scalar(select(func.count(MetadataJob.id))) == 1
        assert failed.job_id == original.job_id
        assert failed.state == "failed"

        with factory.begin() as session:
            persisted = session.get(Movie, movie.id, with_for_update=True)
            assert persisted is not None
            persisted.catalog_state = "core_ready"
        completed = _ensure(queue, movie)

        assert completed.job_id == original.job_id
        assert completed.state == "completed"
    finally:
        engine.dispose()
