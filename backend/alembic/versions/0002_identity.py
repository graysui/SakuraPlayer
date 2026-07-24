"""Create unique administrator and refresh sessions.

Revision ID: 0002_identity
Revises: 0001_initial_skeleton
Create Date: 2026-07-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_identity"
down_revision: Union[str, Sequence[str], None] = "0001_initial_skeleton"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("singleton_key", sa.Boolean(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("session_epoch", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("singleton_key", name="ck_admin_user_singleton_key"),
        sa.CheckConstraint(
            "char_length(username) >= 1",
            name="ck_admin_user_username_not_empty",
        ),
        sa.CheckConstraint(
            "password_hash LIKE '$argon2id$%'",
            name="ck_admin_user_password_argon2id",
        ),
        sa.CheckConstraint(
            "session_epoch >= 0",
            name="ck_admin_user_session_epoch",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton_key", name="uq_admin_user_singleton_key"),
        sa.UniqueConstraint("username", name="uq_admin_user_username"),
    )
    op.create_table(
        "refresh_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("admin_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("client_instance_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(token_hash) = 32",
            name="ck_refresh_session_token_hash_length",
        ),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["admin_user.id"],
            name="fk_refresh_session_admin_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_session_token_hash"),
    )
    op.create_index(
        "ix_refresh_session_admin_id",
        "refresh_session",
        ["admin_id"],
        unique=False,
    )
    op.create_index(
        "uq_refresh_session_active_client",
        "refresh_session",
        ["admin_id", "client_instance_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_refresh_session_active_client", table_name="refresh_session")
    op.drop_index("ix_refresh_session_admin_id", table_name="refresh_session")
    op.drop_table("refresh_session")
    op.drop_table("admin_user")
