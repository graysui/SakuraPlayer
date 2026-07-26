from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from sakuraplayer.identity.models import Base


class Favorite(Base):
    __tablename__ = "favorite"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('movie', 'actor')",
            name="ck_favorite_target_type",
        ),
        UniqueConstraint(
            "target_type",
            "target_id",
            name="uq_favorite_target",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


Index(
    "ix_favorite_target_created",
    Favorite.target_type,
    Favorite.created_at,
    Favorite.target_id,
)


_RANKING_SCOPE_CHECK = (
    "(board = 'top250' AND (year IS NULL OR year BETWEEN 2008 AND 2200)) OR "
    "(board IN ('daily', 'weekly', 'monthly') AND year IS NULL)"
)


class RankingSyncRequest(Base):
    __tablename__ = "ranking_sync_request"
    __table_args__ = (
        CheckConstraint(_RANKING_SCOPE_CHECK, name="ck_ranking_request_scope"),
        CheckConstraint(
            "status IN ('queued', 'claimed', 'completed', 'failed')",
            name="ck_ranking_request_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_ranking_request_attempt",
        ),
        CheckConstraint(
            "(status = 'queued' AND claim_owner IS NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL AND snapshot_id IS NULL "
            "AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'claimed' AND claim_owner IS NOT NULL "
            "AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL "
            "AND snapshot_id IS NULL AND completed_at IS NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'completed' AND claim_owner IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL "
            "AND snapshot_id IS NOT NULL AND completed_at IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'failed' AND claim_owner IS NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL AND snapshot_id IS NULL "
            "AND completed_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="ck_ranking_request_state",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    board: Mapped[str] = mapped_column(String(16), nullable=False)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    claim_owner: Mapped[str | None] = mapped_column(String(128))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ranking_snapshot.id", ondelete="RESTRICT")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "uq_ranking_request_slot",
    RankingSyncRequest.board,
    func.coalesce(RankingSyncRequest.year, 0),
    RankingSyncRequest.scheduled_for,
    unique=True,
)
Index(
    "uq_ranking_request_active_scope",
    RankingSyncRequest.board,
    func.coalesce(RankingSyncRequest.year, 0),
    unique=True,
    postgresql_where=RankingSyncRequest.status.in_(("queued", "claimed")),
    sqlite_where=RankingSyncRequest.status.in_(("queued", "claimed")),
)
Index(
    "ix_ranking_request_claim",
    RankingSyncRequest.status,
    RankingSyncRequest.scheduled_for,
    RankingSyncRequest.id,
)


class RankingSnapshot(Base):
    __tablename__ = "ranking_snapshot"
    __table_args__ = (
        CheckConstraint(_RANKING_SCOPE_CHECK, name="ck_ranking_snapshot_scope"),
        CheckConstraint(
            "status IN ('building', 'current', 'superseded')",
            name="ck_ranking_snapshot_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    board: Mapped[str] = mapped_column(String(16), nullable=False)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


Index(
    "uq_ranking_snapshot_current_scope",
    RankingSnapshot.board,
    func.coalesce(RankingSnapshot.year, 0),
    unique=True,
    postgresql_where=RankingSnapshot.status == "current",
    sqlite_where=RankingSnapshot.status == "current",
)
Index(
    "ix_ranking_snapshot_scope_created",
    RankingSnapshot.board,
    RankingSnapshot.year,
    RankingSnapshot.created_at,
    RankingSnapshot.id,
)


class RankingEntry(Base):
    __tablename__ = "ranking_entry"
    __table_args__ = (
        CheckConstraint("rank > 0", name="ck_ranking_entry_rank"),
        UniqueConstraint(
            "snapshot_id",
            "normalized_number",
            name="uq_ranking_entry_number",
        ),
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ranking_snapshot.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rank: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized_number: Mapped[str] = mapped_column(String(128), nullable=False)
    movie_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("movie.id", ondelete="SET NULL"),
        index=True,
    )


Index(
    "ix_ranking_entry_snapshot_rank",
    RankingEntry.snapshot_id,
    RankingEntry.rank,
)


__all__ = ["Favorite", "RankingEntry", "RankingSnapshot", "RankingSyncRequest"]
