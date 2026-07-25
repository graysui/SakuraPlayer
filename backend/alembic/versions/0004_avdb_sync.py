"""Create AVdb synchronization persistence.

Revision ID: 0004_avdb_sync
Revises: 0003_encrypted_settings
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0004_avdb_sync"
down_revision: Union[str, Sequence[str], None] = "0003_encrypted_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "avdb_sync_request",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("claim_owner", sa.String(length=64), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column("sync_run_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "mode IN ('incremental_30d', 'full_reconcile')",
            name="ck_avdb_sync_request_mode",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_avdb_sync_request_attempts",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "mode",
            "scheduled_for",
            name="uq_avdb_sync_request_slot",
        ),
    )
    op.create_table(
        "avdb_sync_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("repository", sa.String(length=128), nullable=False),
        sa.Column("release_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "cursor",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("failure_detail", sa.Text(), nullable=True),
        sa.Column(
            "stats",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.CheckConstraint(
            "mode IN ('incremental_30d', 'full_reconcile')",
            name="ck_avdb_sync_run_mode",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_avdb_sync_run_status",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint(
            "attempt_count >= 1",
            name="ck_avdb_sync_run_attempts",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository",
            "release_id",
            "mode",
            name="uq_avdb_sync_run_release",
        ),
    )
    op.create_foreign_key(
        "fk_avdb_sync_request_run",
        "avdb_sync_request",
        "avdb_sync_run",
        ["sync_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_avdb_sync_request_claim",
        "avdb_sync_request",
        ["status", "scheduled_for"],
        unique=False,
    )
    op.create_table(
        "avdb_asset",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sync_run_id", sa.Uuid(), nullable=False),
        sa.Column("asset_name", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "manifest",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "length(sha256) = 64 AND lower(sha256) = sha256",
            name="ck_avdb_asset_digest_format",
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_avdb_asset_digest",
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_avdb_asset_byte_size"),
        sa.CheckConstraint(
            "status IN ('downloaded', 'verified', 'decrypted', 'imported', 'failed')",
            name="ck_avdb_asset_status",
        ),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["avdb_sync_run.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sync_run_id",
            "asset_name",
            name="uq_avdb_asset_run_name",
        ),
    )
    op.create_index(
        "ix_avdb_asset_sync_run_id",
        "avdb_asset",
        ["sync_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_avdb_asset_sync_run_id", table_name="avdb_asset")
    op.drop_table("avdb_asset")
    op.drop_index("ix_avdb_sync_request_claim", table_name="avdb_sync_request")
    op.drop_constraint(
        "fk_avdb_sync_request_run",
        "avdb_sync_request",
        type_="foreignkey",
    )
    op.drop_table("avdb_sync_run")
    op.drop_table("avdb_sync_request")
