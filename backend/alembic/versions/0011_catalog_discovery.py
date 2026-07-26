"""Add deterministic catalog search and discovery favorites.

Revision ID: 0011_catalog_discovery
Revises: 0010_translation
Create Date: 2026-07-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_catalog_discovery"
down_revision: Union[str, Sequence[str], None] = "0010_translation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "favorite",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('movie', 'actor')",
            name="ck_favorite_target_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "target_type",
            "target_id",
            name="uq_favorite_target",
        ),
    )
    op.create_index(
        "ix_favorite_target_created",
        "favorite",
        ["target_type", "created_at", "target_id"],
    )
    _create_trigram_index("movie", "title_original")
    _create_trigram_index("movie", "title_zh")
    _create_trigram_index("actor", "name_ja")
    _create_trigram_index("actor", "name_zh")
    op.create_index(
        "ix_actor_alias_normalized_trgm",
        "actor_alias",
        ["normalized_alias"],
        postgresql_using="gin",
        postgresql_ops={"normalized_alias": "gin_trgm_ops"},
    )


def downgrade() -> None:
    for name in (
        "ix_actor_alias_normalized_trgm",
        "ix_actor_name_zh_trgm",
        "ix_actor_name_ja_trgm",
        "ix_movie_title_zh_trgm",
        "ix_movie_title_original_trgm",
    ):
        op.drop_index(name)
    op.drop_index("ix_favorite_target_created", table_name="favorite")
    op.drop_table("favorite")


def _create_trigram_index(table: str, column: str) -> None:
    op.create_index(
        f"ix_{table}_{column}_trgm",
        table,
        [column],
        postgresql_using="gin",
        postgresql_ops={column: "gin_trgm_ops"},
    )
