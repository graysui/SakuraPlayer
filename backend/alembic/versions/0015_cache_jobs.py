"""Add cache jobs, capacity state, and play request idempotency.

Revision ID: 0015_cache_jobs
Revises: 0014_cloud115_binding
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_cache_jobs"
down_revision: Union[str, Sequence[str], None] = "0014_cloud115_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ACTIVE_STATUSES = (
    "queued",
    "submitting",
    "offlining",
    "resolving",
    "awaiting_selection",
    "ready",
    "cancelling",
    "cleaning",
    "cleanup_failed",
)


def upgrade() -> None:
    op.create_table(
        "cache_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("binding_id", sa.Uuid()),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("capacity_class", sa.String(length=16), nullable=False),
        sa.Column("account_key", sa.String(length=128), nullable=False),
        sa.Column("cache_root_cid", sa.String(length=64), nullable=False),
        sa.Column("task_dir_cid", sa.String(length=64)),
        sa.Column("task_dir_name", sa.String(length=128), nullable=False),
        sa.Column("remote_info_hash", sa.String(length=128)),
        sa.Column("remote_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("claim_owner", sa.String(length=128)),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(length=128)),
        sa.Column("failure_detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'submitting', 'offlining', 'resolving', "
            "'awaiting_selection', 'ready', 'cancelling', 'cleaning', "
            "'cleanup_failed', 'failed', 'cleaned', 'detached')",
            name="ck_cache_job_status",
        ),
        sa.CheckConstraint(
            "capacity_class IN ('queued', 'running', 'ready', 'released')",
            name="ck_cache_job_capacity_class",
        ),
        sa.CheckConstraint(
            "(status = 'queued' AND capacity_class = 'queued') OR "
            "(status IN ('submitting', 'offlining', 'resolving') "
            "AND capacity_class = 'running') OR "
            "(status IN ('awaiting_selection', 'ready', 'cleaning', "
            "'cleanup_failed') AND capacity_class = 'ready') OR "
            "(status = 'cancelling' AND capacity_class IN "
            "('queued', 'running', 'ready')) OR "
            "(status IN ('failed', 'cleaned', 'detached') "
            "AND capacity_class = 'released')",
            name="ck_cache_job_state_capacity",
        ),
        sa.CheckConstraint(
            "binding_id IS NOT NULL OR status IN ('failed', 'cleaned', 'detached')",
            name="ck_cache_job_active_binding",
        ),
        sa.CheckConstraint(
            "remote_percent >= 0 AND remote_percent <= 100",
            name="ck_cache_job_remote_percent",
        ),
        sa.CheckConstraint(
            "length(account_key) BETWEEN 1 AND 128",
            name="ck_cache_job_account_key",
        ),
        sa.CheckConstraint(
            "length(cache_root_cid) BETWEEN 1 AND 64",
            name="ck_cache_job_root_cid",
        ),
        sa.CheckConstraint(
            "length(task_dir_name) BETWEEN 1 AND 128",
            name="ck_cache_job_task_dir_name",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"], ["movie.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["resource_source.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["cloud115_binding.id"],
            name="fk_cache_job_binding_id_cloud115_binding",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    active = ", ".join(f"'{status}'" for status in _ACTIVE_STATUSES)
    op.create_index(
        "uq_cache_job_active_source_binding",
        "cache_job",
        ["source_id", "binding_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({active})"),
    )
    op.create_index(
        "uq_cache_job_task_dir_cid",
        "cache_job",
        ["task_dir_cid"],
        unique=True,
        postgresql_where=sa.text("task_dir_cid IS NOT NULL"),
    )
    op.create_index(
        "ix_cache_job_status_created",
        "cache_job",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_cache_job_capacity_created",
        "cache_job",
        ["capacity_class", "created_at"],
    )
    op.create_table(
        "cache_play_request",
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("cache_job_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 16 AND 128",
            name="ck_cache_play_request_idempotency_key_length",
        ),
        sa.CheckConstraint(
            "idempotency_key ~ '^[A-Za-z0-9._~-]{16,128}$'",
            name="ck_cache_play_request_idempotency_key",
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"], ["movie.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["resource_source.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["cache_job_id"], ["cache_job.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("cache_play_request")
    op.drop_index("ix_cache_job_capacity_created", table_name="cache_job")
    op.drop_index("ix_cache_job_status_created", table_name="cache_job")
    op.drop_index("uq_cache_job_task_dir_cid", table_name="cache_job")
    op.drop_index("uq_cache_job_active_source_binding", table_name="cache_job")
    op.drop_table("cache_job")
