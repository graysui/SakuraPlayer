from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.events.models import DomainEvent
from sakuraplayer.events.outbox import (
    DomainEventWriter,
    EventCursorUnavailable,
    EventLog,
)
from sakuraplayer.identity.models import Base


def event_context(now: datetime):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    writer = DomainEventWriter(now=lambda: now)
    return engine, factory, writer


def test_writer_assigns_global_sequence_and_per_aggregate_version() -> None:
    now = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
    engine, factory, writer = event_context(now)
    aggregate_a = uuid.uuid4()
    aggregate_b = uuid.uuid4()
    try:
        with factory.begin() as session:
            first = writer.append(
                session,
                stream="metadata",
                aggregate_id=aggregate_a,
                event_type="metadata.job.queued.v1",
                payload={"id": str(aggregate_a), "status": "queued"},
            )
            second = writer.append(
                session,
                stream="metadata",
                aggregate_id=aggregate_a,
                event_type="metadata.job.started.v1",
                payload={"id": str(aggregate_a), "status": "running"},
            )
            third = writer.append(
                session,
                stream="metadata",
                aggregate_id=aggregate_b,
                event_type="metadata.job.queued.v1",
                payload={"id": str(aggregate_b), "status": "queued"},
            )

        assert (first.sequence, second.sequence, third.sequence) == (1, 2, 3)
        assert (first.stream_version, second.stream_version) == (1, 2)
        assert third.stream_version == 1
        assert first.expires_at == now + timedelta(days=30)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "private"},
        {"nested": {"api_key": "private"}},
        {"url": "https://example.test/play?signature=private"},
        {"magnet": "magnet:?xt=urn:btih:private"},
    ],
)
def test_writer_rejects_payload_that_requires_redaction(
    payload: dict[str, object],
) -> None:
    now = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
    engine, factory, writer = event_context(now)
    try:
        with pytest.raises(ValueError, match="sensitive event payload"):
            with factory.begin() as session:
                writer.append(
                    session,
                    stream="metadata",
                    aggregate_id=uuid.uuid4(),
                    event_type="metadata.job.failed.v1",
                    payload=payload,
                )
        with factory() as session:
            assert list(session.scalars(select(DomainEvent))) == []
    finally:
        engine.dispose()


def test_transaction_rollback_removes_event_and_sequence_increment() -> None:
    now = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
    engine, factory, writer = event_context(now)
    aggregate_id = uuid.uuid4()
    try:
        with pytest.raises(RuntimeError, match="rollback"):
            with factory.begin() as session:
                writer.append(
                    session,
                    stream="metadata",
                    aggregate_id=aggregate_id,
                    event_type="metadata.job.queued.v1",
                    payload={"id": str(aggregate_id), "status": "queued"},
                )
                raise RuntimeError("rollback")
        with factory.begin() as session:
            event = writer.append(
                session,
                stream="metadata",
                aggregate_id=aggregate_id,
                event_type="metadata.job.queued.v1",
                payload={"id": str(aggregate_id), "status": "queued"},
            )
        assert event.sequence == 1
    finally:
        engine.dispose()


def test_event_log_orders_by_sequence_and_rejects_expired_cursor() -> None:
    now = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
    engine, factory, writer = event_context(now)
    try:
        with factory.begin() as session:
            first = writer.append(
                session,
                stream="metadata",
                aggregate_id=uuid.uuid4(),
                event_type="metadata.job.queued.v1",
                payload={"id": str(uuid.uuid4()), "status": "queued"},
            )
            second = writer.append(
                session,
                stream="metadata",
                aggregate_id=uuid.uuid4(),
                event_type="metadata.job.queued.v1",
                payload={"id": str(uuid.uuid4()), "status": "queued"},
            )
        log = EventLog(factory, now=lambda: now)
        assert [item.event_id for item in log.read_after(first.event_id)] == [
            second.event_id
        ]

        expired_log = EventLog(factory, now=lambda: now + timedelta(days=31))
        with pytest.raises(EventCursorUnavailable):
            expired_log.read_after(first.event_id)
    finally:
        engine.dispose()


def test_pruning_does_not_reset_global_or_stream_versions() -> None:
    now = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
    engine, factory, writer = event_context(now)
    aggregate_id = uuid.uuid4()
    try:
        with factory.begin() as session:
            first = writer.append(
                session,
                stream="metadata",
                aggregate_id=aggregate_id,
                event_type="metadata.job.queued.v1",
                payload={"id": str(aggregate_id), "status": "queued"},
            )
        future = now + timedelta(days=31)
        future_log = EventLog(factory, now=lambda: future)
        assert future_log.prune_expired() == 1
        with factory() as session:
            assert future_log.watermark(session) == (1, None)

        with factory.begin() as session:
            second = DomainEventWriter(now=lambda: future).append(
                session,
                stream="metadata",
                aggregate_id=aggregate_id,
                event_type="metadata.job.started.v1",
                payload={"id": str(aggregate_id), "status": "running"},
            )
        assert first.stream_version == 1
        assert (second.sequence, second.stream_version) == (2, 2)
    finally:
        engine.dispose()
