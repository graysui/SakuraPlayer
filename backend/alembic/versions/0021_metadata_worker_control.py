"""Add persistent metadata worker claim control.

Revision ID: 0021_metadata_worker_control
Revises: 0020_cache_events_notifications
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0021_metadata_worker_control"
down_revision: Union[str, Sequence[str], None] = "0020_cache_events_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metadata_worker_control",
        sa.Column("singleton_key", sa.Boolean(), nullable=False),
        sa.Column(
            "paused",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "singleton_key",
            name="ck_metadata_worker_control_singleton",
        ),
        sa.PrimaryKeyConstraint("singleton_key"),
    )


def downgrade() -> None:
    op.drop_table("metadata_worker_control")
