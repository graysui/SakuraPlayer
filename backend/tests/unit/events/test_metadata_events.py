from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)


def test_metadata_state_and_events_commit_in_the_same_transactions() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number="EVENT-001",
        raw_numbers=["EVENT-001"],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add(movie)
    queue = MetadataQueue(
        factory,
        now=lambda: NOW,
        event_writer=DomainEventWriter(now=lambda: NOW),
    )
    try:
        outcome = queue.enqueue(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=None,
            reason="daily",
        )
        claim = queue.claim_next("worker", lease_duration=timedelta(minutes=1))
        assert claim is not None
        queue.start_stage(claim, "javdb_core")
        queue.fail(claim, code="javdb_movie_not_found", detail="safe_failure")

        with factory() as session:
            events = list(
                session.scalars(select(DomainEvent).order_by(DomainEvent.sequence))
            )
        assert [event.event_type for event in events] == [
            "metadata.job.queued.v1",
            "metadata.job.started.v1",
            "metadata.job.stage_changed.v1",
            "metadata.job.failed.v1",
        ]
        assert [event.stream_version for event in events] == [1, 2, 3, 4]
        assert all(event.aggregate_id == outcome.job_id for event in events)
        assert events[-1].payload["error_code"] == "javdb_movie_not_found"
        assert "safe_failure" not in str(events[-1].payload)
    finally:
        engine.dispose()
