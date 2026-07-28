from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.models import Notification
from sakuraplayer.cloud_cache.notifications import (
    NotificationService,
    NotificationWriter,
)
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.identity.models import Base

NOW = datetime(2026, 7, 28, 13, 0, tzinfo=timezone.utc)


def test_notification_create_and_mark_read_are_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    event_writer = DomainEventWriter(now=lambda: NOW)
    writer = NotificationWriter(event_writer, now=lambda: NOW)
    resource_id = uuid.uuid4()
    try:
        with factory.begin() as session:
            first = writer.create(
                session,
                notification_type="cache_ready",
                resource_id=resource_id,
                error_code=None,
                dedupe_key=f"cache:{resource_id}:ready",
            )
        with factory.begin() as session:
            repeated = writer.create(
                session,
                notification_type="cache_ready",
                resource_id=resource_id,
                error_code=None,
                dedupe_key=f"cache:{resource_id}:ready",
            )
        assert repeated.id == first.id

        service = NotificationService(
            factory,
            event_writer=event_writer,
            now=lambda: NOW + timedelta(minutes=1),
        )
        marked = service.mark_read(first.id)
        repeated_mark = service.mark_read(first.id)
        assert marked.read_at == NOW + timedelta(minutes=1)
        assert repeated_mark.read_at == marked.read_at

        with factory() as session:
            events = list(
                session.scalars(select(DomainEvent).order_by(DomainEvent.sequence))
            )
            assert [event.event_type for event in events] == [
                "notification.created.v1",
                "notification.read.v1",
            ]
            assert len(list(session.scalars(select(Notification)))) == 1
    finally:
        engine.dispose()


def test_notification_prune_uses_fixed_thirty_day_retention() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    old_id = uuid.uuid4()
    fresh_id = uuid.uuid4()
    with factory.begin() as session:
        session.add_all(
            [
                Notification(
                    id=old_id,
                    type="cache_ready",
                    resource_id=uuid.uuid4(),
                    error_code=None,
                    dedupe_key="old",
                    created_at=NOW - timedelta(days=30),
                    read_at=None,
                ),
                Notification(
                    id=fresh_id,
                    type="cache_ready",
                    resource_id=uuid.uuid4(),
                    error_code=None,
                    dedupe_key="fresh",
                    created_at=NOW - timedelta(days=30) + timedelta(microseconds=1),
                    read_at=None,
                ),
            ]
        )
    try:
        service = NotificationService(factory, now=lambda: NOW)
        assert service.prune_expired() == 1
        with factory() as session:
            assert session.get(Notification, old_id) is None
            assert session.get(Notification, fresh_id) is not None
    finally:
        engine.dispose()
