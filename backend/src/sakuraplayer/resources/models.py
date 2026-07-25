from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
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


class AvdbSyncRequest(Base):
    __tablename__ = "avdb_sync_request"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('incremental_30d', 'full_reconcile')",
            name="ck_avdb_sync_request_mode",
        ),
        CheckConstraint(
            "(status = 'queued' AND claim_owner IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL "
            "AND completed_at IS NULL "
            "AND failure_code IS NULL AND sync_run_id IS NULL) OR "
            "(status = 'claimed' AND claim_owner IS NOT NULL "
            "AND claim_token IS NOT NULL AND claimed_at IS NOT NULL "
            "AND claim_expires_at IS NOT NULL "
            "AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'completed' AND claim_owner IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL "
            "AND completed_at IS NOT NULL "
            "AND failure_code IS NULL AND sync_run_id IS NOT NULL) OR "
            "(status = 'failed' AND claim_owner IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL "
            "AND completed_at IS NOT NULL "
            "AND failure_code IS NOT NULL)",
            name="ck_avdb_sync_request_state",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_avdb_sync_request_attempts"),
        UniqueConstraint(
            "mode",
            "scheduled_for",
            name="uq_avdb_sync_request_slot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    claim_owner: Mapped[str | None] = mapped_column(String(64))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    failure_detail: Mapped[str | None] = mapped_column(Text)
    sync_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("avdb_sync_run.id", ondelete="RESTRICT"),
    )


class AvdbSyncRun(Base):
    __tablename__ = "avdb_sync_run"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('incremental_30d', 'full_reconcile')",
            name="ck_avdb_sync_run_mode",
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_avdb_sync_run_status",
        ),
        CheckConstraint(
            "(status = 'running' AND completed_at IS NULL "
            "AND failure_code IS NULL AND failure_detail IS NULL "
            "AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL "
            "AND failure_code IS NULL AND failure_detail IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL) OR "
            "(status = 'failed' AND completed_at IS NOT NULL "
            "AND failure_code IS NOT NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL)",
            name="ck_avdb_sync_run_state",
        ),
        CheckConstraint("attempt_count >= 1", name="ck_avdb_sync_run_attempts"),
        UniqueConstraint(
            "repository",
            "release_id",
            "mode",
            name="uq_avdb_sync_run_release",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    repository: Mapped[str] = mapped_column(String(128), nullable=False)
    release_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    cursor: Mapped[dict[str, object]] = mapped_column(_JSON_VALUE, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    failure_detail: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict[str, int]] = mapped_column(_JSON_VALUE, nullable=False)
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class AvdbAsset(Base):
    __tablename__ = "avdb_asset"
    __table_args__ = (
        CheckConstraint(
            "length(sha256) = 64 AND lower(sha256) = sha256",
            name="ck_avdb_asset_digest_format",
        ),
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_avdb_asset_digest",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("byte_size > 0", name="ck_avdb_asset_byte_size"),
        CheckConstraint(
            "status IN ('downloaded', 'verified', 'decrypted', 'imported', 'failed')",
            name="ck_avdb_asset_status",
        ),
        UniqueConstraint(
            "sync_run_id",
            "asset_name",
            name="uq_avdb_asset_run_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("avdb_sync_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    manifest: Mapped[dict[str, object]] = mapped_column(_JSON_VALUE, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


Index(
    "ix_avdb_sync_request_claim",
    AvdbSyncRequest.status,
    AvdbSyncRequest.scheduled_for,
)


__all__ = ["AvdbAsset", "AvdbSyncRequest", "AvdbSyncRun", "Base"]
