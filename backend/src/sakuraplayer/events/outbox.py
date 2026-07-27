from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.events.models import (
    DomainEvent,
    EventSequence,
    EventStreamVersion,
)
from sakuraplayer.shared.redaction import redact_value, stable_error_code

EVENT_RETENTION = timedelta(days=30)
EVENT_STREAMS = frozenset(
    {"metadata", "cache", "credential", "catalog", "notification"}
)


class EventCursorUnavailable(LookupError):
    pass


class DomainEventWriter:
    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))

    def append(
        self,
        session: Session,
        *,
        stream: str,
        aggregate_id: uuid.UUID,
        event_type: str,
        payload: Mapping[str, object],
    ) -> DomainEvent:
        if stream not in EVENT_STREAMS:
            raise ValueError("invalid event stream")
        if stable_error_code(event_type.replace(".", "_")) == "internal_error":
            raise ValueError("invalid event type")
        safe_payload = dict(payload)
        if redact_value(safe_payload) != safe_payload:
            raise ValueError("sensitive event payload")

        current = self._utc_now()
        sequence = session.get(EventSequence, True, with_for_update=True)
        if sequence is None:
            sequence = EventSequence(singleton_key=True, current_value=0)
            session.add(sequence)
            session.flush()
        sequence.current_value += 1
        version = session.get(
            EventStreamVersion,
            (stream, aggregate_id),
            with_for_update=True,
        )
        if version is None:
            version = EventStreamVersion(
                stream=stream,
                aggregate_id=aggregate_id,
                current_version=1,
            )
            session.add(version)
        else:
            version.current_version += 1
        event = DomainEvent(
            event_id=uuid.uuid4(),
            sequence=sequence.current_value,
            stream=stream,
            aggregate_id=aggregate_id,
            stream_version=version.current_version,
            event_type=event_type,
            payload=safe_payload,
            occurred_at=current,
            expires_at=current + EVENT_RETENTION,
        )
        session.add(event)
        session.flush()
        return event

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("event clock must be timezone-aware")
        return current.astimezone(timezone.utc)


class EventLog:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def read_after(
        self,
        after_event_id: uuid.UUID | None,
        *,
        limit: int = 100,
    ) -> list[DomainEvent]:
        if not 1 <= limit <= 100:
            raise ValueError("event limit must be 1..100")
        current = self._utc_now()
        with self._session_factory() as session:
            after_sequence = 0
            if after_event_id is not None:
                cursor = session.scalar(
                    select(DomainEvent).where(
                        DomainEvent.event_id == after_event_id,
                        DomainEvent.expires_at > current,
                    )
                )
                if cursor is None:
                    raise EventCursorUnavailable from None
                after_sequence = cursor.sequence
            return list(
                session.scalars(
                    select(DomainEvent)
                    .where(
                        DomainEvent.sequence > after_sequence,
                        DomainEvent.expires_at > current,
                    )
                    .order_by(DomainEvent.sequence)
                    .limit(limit)
                )
            )

    def watermark(self, session: Session) -> tuple[int, uuid.UUID | None]:
        current = self._utc_now()
        sequence = session.get(EventSequence, True)
        watermark = sequence.current_value if sequence is not None else 0
        event = session.scalar(
            select(DomainEvent).where(
                DomainEvent.sequence == watermark,
                DomainEvent.expires_at > current,
            )
        )
        return watermark, event.event_id if event is not None else None

    def prune_expired(self) -> int:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                delete(DomainEvent).where(DomainEvent.expires_at <= current)
            )
        return int(result.rowcount or 0)

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("event log clock must be timezone-aware")
        return current.astimezone(timezone.utc)


__all__ = [
    "DomainEventWriter",
    "EVENT_RETENTION",
    "EVENT_STREAMS",
    "EventCursorUnavailable",
    "EventLog",
]
