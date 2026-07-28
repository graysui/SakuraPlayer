"""Add deterministic cache lifecycle, cleanup, and lease schema.

Revision ID: 0018_cache_lifecycle
Revises: 0017_cache_media
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_cache_lifecycle"
down_revision = "0017_cache_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE cache_job
        SET ready_at = COALESCE(ready_at, updated_at, created_at),
            last_accessed_at = COALESCE(last_accessed_at, ready_at, updated_at, created_at),
            expires_at = COALESCE(
              expires_at,
              COALESCE(last_accessed_at, ready_at, updated_at, created_at)
                + INTERVAL '24 hours'
            )
        WHERE status IN ('awaiting_selection', 'ready')
        """
    )
    op.create_check_constraint(
        "ck_cache_job_materialized_timestamps",
        "cache_job",
        "status NOT IN ('awaiting_selection', 'ready') OR "
        "(ready_at IS NOT NULL AND last_accessed_at IS NOT NULL "
        "AND expires_at IS NOT NULL AND expires_at > last_accessed_at)",
    )
    op.create_index(
        "ix_cache_job_lifecycle_lru",
        "cache_job",
        ["status", "last_accessed_at", "ready_at", "created_at", "id"],
    )
    op.create_table(
        "cache_cleanup_attempt",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cache_job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column(
            "ownership_evidence",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failure_code", sa.String(length=128)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("attempt_no >= 1", name="ck_cache_cleanup_attempt_no"),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'detached')",
            name="ck_cache_cleanup_status",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL "
            "AND failure_code IS NULL) OR "
            "(status IN ('succeeded', 'detached') AND finished_at IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'failed' AND finished_at IS NOT NULL "
            "AND failure_code IS NOT NULL)",
            name="ck_cache_cleanup_result_shape",
        ),
        sa.ForeignKeyConstraint(
            ["cache_job_id"], ["cache_job.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cache_job_id", "attempt_no", name="uq_cache_cleanup_job_attempt"
        ),
    )
    op.create_index(
        "uq_cache_cleanup_running_job",
        "cache_cleanup_attempt",
        ["cache_job_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "playback_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=False),
        sa.Column("session_epoch", sa.BigInteger(), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("cache_job_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("session_epoch >= 0", name="ck_playback_session_epoch"),
        sa.CheckConstraint(
            "mode IN ('original', 'compatibility')", name="ck_playback_session_mode"
        ),
        sa.CheckConstraint(
            "platform IN ('windows', 'harmonyos')",
            name="ck_playback_session_platform",
        ),
        sa.CheckConstraint(
            "length(user_agent_hash) = 64",
            name="ck_playback_session_user_agent_hash",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at", name="ck_playback_session_expiry"
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["admin_user.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["movie_id"], ["movie.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["cache_job_id"], ["cache_job.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["cache_job_id", "media_id"],
            ["remote_media.cache_job_id", "remote_media.id"],
            name="fk_playback_session_owned_media",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_playback_session_cache_job", "playback_session", ["cache_job_id"]
    )
    op.create_table(
        "playback_lease",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("playback_session_id", sa.Uuid(), nullable=False),
        sa.Column("client_instance_id", sa.Uuid(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "expires_at > last_heartbeat_at", name="ck_playback_lease_expiry"
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= last_heartbeat_at",
            name="ck_playback_lease_end",
        ),
        sa.ForeignKeyConstraint(
            ["playback_session_id"],
            ["playback_session.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "playback_session_id",
            "client_instance_id",
            name="uq_playback_lease_session_client",
        ),
    )
    op.create_index(
        "ix_playback_lease_active",
        "playback_lease",
        ["expires_at", "ended_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_playback_lease_active", table_name="playback_lease")
    op.drop_table("playback_lease")
    op.drop_index("ix_playback_session_cache_job", table_name="playback_session")
    op.drop_table("playback_session")
    op.drop_index("uq_cache_cleanup_running_job", table_name="cache_cleanup_attempt")
    op.drop_table("cache_cleanup_attempt")
    op.drop_index("ix_cache_job_lifecycle_lru", table_name="cache_job")
    op.drop_constraint(
        "ck_cache_job_materialized_timestamps", "cache_job", type_="check"
    )
