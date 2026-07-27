"""Add the singleton encrypted Cloud115 binding.

Revision ID: 0014_cloud115_binding
Revises: 0013_events_settings_diagnostics
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_cloud115_binding"
down_revision: Union[str, Sequence[str], None] = "0013_events_settings_diagnostics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cloud115_binding",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("singleton_key", sa.Boolean(), nullable=False),
        sa.Column("account_key", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=128)),
        sa.Column("cookie_setting_key", sa.String(length=128), nullable=False),
        sa.Column("login_app", sa.String(length=32), nullable=False),
        sa.Column("cache_root_cid", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("credential_version", sa.BigInteger(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "singleton_key", name="ck_cloud115_binding_singleton_key"
        ),
        sa.CheckConstraint(
            "length(account_key) BETWEEN 1 AND 128",
            name="ck_cloud115_binding_account_key",
        ),
        sa.CheckConstraint(
            "cookie_setting_key = 'cloud115.cookie'",
            name="ck_cloud115_binding_cookie_key",
        ),
        sa.CheckConstraint(
            "login_app = 'alipaymini'",
            name="ck_cloud115_binding_login_app",
        ),
        sa.CheckConstraint(
            "length(cache_root_cid) BETWEEN 1 AND 64",
            name="ck_cloud115_binding_root_cid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'unavailable', 'detached')",
            name="ck_cloud115_binding_status",
        ),
        sa.CheckConstraint(
            "credential_version >= 1",
            name="ck_cloud115_binding_credential_version",
        ),
        sa.ForeignKeyConstraint(
            ["cookie_setting_key"],
            ["encrypted_setting.key"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "singleton_key", name="uq_cloud115_binding_singleton_key"
        ),
    )


def downgrade() -> None:
    op.drop_table("cloud115_binding")
