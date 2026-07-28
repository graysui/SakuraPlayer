"""Add cache event recovery fields and persistent notifications.

Revision ID: 0020_cache_events_notifications
Revises: 0019_playback_progress
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0020_cache_events_notifications"
down_revision: Union[str, Sequence[str], None] = "0019_playback_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cache_job", sa.Column("failure_stage", sa.String(length=32)))
    op.add_column("cache_job", sa.Column("cleanup_reason", sa.String(length=16)))
    op.create_check_constraint(
        "ck_cache_job_failure_stage",
        "cache_job",
        "failure_stage IS NULL OR length(failure_stage) BETWEEN 1 AND 32",
    )
    op.create_check_constraint(
        "ck_cache_job_cleanup_reason",
        "cache_job",
        "cleanup_reason IS NULL OR cleanup_reason IN "
        "('cancelled', 'manual', 'ttl', 'capacity')",
    )
    op.execute(
        "UPDATE cache_job SET cleanup_reason = 'manual' "
        "WHERE status IN ('cleaning', 'cleanup_failed', 'cleaned') "
        "AND cleanup_reason IS NULL"
    )
    op.create_table(
        "notification",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "type IN ('cache_started', 'cache_ready', 'cache_failed', "
            "'credential_expired')",
            name="ck_notification_type",
        ),
        sa.CheckConstraint(
            "length(dedupe_key) BETWEEN 1 AND 255",
            name="ck_notification_dedupe_key",
        ),
        sa.CheckConstraint(
            "read_at IS NULL OR read_at >= created_at",
            name="ck_notification_read_at",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_dedupe_key"),
    )
    op.create_index(
        "ix_notification_unread",
        "notification",
        ["created_at", "id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notification_unread", table_name="notification")
    op.drop_table("notification")
    op.drop_constraint("ck_cache_job_cleanup_reason", "cache_job", type_="check")
    op.drop_constraint("ck_cache_job_failure_stage", "cache_job", type_="check")
    op.drop_column("cache_job", "cleanup_reason")
    op.drop_column("cache_job", "failure_stage")
