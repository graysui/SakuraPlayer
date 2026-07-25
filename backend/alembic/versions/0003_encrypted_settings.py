"""Create encrypted settings storage.

Revision ID: 0003_encrypted_settings
Revises: 0002_identity
Create Date: 2026-07-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_encrypted_settings"
down_revision: Union[str, Sequence[str], None] = "0002_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "encrypted_setting",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column(
            "public_value",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
        ),
        sa.Column("key_id", sa.String(length=64), nullable=True),
        sa.Column("nonce", sa.LargeBinary(length=12), nullable=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(key) >= 1",
            name="ck_encrypted_setting_key_not_empty",
        ),
        sa.CheckConstraint(
            "(public_value IS NOT NULL AND key_id IS NULL "
            "AND nonce IS NULL AND ciphertext IS NULL) OR "
            "(public_value IS NULL AND key_id IS NOT NULL "
            "AND nonce IS NOT NULL AND ciphertext IS NOT NULL)",
            name="ck_encrypted_setting_value_shape",
        ),
        sa.CheckConstraint(
            "key_id IS NULL OR char_length(key_id) >= 1",
            name="ck_encrypted_setting_key_id_not_empty",
        ),
        sa.CheckConstraint(
            "nonce IS NULL OR length(nonce) = 12",
            name="ck_encrypted_setting_nonce_length",
        ),
        sa.CheckConstraint(
            "ciphertext IS NULL OR length(ciphertext) >= 16",
            name="ck_encrypted_setting_ciphertext_length",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_encrypted_setting_version",
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("encrypted_setting")
