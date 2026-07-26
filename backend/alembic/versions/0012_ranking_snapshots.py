"""Add persistent ranking requests and immutable snapshots.

Revision ID: 0012_ranking_snapshots
Revises: 0011_catalog_discovery
Create Date: 2026-07-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_ranking_snapshots"
down_revision: Union[str, Sequence[str], None] = "0011_catalog_discovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SCOPE_CHECK = (
    "(board = 'top250' AND (year IS NULL OR year BETWEEN 2008 AND 2200)) OR "
    "(board IN ('daily', 'weekly', 'monthly') AND year IS NULL)"
)


def upgrade() -> None:
    op.create_table(
        "ranking_snapshot",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("board", sa.String(length=16), nullable=False),
        sa.Column("year", sa.SmallInteger()),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_SCOPE_CHECK, name="ck_ranking_snapshot_scope"),
        sa.CheckConstraint(
            "status IN ('building', 'current', 'superseded')",
            name="ck_ranking_snapshot_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ranking_snapshot_current_scope",
        "ranking_snapshot",
        ["board", sa.text("COALESCE(year, 0)")],
        unique=True,
        postgresql_where=sa.text("status = 'current'"),
    )
    op.create_index(
        "ix_ranking_snapshot_scope_created",
        "ranking_snapshot",
        ["board", "year", "created_at", "id"],
    )
    op.create_table(
        "ranking_sync_request",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("board", sa.String(length=16), nullable=False),
        sa.Column("year", sa.SmallInteger()),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("claim_owner", sa.String(length=128)),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(length=128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_SCOPE_CHECK, name="ck_ranking_request_scope"),
        sa.CheckConstraint(
            "status IN ('queued', 'claimed', 'completed', 'failed')",
            name="ck_ranking_request_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_ranking_request_attempt",
        ),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["ranking_snapshot.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_ranking_request_slot",
        "ranking_sync_request",
        ["board", sa.text("COALESCE(year, 0)"), "scheduled_for"],
        unique=True,
    )
    op.create_index(
        "uq_ranking_request_active_scope",
        "ranking_sync_request",
        ["board", sa.text("COALESCE(year, 0)")],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'claimed')"),
    )
    op.create_index(
        "ix_ranking_request_claim",
        "ranking_sync_request",
        ["status", "scheduled_for", "id"],
    )
    op.create_table(
        "ranking_entry",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("normalized_number", sa.String(length=128), nullable=False),
        sa.Column("movie_id", sa.Uuid()),
        sa.CheckConstraint("rank > 0", name="ck_ranking_entry_rank"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["ranking_snapshot.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["movie_id"], ["movie.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("snapshot_id", "rank"),
        sa.UniqueConstraint(
            "snapshot_id",
            "normalized_number",
            name="uq_ranking_entry_number",
        ),
    )
    op.create_index(
        "ix_ranking_entry_movie_id",
        "ranking_entry",
        ["movie_id"],
    )
    op.create_index(
        "ix_ranking_entry_snapshot_rank",
        "ranking_entry",
        ["snapshot_id", "rank"],
    )


def downgrade() -> None:
    op.drop_index("ix_ranking_entry_snapshot_rank", table_name="ranking_entry")
    op.drop_index("ix_ranking_entry_movie_id", table_name="ranking_entry")
    op.drop_table("ranking_entry")
    op.drop_index("ix_ranking_request_claim", table_name="ranking_sync_request")
    op.drop_index(
        "uq_ranking_request_active_scope",
        table_name="ranking_sync_request",
    )
    op.drop_index("uq_ranking_request_slot", table_name="ranking_sync_request")
    op.drop_table("ranking_sync_request")
    op.drop_index(
        "ix_ranking_snapshot_scope_created",
        table_name="ranking_snapshot",
    )
    op.drop_index(
        "uq_ranking_snapshot_current_scope",
        table_name="ranking_snapshot",
    )
    op.drop_table("ranking_snapshot")
