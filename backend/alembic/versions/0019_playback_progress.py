"""Add movie-level playback progress.

Revision ID: 0019_playback_progress
Revises: 0018_cache_lifecycle
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0019_playback_progress"
down_revision: Union[str, Sequence[str], None] = "0018_cache_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "movie_playback_state",
        sa.Column("movie_id", sa.Uuid(), nullable=False),
        sa.Column("position_seconds", sa.Numeric(12, 3), nullable=False),
        sa.Column("duration_seconds", sa.Numeric(12, 3)),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("last_watched_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "position_seconds >= 0 AND position_seconds <= 999999999.999",
            name="ck_movie_playback_position",
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR "
            "(duration_seconds > 0 AND duration_seconds <= 999999999.999)",
            name="ck_movie_playback_duration",
        ),
        sa.CheckConstraint(
            "NOT completed OR position_seconds = 0",
            name="ck_movie_playback_completed_position",
        ),
        sa.CheckConstraint("version >= 1", name="ck_movie_playback_version"),
        sa.ForeignKeyConstraint(
            ["movie_id"], ["movie.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("movie_id"),
    )


def downgrade() -> None:
    op.drop_table("movie_playback_state")
