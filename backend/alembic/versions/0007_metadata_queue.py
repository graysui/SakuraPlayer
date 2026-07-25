"""Create the persistent metadata job queue and stage records.

Revision ID: 0007_metadata_queue
Revises: 0006_movie_source_management
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007_metadata_queue"
down_revision: Union[str, Sequence[str], None] = "0006_movie_source_management"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metadata_queue_state",
        sa.Column("singleton_key", sa.Boolean(), nullable=False),
        sa.Column("initial_as_of", sa.Date(), nullable=False),
        sa.Column("initial_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "singleton_key",
            name="ck_metadata_queue_state_singleton",
        ),
        sa.PrimaryKeyConstraint("singleton_key"),
    )
    op.create_table(
        "metadata_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_number", sa.String(length=128), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("sort_date", sa.Date(), nullable=True),
        sa.Column("retry_mode", sa.String(length=32), nullable=False),
        sa.Column(
            "requested_stages",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_no", sa.BigInteger(), nullable=False),
        sa.Column("parent_job_id", sa.Uuid(), nullable=True),
        sa.Column("claim_owner", sa.String(length=128), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_ms", sa.BigInteger(), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(reason = 'manual_or_search' AND priority = 10) OR "
            "(reason = 'ranking' AND priority = 20) OR "
            "(reason = 'daily' AND priority = 30) OR "
            "(reason = 'initial' AND priority = 40) OR "
            "(reason = 'history' AND priority = 50)",
            name="ck_metadata_job_priority_reason",
        ),
        sa.CheckConstraint(
            "(retry_mode = 'full' AND requested_stages = '[]'::jsonb) OR "
            "(retry_mode = 'missing_enrichment' "
            "AND jsonb_typeof(requested_stages) = 'array' "
            "AND jsonb_array_length(requested_stages) > 0 "
            "AND requested_stages <@ "
            "'[\"images\",\"dmm\",\"actor_map\",\"gfriends\",\"translation\"]'::jsonb "
            "AND NOT requested_stages ? 'javdb_core')",
            name="ck_metadata_job_retry_shape",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', "
            "'completed_with_warnings', 'failed')",
            name="ck_metadata_job_status",
        ),
        sa.CheckConstraint("attempt_no >= 1", name="ck_metadata_job_attempt_no"),
        sa.CheckConstraint(
            "elapsed_ms IS NULL OR elapsed_ms >= 0",
            name="ck_metadata_job_elapsed",
        ),
        sa.CheckConstraint(
            "(status = 'queued' AND claim_owner IS NULL "
            "AND claim_expires_at IS NULL AND started_at IS NULL "
            "AND finished_at IS NULL AND elapsed_ms IS NULL "
            "AND failure_code IS NULL AND failure_detail IS NULL) OR "
            "(status = 'running' AND claim_owner IS NOT NULL "
            "AND claim_expires_at IS NOT NULL AND started_at IS NOT NULL "
            "AND finished_at IS NULL AND elapsed_ms IS NULL "
            "AND failure_code IS NULL AND failure_detail IS NULL) OR "
            "(status IN ('completed', 'completed_with_warnings') "
            "AND claim_owner IS NULL AND claim_expires_at IS NULL "
            "AND started_at IS NOT NULL AND finished_at IS NOT NULL "
            "AND elapsed_ms IS NOT NULL AND failure_code IS NULL "
            "AND failure_detail IS NULL) OR "
            "(status = 'failed' AND claim_owner IS NULL "
            "AND claim_expires_at IS NULL AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL AND elapsed_ms IS NOT NULL "
            "AND failure_code IS NOT NULL AND failure_detail IS NOT NULL)",
            name="ck_metadata_job_state",
        ),
        sa.ForeignKeyConstraint(["movie_id"], ["movie.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["parent_job_id"],
            ["metadata_job.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_number",
            "attempt_no",
            name="uq_metadata_job_number_attempt",
        ),
    )
    op.create_index(
        "uq_metadata_job_active_number",
        "metadata_job",
        ["normalized_number"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_metadata_job_claim",
        "metadata_job",
        [
            "status",
            "priority",
            sa.text("sort_date DESC NULLS LAST"),
            "created_at",
            "id",
        ],
        unique=False,
    )
    op.create_index(
        "ix_metadata_job_movie_id",
        "metadata_job",
        ["movie_id"],
        unique=False,
    )
    op.create_table(
        "metadata_stage",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "stage IN ('javdb_core', 'images', 'dmm', 'actor_map', "
            "'gfriends', 'translation')",
            name="ck_metadata_stage_name",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'warning', "
            "'failed', 'skipped')",
            name="ck_metadata_stage_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND started_at IS NULL "
            "AND finished_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL "
            "AND finished_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'succeeded' AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status IN ('warning', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL AND failure_code IS NOT NULL) OR "
            "(status = 'skipped' AND started_at IS NULL "
            "AND finished_at IS NULL AND failure_code IS NULL)",
            name="ck_metadata_stage_state",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["metadata_job.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", "stage"),
    )
    op.execute(
        """
        CREATE FUNCTION guard_metadata_job_terminal_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.status IN ('completed', 'completed_with_warnings', 'failed')
             AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'terminal metadata job is immutable'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER trg_metadata_job_terminal_immutable
        BEFORE UPDATE ON metadata_job
        FOR EACH ROW EXECUTE FUNCTION guard_metadata_job_terminal_immutable();
        CREATE FUNCTION guard_metadata_stage_terminal_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.status IN ('succeeded', 'warning', 'failed', 'skipped')
             AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'terminal metadata stage is immutable'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER trg_metadata_stage_terminal_immutable
        BEFORE UPDATE ON metadata_stage
        FOR EACH ROW EXECUTE FUNCTION guard_metadata_stage_terminal_immutable();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER trg_metadata_stage_terminal_immutable ON metadata_stage;
        DROP FUNCTION guard_metadata_stage_terminal_immutable();
        DROP TRIGGER trg_metadata_job_terminal_immutable ON metadata_job;
        DROP FUNCTION guard_metadata_job_terminal_immutable();
        """
    )
    op.drop_table("metadata_stage")
    op.drop_index("ix_metadata_job_movie_id", table_name="metadata_job")
    op.drop_index("ix_metadata_job_claim", table_name="metadata_job")
    op.drop_index("uq_metadata_job_active_number", table_name="metadata_job")
    op.drop_table("metadata_job")
    op.drop_table("metadata_queue_state")
