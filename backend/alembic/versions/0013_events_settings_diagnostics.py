"""Add persistent domain events for settings and diagnostics.

Revision ID: 0013_events_settings_diagnostics
Revises: 0012_ranking_snapshots
Create Date: 2026-07-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0013_events_settings_diagnostics"
down_revision: Union[str, Sequence[str], None] = "0012_ranking_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connection_test_result",
        sa.Column("target", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=128)),
        sa.Column("elapsed_ms", sa.BigInteger(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target IN ('cloud115', 'javdb', 'dmm', 'gfriends', 'ai')",
            name="ck_connection_test_target",
        ),
        sa.CheckConstraint(
            "status IN ('available', 'unavailable', 'credentials_invalid', "
            "'not_configured')",
            name="ck_connection_test_status",
        ),
        sa.CheckConstraint("elapsed_ms >= 0", name="ck_connection_test_elapsed"),
        sa.PrimaryKeyConstraint("target"),
    )
    op.create_table(
        "event_sequence",
        sa.Column("singleton_key", sa.Boolean(), nullable=False),
        sa.Column("current_value", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("singleton_key", name="ck_event_sequence_singleton"),
        sa.CheckConstraint("current_value >= 0", name="ck_event_sequence_value"),
        sa.PrimaryKeyConstraint("singleton_key"),
    )
    op.bulk_insert(
        sa.table(
            "event_sequence",
            sa.column("singleton_key", sa.Boolean()),
            sa.column("current_value", sa.BigInteger()),
        ),
        [{"singleton_key": True, "current_value": 0}],
    )
    op.create_table(
        "event_stream_version",
        sa.Column("stream", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("current_version", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "stream IN ('metadata', 'cache', 'credential', 'catalog', "
            "'notification')",
            name="ck_event_stream_version_stream",
        ),
        sa.CheckConstraint(
            "current_version > 0", name="ck_event_stream_version_value"
        ),
        sa.PrimaryKeyConstraint("stream", "aggregate_id"),
    )
    op.create_table(
        "domain_event",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("stream", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("stream_version", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column(
            "payload",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence > 0", name="ck_domain_event_sequence"),
        sa.CheckConstraint(
            "stream IN ('metadata', 'cache', 'credential', 'catalog', "
            "'notification')",
            name="ck_domain_event_stream",
        ),
        sa.CheckConstraint(
            "stream_version > 0", name="ck_domain_event_stream_version"
        ),
        sa.CheckConstraint("length(event_type) >= 1", name="ck_domain_event_type"),
        sa.CheckConstraint(
            "expires_at > occurred_at", name="ck_domain_event_expiry"
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("sequence", name="uq_domain_event_sequence"),
        sa.UniqueConstraint(
            "stream",
            "aggregate_id",
            "stream_version",
            name="uq_domain_event_stream_version",
        ),
    )
    op.create_index(
        "ix_domain_event_delivery",
        "domain_event",
        ["sequence", "expires_at"],
    )
    op.create_index(
        "ix_domain_event_aggregate",
        "domain_event",
        ["stream", "aggregate_id", "stream_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_domain_event_aggregate", table_name="domain_event")
    op.drop_index("ix_domain_event_delivery", table_name="domain_event")
    op.drop_table("domain_event")
    op.drop_table("event_stream_version")
    op.drop_table("event_sequence")
    op.drop_table("connection_test_result")
