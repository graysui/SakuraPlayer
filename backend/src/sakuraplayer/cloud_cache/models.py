from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from sakuraplayer.identity.models import Base


class Cloud115Binding(Base):
    __tablename__ = "cloud115_binding"
    __table_args__ = (
        CheckConstraint(
            "singleton_key",
            name="ck_cloud115_binding_singleton_key",
        ),
        CheckConstraint(
            "length(account_key) BETWEEN 1 AND 128",
            name="ck_cloud115_binding_account_key",
        ),
        CheckConstraint(
            "cookie_setting_key = 'cloud115.cookie'",
            name="ck_cloud115_binding_cookie_key",
        ),
        CheckConstraint(
            "login_app = 'alipaymini'",
            name="ck_cloud115_binding_login_app",
        ),
        CheckConstraint(
            "length(cache_root_cid) BETWEEN 1 AND 64",
            name="ck_cloud115_binding_root_cid",
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'unavailable', 'detached')",
            name="ck_cloud115_binding_status",
        ),
        CheckConstraint(
            "credential_version >= 1",
            name="ck_cloud115_binding_credential_version",
        ),
        UniqueConstraint(
            "singleton_key",
            name="uq_cloud115_binding_singleton_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    singleton_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    account_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    cookie_setting_key: Mapped[str] = mapped_column(
        ForeignKey("encrypted_setting.key", ondelete="RESTRICT"),
        nullable=False,
        default="cloud115.cookie",
    )
    login_app: Mapped[str] = mapped_column(
        String(32), nullable=False, default="alipaymini"
    )
    cache_root_cid: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    credential_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class CacheJob(Base):
    __tablename__ = "cache_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'submitting', 'offlining', 'submit_uncertain', "
            "'resolving', "
            "'awaiting_selection', 'ready', 'cancelling', 'cleaning', "
            "'cleanup_failed', 'failed', 'cleaned', 'detached')",
            name="ck_cache_job_status",
        ),
        CheckConstraint(
            "capacity_class IN ('queued', 'running', 'ready', 'released')",
            name="ck_cache_job_capacity_class",
        ),
        CheckConstraint(
            "(status = 'queued' AND capacity_class = 'queued') OR "
            "(status IN ('submitting', 'offlining', 'submit_uncertain', "
            "'resolving') "
            "AND capacity_class = 'running') OR "
            "(status IN ('awaiting_selection', 'ready', 'cleaning', "
            "'cleanup_failed') AND capacity_class = 'ready') OR "
            "(status = 'cancelling' AND capacity_class IN "
            "('queued', 'running', 'ready')) OR "
            "(status IN ('failed', 'cleaned', 'detached') "
            "AND capacity_class = 'released')",
            name="ck_cache_job_state_capacity",
        ),
        CheckConstraint(
            "binding_id IS NOT NULL OR status IN ('failed', 'cleaned', 'detached')",
            name="ck_cache_job_active_binding",
        ),
        CheckConstraint(
            "remote_percent >= 0 AND remote_percent <= 100",
            name="ck_cache_job_remote_percent",
        ),
        CheckConstraint(
            "length(account_key) BETWEEN 1 AND 128",
            name="ck_cache_job_account_key",
        ),
        CheckConstraint(
            "length(cache_root_cid) BETWEEN 1 AND 64",
            name="ck_cache_job_root_cid",
        ),
        CheckConstraint(
            "length(task_dir_name) BETWEEN 1 AND 128",
            name="ck_cache_job_task_dir_name",
        ),
        CheckConstraint(
            "(claim_owner IS NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL) OR "
            "(claim_owner IS NOT NULL AND claim_token IS NOT NULL "
            "AND claim_expires_at IS NOT NULL)",
            name="ck_cache_job_claim_shape",
        ),
        CheckConstraint(
            "(submit_started_at IS NULL OR task_dir_cid IS NOT NULL) AND "
            "(remote_info_hash IS NULL OR "
            "(task_dir_cid IS NOT NULL AND submit_started_at IS NOT NULL)) AND "
            "(status <> 'submit_uncertain' OR "
            "(task_dir_cid IS NOT NULL AND submit_started_at IS NOT NULL "
            "AND remote_info_hash IS NULL "
            "AND failure_code = 'cloud115_submit_uncertain'))",
            name="ck_cache_job_submission_shape",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resource_source.id", ondelete="RESTRICT"), nullable=False
    )
    binding_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "cloud115_binding.id",
            name="fk_cache_job_binding_id_cloud115_binding",
            ondelete="SET NULL",
        )
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    capacity_class: Mapped[str] = mapped_column(String(16), nullable=False)
    account_key: Mapped[str] = mapped_column(String(128), nullable=False)
    cache_root_cid: Mapped[str] = mapped_column(String(64), nullable=False)
    task_dir_cid: Mapped[str | None] = mapped_column(String(64))
    task_dir_name: Mapped[str] = mapped_column(String(128), nullable=False)
    remote_info_hash: Mapped[str | None] = mapped_column(String(128))
    submit_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remote_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_owner: Mapped[str | None] = mapped_column(String(128))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    failure_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


_ACTIVE_CACHE_STATUSES = (
    "queued",
    "submitting",
    "offlining",
    "submit_uncertain",
    "resolving",
    "awaiting_selection",
    "ready",
    "cancelling",
    "cleaning",
    "cleanup_failed",
)

Index(
    "uq_cache_job_active_source_binding",
    CacheJob.source_id,
    CacheJob.binding_id,
    unique=True,
    postgresql_where=CacheJob.status.in_(_ACTIVE_CACHE_STATUSES),
    sqlite_where=CacheJob.status.in_(_ACTIVE_CACHE_STATUSES),
)
Index(
    "uq_cache_job_task_dir_cid",
    CacheJob.task_dir_cid,
    unique=True,
    postgresql_where=CacheJob.task_dir_cid.is_not(None),
    sqlite_where=CacheJob.task_dir_cid.is_not(None),
)
Index("ix_cache_job_status_created", CacheJob.status, CacheJob.created_at)
Index("ix_cache_job_capacity_created", CacheJob.capacity_class, CacheJob.created_at)


class CachePlayRequest(Base):
    __tablename__ = "cache_play_request"
    __table_args__ = (
        CheckConstraint(
            "length(idempotency_key) BETWEEN 16 AND 128",
            name="ck_cache_play_request_idempotency_key_length",
        ),
        CheckConstraint(
            "idempotency_key ~ '^[A-Za-z0-9._~-]{16,128}$'",
            name="ck_cache_play_request_idempotency_key",
        ).ddl_if(dialect="postgresql"),
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    movie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("movie.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resource_source.id", ondelete="RESTRICT"), nullable=False
    )
    cache_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cache_job.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


__all__ = ["CacheJob", "CachePlayRequest", "Cloud115Binding"]
