"""Create source labels and permanent rejection records.

Revision ID: 0006_movie_source_management
Revises: 0005_resource_import
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_movie_source_management"
down_revision: Union[str, Sequence[str], None] = "0005_resource_import"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_source_label",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=16), nullable=False),
        sa.Column("evidence", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "label IN ('subtitle', 'cracked', '4k', 'censored')",
            name="ck_resource_source_label_value",
        ),
        sa.CheckConstraint(
            "length(evidence) >= 1",
            name="ck_resource_source_label_evidence",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["resource_source.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_id", "label"),
    )
    op.create_table(
        "source_rejection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("website", sa.String(length=32), nullable=False),
        sa.Column("external_post_id", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_release_id", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "length(reason_code) >= 1",
            name="ck_source_rejection_reason_code",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "website",
            "external_post_id",
            name="uq_source_rejection_external",
        ),
    )
    op.execute(
        """
        INSERT INTO resource_source_label (source_id, label, evidence, created_at)
        SELECT source_id, label, evidence, CURRENT_TIMESTAMP
        FROM (
          SELECT id AS source_id, 'subtitle' AS label, 'section=中文字幕' AS evidence
          FROM resource_source WHERE section = '中文字幕'
          UNION ALL
          SELECT id, 'cracked', 'category=' || category
          FROM resource_source WHERE category LIKE '%无码破解%'
          UNION ALL
          SELECT id, 'cracked', 'title=无码破解'
          FROM resource_source
          WHERE (category NOT LIKE '%无码破解%' OR category IS NULL)
            AND title LIKE '%无码破解%'
          UNION ALL
          SELECT id, '4k', 'section=4K原版'
          FROM resource_source WHERE section = '4K原版'
          UNION ALL
          SELECT id, 'censored', 'category=' || category
          FROM resource_source WHERE category LIKE '%有码%'
        ) AS label_rows
        ON CONFLICT (source_id, label) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("source_rejection")
    op.drop_table("resource_source_label")
