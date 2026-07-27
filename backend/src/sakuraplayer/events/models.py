from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sakuraplayer.identity.models import Base

_JSON_VALUE = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True),
    "postgresql",
)


class EventSequence(Base):
    __tablename__ = "event_sequence"
    __table_args__ = (
        CheckConstraint("singleton_key", name="ck_event_sequence_singleton"),
        CheckConstraint("current_value >= 0", name="ck_event_sequence_value"),
    )

    singleton_key: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=True)
    current_value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class EventStreamVersion(Base):
    __tablename__ = "event_stream_version"
    __table_args__ = (
        CheckConstraint(
            "stream IN ('metadata', 'cache', 'credential', 'catalog', 'notification')",
            name="ck_event_stream_version_stream",
        ),
        CheckConstraint(
            "current_version > 0",
            name="ck_event_stream_version_value",
        ),
    )

    stream: Mapped[str] = mapped_column(String(64), primary_key=True)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    current_version: Mapped[int] = mapped_column(BigInteger, nullable=False)


class DomainEvent(Base):
    __tablename__ = "domain_event"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_domain_event_sequence"),
        CheckConstraint(
            "stream IN ('metadata', 'cache', 'credential', 'catalog', 'notification')",
            name="ck_domain_event_stream",
        ),
        CheckConstraint("stream_version > 0", name="ck_domain_event_stream_version"),
        CheckConstraint("length(event_type) >= 1", name="ck_domain_event_type"),
        CheckConstraint("expires_at > occurred_at", name="ck_domain_event_expiry"),
        UniqueConstraint("sequence", name="uq_domain_event_sequence"),
        UniqueConstraint(
            "stream",
            "aggregate_id",
            "stream_version",
            name="uq_domain_event_stream_version",
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stream: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    stream_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(_JSON_VALUE, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index("ix_domain_event_delivery", DomainEvent.sequence, DomainEvent.expires_at)
Index(
    "ix_domain_event_aggregate",
    DomainEvent.stream,
    DomainEvent.aggregate_id,
    DomainEvent.stream_version,
)


__all__ = ["DomainEvent", "EventSequence", "EventStreamVersion"]
