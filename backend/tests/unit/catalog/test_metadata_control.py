from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import MetadataJob, MetadataWorkerControl
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)


def test_pause_blocks_new_claims_without_interrupting_running_and_resume_continues() -> (
    None
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    queue = MetadataQueue(factory, now=lambda: NOW)
    movies = [_movie("ABP-801"), _movie("ABP-802")]
    with factory.begin() as session:
        session.add_all(movies)
    for index, movie in enumerate(movies):
        queue.enqueue(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 8, 2 - index),
            reason="manual_or_search",
        )

    running = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))
    assert running is not None
    paused = queue.set_paused(True)

    assert paused.paused is True
    assert paused.queued == 1
    assert paused.running == 1
    assert queue.claim_next("worker-2", lease_duration=timedelta(minutes=5)) is None
    with factory() as session:
        assert session.get(MetadataJob, running.job_id).status == "running"
        assert session.get(MetadataWorkerControl, True).paused is True

    resumed = queue.set_paused(False)
    next_claim = queue.claim_next("worker-2", lease_duration=timedelta(minutes=5))

    assert resumed.paused is False
    assert next_claim is not None
    assert next_claim.job_id != running.job_id
    engine.dispose()


def test_control_snapshot_defaults_to_running_without_creating_state() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    queue = MetadataQueue(factory, now=lambda: NOW)

    snapshot = queue.control_snapshot()

    assert snapshot.paused is False
    assert snapshot.queued == snapshot.running == 0
    with factory() as session:
        assert session.scalar(select(MetadataWorkerControl)) is None
    engine.dispose()


def _movie(number: str) -> Movie:
    return Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
