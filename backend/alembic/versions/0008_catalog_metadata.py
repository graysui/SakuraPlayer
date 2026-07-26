"""Add JavDB core catalog metadata and permanent image facts.

Revision ID: 0008_catalog_metadata
Revises: 0007_metadata_queue
Create Date: 2026-07-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_catalog_metadata"
down_revision: Union[str, Sequence[str], None] = "0007_metadata_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("movie", sa.Column("javdb_id", sa.String(length=128)))
    op.add_column("movie", sa.Column("title_original", sa.Text()))
    op.add_column("movie", sa.Column("title_zh", sa.Text()))
    op.add_column("movie", sa.Column("release_date", sa.Date()))
    op.add_column("movie", sa.Column("maker", sa.String(length=255)))
    op.add_column("movie", sa.Column("series", sa.String(length=255)))
    op.add_column("movie", sa.Column("director", sa.String(length=255)))
    op.add_column("movie", sa.Column("description_original", sa.Text()))
    op.add_column("movie", sa.Column("description_zh", sa.Text()))
    op.add_column("movie", sa.Column("score", sa.Numeric(precision=5, scale=2)))
    op.add_column(
        "movie",
        sa.Column("metadata_updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "uq_movie_javdb_id",
        "movie",
        ["javdb_id"],
        unique=True,
        postgresql_where=sa.text("javdb_id IS NOT NULL"),
    )

    op.create_table(
        "actor",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("javdb_id", sa.String(length=128), nullable=False),
        sa.Column("name_ja", sa.String(length=255)),
        sa.Column("name_zh", sa.String(length=255)),
        sa.Column("bio_original", sa.Text()),
        sa.Column("bio_zh", sa.Text()),
        sa.Column("gender", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "gender IN ('female', 'male', 'unknown')",
            name="ck_actor_gender",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("javdb_id", name="uq_actor_javdb_id"),
    )
    op.create_table(
        "tag",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_tag_name"),
    )
    op.create_table(
        "actor_alias",
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("authority", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "authority IN ('javdb', 'actor_mapping')",
            name="ck_actor_alias_authority",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["actor.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("actor_id", "normalized_alias"),
    )
    op.create_index(
        "ix_actor_alias_normalized",
        "actor_alias",
        ["normalized_alias"],
    )
    op.create_table(
        "movie_actor",
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_movie_actor_position"),
        sa.ForeignKeyConstraint(["actor_id"], ["actor.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["movie_id"], ["movie.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("movie_id", "actor_id"),
        sa.UniqueConstraint(
            "movie_id",
            "position",
            name="uq_movie_actor_position",
        ),
    )
    op.create_table(
        "movie_tag",
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movie.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("movie_id", "tag_id"),
    )
    op.create_table(
        "catalog_image",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_type", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64)),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "owner_type IN ('movie', 'actor')",
            name="ck_catalog_image_owner_type",
        ),
        sa.CheckConstraint(
            "kind IN ('cover', 'plot', 'profile', 'placeholder')",
            name="ck_catalog_image_kind",
        ),
        sa.CheckConstraint("position >= 0", name="ck_catalog_image_position"),
        sa.CheckConstraint(
            "kind <> 'cover' OR position = 0",
            name="ck_catalog_image_cover_position",
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'placeholder', 'retry_pending')",
            name="ck_catalog_image_status",
        ),
        sa.CheckConstraint(
            "relative_path <> '' AND relative_path NOT LIKE '/%' "
            "AND relative_path NOT LIKE '%..%'",
            name="ck_catalog_image_relative_path",
        ),
        sa.CheckConstraint(
            "sha256 IS NULL OR (length(sha256) = 64 AND lower(sha256) = sha256)",
            name="ck_catalog_image_sha256",
        ),
        sa.CheckConstraint(
            "sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_catalog_image_sha256_format",
        ),
        sa.CheckConstraint(
            "(status = 'ready' AND source_url IS NOT NULL AND sha256 IS NOT NULL) OR "
            "(status = 'retry_pending' AND source_url IS NOT NULL) OR "
            "(status = 'placeholder' AND source_url IS NULL AND sha256 IS NOT NULL)",
            name="ck_catalog_image_ready_shape",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_type",
            "owner_id",
            "kind",
            "position",
            name="uq_catalog_image_owner_kind_position",
        ),
    )
    op.create_index(
        "ix_catalog_image_owner",
        "catalog_image",
        ["owner_type", "owner_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_image_owner", table_name="catalog_image")
    op.drop_table("catalog_image")
    op.drop_table("movie_tag")
    op.drop_table("movie_actor")
    op.drop_index("ix_actor_alias_normalized", table_name="actor_alias")
    op.drop_table("actor_alias")
    op.drop_table("tag")
    op.drop_table("actor")
    op.drop_index("uq_movie_javdb_id", table_name="movie")
    op.drop_column("movie", "metadata_updated_at")
    op.drop_column("movie", "score")
    op.drop_column("movie", "description_zh")
    op.drop_column("movie", "description_original")
    op.drop_column("movie", "director")
    op.drop_column("movie", "series")
    op.drop_column("movie", "maker")
    op.drop_column("movie", "release_date")
    op.drop_column("movie", "title_zh")
    op.drop_column("movie", "title_original")
    op.drop_column("movie", "javdb_id")
