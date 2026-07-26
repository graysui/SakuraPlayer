"""Add paid translation dispatch and result facts.

Revision ID: 0010_translation
Revises: 0009_provider_snapshots
Create Date: 2026-07-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_translation"
down_revision: Union[str, Sequence[str], None] = "0009_provider_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("actor", sa.Column("bio_zh_source", sa.String(length=16)))
    op.execute(
        "UPDATE actor SET bio_zh_source = 'actor_mapping' "
        "WHERE bio_zh IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_actor_bio_zh_source",
        "actor",
        "(bio_zh IS NULL AND bio_zh_source IS NULL) OR "
        "(bio_zh IS NOT NULL AND bio_zh_source IN ('actor_mapping', 'ai'))",
    )
    op.create_table(
        "translation_record",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("translated_text", sa.Text()),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True)),
        sa.Column("dispatch_started_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(length=128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "owner_type IN ('movie_title', 'movie_description', 'actor_bio')",
            name="ck_translation_record_owner_type",
        ),
        sa.CheckConstraint(
            "length(source_text) BETWEEN 1 AND 32000",
            name="ck_translation_record_source_text",
        ),
        sa.CheckConstraint(
            "length(source_hash) = 64 AND lower(source_hash) = source_hash",
            name="ck_translation_record_source_hash",
        ),
        sa.CheckConstraint(
            "source_hash ~ '^[0-9a-f]{64}$'",
            name="ck_translation_record_source_hash_format",
        ),
        sa.CheckConstraint(
            "length(model) BETWEEN 1 AND 255",
            name="ck_translation_record_model",
        ),
        sa.CheckConstraint(
            "length(prompt_version) BETWEEN 1 AND 64",
            name="ck_translation_record_prompt_version",
        ),
        sa.CheckConstraint(
            "translated_text IS NULL OR length(translated_text) BETWEEN 1 AND 32000",
            name="ck_translation_record_translated_text",
        ),
        sa.CheckConstraint(
            "status IN ('reserved', 'dispatched', 'completed', 'rejected', 'unknown')",
            name="ck_translation_record_status",
        ),
        sa.CheckConstraint(
            "(status = 'reserved' AND translated_text IS NULL "
            "AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL "
            "AND dispatch_started_at IS NULL AND failure_code IS NULL) OR "
            "(status = 'dispatched' AND translated_text IS NULL "
            "AND claim_token IS NOT NULL AND claim_expires_at IS NULL "
            "AND dispatch_started_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status = 'completed' AND translated_text IS NOT NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL "
            "AND dispatch_started_at IS NOT NULL AND failure_code IS NULL) OR "
            "(status IN ('rejected', 'unknown') AND translated_text IS NULL "
            "AND claim_token IS NULL AND claim_expires_at IS NULL "
            "AND dispatch_started_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="ck_translation_record_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_type",
            "owner_id",
            "source_hash",
            "model",
            "prompt_version",
            name="uq_translation_record_business_key",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION guard_translation_record_dispatch_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.owner_type IS DISTINCT FROM OLD.owner_type
             OR NEW.owner_id IS DISTINCT FROM OLD.owner_id
             OR NEW.source_text IS DISTINCT FROM OLD.source_text
             OR NEW.source_hash IS DISTINCT FROM OLD.source_hash
             OR NEW.model IS DISTINCT FROM OLD.model
             OR NEW.prompt_version IS DISTINCT FROM OLD.prompt_version
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'translation business key is immutable'
              USING ERRCODE = '23514';
          END IF;
          IF OLD.status IN ('completed', 'rejected', 'unknown')
             AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'terminal translation record is immutable'
              USING ERRCODE = '23514';
          END IF;
          IF OLD.status = 'dispatched'
             AND NEW.status NOT IN ('completed', 'rejected', 'unknown') THEN
            RAISE EXCEPTION 'dispatched translation cannot be reserved again'
              USING ERRCODE = '23514';
          END IF;
          IF OLD.status = 'dispatched' AND NEW.status = 'dispatched'
             AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'dispatched translation is immutable while in flight'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$;
        CREATE TRIGGER trg_translation_record_dispatch_immutable
        BEFORE UPDATE ON translation_record
        FOR EACH ROW EXECUTE FUNCTION guard_translation_record_dispatch_immutable();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER trg_translation_record_dispatch_immutable
          ON translation_record;
        DROP FUNCTION guard_translation_record_dispatch_immutable();
        """
    )
    op.drop_table("translation_record")
    op.drop_constraint("ck_actor_bio_zh_source", "actor", type_="check")
    op.drop_column("actor", "bio_zh_source")
