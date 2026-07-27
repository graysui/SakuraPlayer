"""Add deterministic cache media resolution schema.

Revision ID: 0017_cache_media
Revises: 0016_cache_offline
Create Date: 2026-07-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_cache_media"
down_revision: Union[str, Sequence[str], None] = "0016_cache_offline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "remote_media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cache_job_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.String(length=64), nullable=False),
        sa.Column("pickcode", sa.String(length=128), nullable=False),
        sa.Column("parent_cid", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_seconds", sa.BigInteger()),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("selection_score", sa.Integer(), nullable=False),
        sa.Column(
            "selection_evidence",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
        ),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(file_id) BETWEEN 1 AND 64", name="ck_remote_media_file_id"
        ),
        sa.CheckConstraint(
            "length(pickcode) BETWEEN 1 AND 128", name="ck_remote_media_pickcode"
        ),
        sa.CheckConstraint(
            "length(parent_cid) BETWEEN 1 AND 64", name="ck_remote_media_parent_cid"
        ),
        sa.CheckConstraint("length(name) >= 1", name="ck_remote_media_name"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_remote_media_size"),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0",
            name="ck_remote_media_duration",
        ),
        sa.CheckConstraint("sequence_no >= 0", name="ck_remote_media_sequence"),
        sa.CheckConstraint("selection_score >= 0", name="ck_remote_media_score"),
        sa.ForeignKeyConstraint(
            ["cache_job_id"], ["cache_job.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cache_job_id", "file_id", name="uq_remote_media_job_file"
        ),
        sa.UniqueConstraint("cache_job_id", "id", name="uq_remote_media_job_id"),
        sa.UniqueConstraint(
            "cache_job_id",
            "candidate_id",
            "sequence_no",
            name="uq_remote_media_candidate_sequence",
        ),
    )
    op.create_table(
        "remote_subtitle",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cache_job_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid()),
        sa.Column("file_id", sa.String(length=64), nullable=False),
        sa.Column("pickcode", sa.String(length=128), nullable=False),
        sa.Column("parent_cid", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("extension", sa.String(length=8), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column(
            "match_evidence",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "extension IN ('srt', 'ass', 'ssa', 'vtt')",
            name="ck_remote_subtitle_extension",
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 8388608", name="ck_remote_subtitle_size"
        ),
        sa.CheckConstraint("match_score >= 0", name="ck_remote_subtitle_score"),
        sa.ForeignKeyConstraint(
            ["cache_job_id"], ["cache_job.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["cache_job_id", "media_id"],
            ["remote_media.cache_job_id", "remote_media.id"],
            name="fk_remote_subtitle_owned_media",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cache_job_id", "file_id", name="uq_remote_subtitle_job_file"
        ),
    )
    op.create_table(
        "cache_job_media_selection",
        sa.Column("cache_job_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "sequence_no >= 0", name="ck_cache_selection_sequence"
        ),
        sa.ForeignKeyConstraint(
            ["cache_job_id"], ["cache_job.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["cache_job_id", "media_id"],
            ["remote_media.cache_job_id", "remote_media.id"],
            name="fk_cache_selection_owned_media",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cache_job_id", "sequence_no"),
        sa.UniqueConstraint(
            "cache_job_id", "media_id", name="uq_cache_selection_job_media"
        ),
    )
    op.execute(
        """
        CREATE FUNCTION enforce_cache_job_ready_selection() RETURNS trigger AS $$
        BEGIN
          IF NEW.status = 'ready' AND NOT EXISTS (
            SELECT 1 FROM cache_job_media_selection
            WHERE cache_job_id = NEW.id
          ) THEN
            RAISE EXCEPTION 'ready cache job requires selected media'
              USING ERRCODE = '23514', CONSTRAINT = 'ck_cache_job_ready_selection';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_cache_job_ready_selection
        AFTER INSERT OR UPDATE ON cache_job
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_cache_job_ready_selection()
        """
    )
    op.execute(
        """
        CREATE FUNCTION enforce_cache_selection_delete() RETURNS trigger AS $$
        DECLARE target_job_id uuid;
        BEGIN
          target_job_id := OLD.cache_job_id;
          IF EXISTS (
            SELECT 1 FROM cache_job
            WHERE id = target_job_id AND status = 'ready'
          ) AND NOT EXISTS (
            SELECT 1 FROM cache_job_media_selection
            WHERE cache_job_id = target_job_id
          ) THEN
            RAISE EXCEPTION 'ready cache job requires selected media'
              USING ERRCODE = '23514', CONSTRAINT = 'ck_cache_job_ready_selection';
          END IF;
          RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_cache_selection_ready_guard
        AFTER DELETE OR UPDATE ON cache_job_media_selection
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_cache_selection_delete()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_cache_selection_ready_guard ON cache_job_media_selection"
    )
    op.execute("DROP FUNCTION enforce_cache_selection_delete()")
    op.execute("DROP TRIGGER trg_cache_job_ready_selection ON cache_job")
    op.execute("DROP FUNCTION enforce_cache_job_ready_selection()")
    op.drop_table("cache_job_media_selection")
    op.drop_table("remote_subtitle")
    op.drop_table("remote_media")
