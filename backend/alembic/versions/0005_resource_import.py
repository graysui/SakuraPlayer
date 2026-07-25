"""Create movie skeleton and AVdb resource source storage.

Revision ID: 0005_resource_import
Revises: 0004_avdb_sync
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0005_resource_import"
down_revision: Union[str, Sequence[str], None] = "0004_avdb_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "movie",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("normalized_number", sa.String(length=128), nullable=False),
        sa.Column(
            "raw_numbers",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
        ),
        sa.Column("catalog_state", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "catalog_state IN ('raw_only', 'metadata_queued', "
            "'metadata_running', 'core_ready')",
            name="ck_movie_catalog_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_number",
            name="uq_movie_normalized_number",
        ),
    )
    op.create_table(
        "resource_source",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("website", sa.String(length=32), nullable=False),
        sa.Column("external_post_id", sa.BigInteger(), nullable=False),
        sa.Column("movie_id", sa.Uuid(), nullable=True),
        sa.Column("raw_number", sa.String(length=128), nullable=True),
        sa.Column("normalized_number", sa.String(length=128), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publish_date", sa.Date(), nullable=True),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("resource_size_mb", sa.BigInteger(), nullable=True),
        sa.Column("detail_url", sa.Text(), nullable=True),
        sa.Column(
            "preview_urls",
            postgresql.JSONB(none_as_null=True),
            nullable=False,
        ),
        sa.Column("magnet_key_id", sa.String(length=64), nullable=True),
        sa.Column("magnet_nonce", sa.LargeBinary(length=12), nullable=True),
        sa.Column("magnet_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("identification_status", sa.String(length=16), nullable=False),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "website IN ('sehuatang', 'x1080x')",
            name="ck_resource_source_website",
        ),
        sa.CheckConstraint(
            "resource_size_mb IS NULL OR resource_size_mb >= 0",
            name="ck_resource_source_size",
        ),
        sa.CheckConstraint(
            "section IN "
            "('亚洲有码', '亚洲无码', '中文字幕', "
            "'4K原版', '素人有码', 'FC2')",
            name="ck_resource_source_section",
        ),
        sa.CheckConstraint(
            "identification_status IN "
            "('identified', 'pending', 'manual', 'rejected')",
            name="ck_resource_source_identification_status",
        ),
        sa.CheckConstraint(
            "(identification_status = 'pending' AND movie_id IS NULL "
            "AND normalized_number IS NULL) OR "
            "(identification_status IN ('identified', 'manual') "
            "AND movie_id IS NOT NULL AND normalized_number IS NOT NULL) OR "
            "(identification_status = 'rejected')",
            name="ck_resource_source_identification",
        ),
        sa.CheckConstraint(
            "(magnet_key_id IS NULL AND magnet_nonce IS NULL "
            "AND magnet_ciphertext IS NULL) OR "
            "(magnet_key_id IS NOT NULL AND magnet_nonce IS NOT NULL "
            "AND magnet_ciphertext IS NOT NULL)",
            name="ck_resource_source_magnet_shape",
        ),
        sa.CheckConstraint(
            "identification_status <> 'rejected' OR "
            "(magnet_key_id IS NULL AND magnet_nonce IS NULL "
            "AND magnet_ciphertext IS NULL)",
            name="ck_resource_source_rejected_secret",
        ),
        sa.CheckConstraint(
            "magnet_nonce IS NULL OR length(magnet_nonce) = 12",
            name="ck_resource_source_magnet_nonce",
        ),
        sa.CheckConstraint(
            "magnet_ciphertext IS NULL OR length(magnet_ciphertext) >= 16",
            name="ck_resource_source_magnet_ciphertext",
        ),
        sa.ForeignKeyConstraint(["movie_id"], ["movie.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "website",
            "external_post_id",
            name="uq_resource_source_external",
        ),
    )
    op.create_index(
        "ix_resource_source_movie_id",
        "resource_source",
        ["movie_id"],
        unique=False,
    )
    op.create_index(
        "ix_resource_source_number_publish_date",
        "resource_source",
        ["normalized_number", sa.text("publish_date DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resource_source_number_publish_date",
        table_name="resource_source",
    )
    op.drop_index("ix_resource_source_movie_id", table_name="resource_source")
    op.drop_table("resource_source")
    op.drop_table("movie")
