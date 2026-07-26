"""Add provider snapshot queue, current snapshots, and GFriends URL assets.

Revision ID: 0009_provider_snapshots
Revises: 0008_catalog_metadata
Create Date: 2026-07-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_provider_snapshots"
down_revision: Union[str, Sequence[str], None] = "0008_catalog_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_snapshot_request",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("claim_owner", sa.String(length=128)),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(length=128)),
        sa.CheckConstraint(
            "status IN ('queued', 'claimed', 'completed', 'failed')",
            name="ck_provider_snapshot_request_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_provider_snapshot_request_attempt",
        ),
        sa.CheckConstraint(
            "(status = 'queued' AND claim_owner IS NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL AND completed_at IS NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'claimed' AND claim_owner IS NOT NULL "
            "AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL "
            "AND completed_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'completed' AND claim_owner IS NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL AND completed_at IS NOT NULL "
            "AND failure_code IS NULL) OR "
            "(status = 'failed' AND claim_owner IS NULL AND claim_token IS NULL "
            "AND claim_expires_at IS NULL AND completed_at IS NOT NULL "
            "AND failure_code IS NOT NULL)",
            name="ck_provider_snapshot_request_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scheduled_for",
            name="uq_provider_snapshot_request_slot",
        ),
    )
    _create_snapshot_table(
        "actor_mapping_snapshot",
        "actor_mapping",
        max_bytes=16 * 1024 * 1024,
        state_constraint="ck_actor_mapping_snapshot_state",
    )
    _create_snapshot_table(
        "gfriends_snapshot",
        "gfriends",
        max_bytes=32 * 1024 * 1024,
        state_constraint="ck_gfriends_snapshot_state",
    )
    op.create_table(
        "gfriends_actor_asset",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("asset_kind", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("match_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "asset_kind IN ('profile', 'gallery')",
            name="ck_gfriends_actor_asset_kind",
        ),
        sa.CheckConstraint(
            "(asset_kind = 'profile' AND position = 0) OR "
            "(asset_kind = 'gallery' AND position >= 1)",
            name="ck_gfriends_actor_asset_position",
        ),
        sa.CheckConstraint(
            "match_name <> ''",
            name="ck_gfriends_actor_asset_match_name",
        ),
        sa.CheckConstraint(
            "url LIKE 'https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/%'",
            name="ck_gfriends_actor_asset_url",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["actor.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["gfriends_snapshot.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "actor_id",
            "asset_kind",
            "position",
            name="uq_gfriends_actor_asset_owner_position",
        ),
        sa.UniqueConstraint("url", name="uq_gfriends_actor_asset_url"),
    )


def downgrade() -> None:
    op.drop_table("gfriends_actor_asset")
    op.drop_index(
        "uq_gfriends_snapshot_current",
        table_name="gfriends_snapshot",
    )
    op.drop_table("gfriends_snapshot")
    op.drop_index(
        "uq_actor_mapping_snapshot_current",
        table_name="actor_mapping_snapshot",
    )
    op.drop_table("actor_mapping_snapshot")
    op.drop_table("provider_snapshot_request")


def _create_snapshot_table(
    table_name: str,
    constraint_prefix: str,
    *,
    max_bytes: int,
    state_constraint: str,
) -> None:
    op.create_table(
        table_name,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('current', 'superseded')",
            name=state_constraint,
        ),
        sa.CheckConstraint(
            f"byte_size > 0 AND byte_size <= {max_bytes}",
            name=f"ck_{constraint_prefix}_snapshot_size",
        ),
        sa.CheckConstraint(
            "length(sha256) = 64 AND lower(sha256) = sha256",
            name=f"ck_{constraint_prefix}_snapshot_sha256",
        ),
        sa.CheckConstraint(
            "relative_path <> '' AND relative_path NOT LIKE '/%' "
            "AND relative_path NOT LIKE '%..%'",
            name=f"ck_{constraint_prefix}_snapshot_path",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sha256",
            name=f"uq_{constraint_prefix}_snapshot_sha256",
        ),
    )
    op.create_index(
        f"uq_{constraint_prefix}_snapshot_current",
        table_name,
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'current'"),
    )
