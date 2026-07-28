from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from sakuraplayer.identity.models import Base


class PlaybackSession(Base):
    __tablename__ = "playback_session"
    __table_args__ = (
        CheckConstraint("session_epoch >= 0", name="ck_playback_session_epoch"),
        CheckConstraint(
            "mode IN ('original', 'compatibility')", name="ck_playback_session_mode"
        ),
        CheckConstraint(
            "platform IN ('windows', 'harmonyos')",
            name="ck_playback_session_platform",
        ),
        CheckConstraint(
            "length(user_agent_hash) = 64",
            name="ck_playback_session_user_agent_hash",
        ),
        CheckConstraint("expires_at > issued_at", name="ck_playback_session_expiry"),
        ForeignKeyConstraint(
            ["cache_job_id", "media_id"],
            ["remote_media.cache_job_id", "remote_media.id"],
            name="fk_playback_session_owned_media",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_user.id", ondelete="CASCADE"), nullable=False
    )
    session_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie.id", ondelete="RESTRICT"), nullable=False
    )
    cache_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cache_job.id", ondelete="RESTRICT"), nullable=False
    )
    media_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    user_agent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlaybackLease(Base):
    __tablename__ = "playback_lease"
    __table_args__ = (
        CheckConstraint(
            "expires_at > last_heartbeat_at", name="ck_playback_lease_expiry"
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= last_heartbeat_at",
            name="ck_playback_lease_end",
        ),
        UniqueConstraint(
            "playback_session_id",
            "client_instance_id",
            name="uq_playback_lease_session_client",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    playback_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playback_session.id", ondelete="CASCADE"), nullable=False
    )
    client_instance_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MoviePlaybackState(Base):
    __tablename__ = "movie_playback_state"
    __table_args__ = (
        CheckConstraint(
            "position_seconds >= 0 AND position_seconds <= 999999999.999",
            name="ck_movie_playback_position",
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR "
            "(duration_seconds > 0 AND duration_seconds <= 999999999.999)",
            name="ck_movie_playback_duration",
        ),
        CheckConstraint(
            "NOT completed OR position_seconds = 0",
            name="ck_movie_playback_completed_position",
        ),
        CheckConstraint("version >= 1", name="ck_movie_playback_version"),
    )

    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie.id", ondelete="CASCADE"), primary_key=True
    )
    position_seconds: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_watched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index("ix_playback_session_cache_job", PlaybackSession.cache_job_id)
Index("ix_playback_lease_active", PlaybackLease.expires_at, PlaybackLease.ended_at)


__all__ = ["MoviePlaybackState", "PlaybackLease", "PlaybackSession"]
