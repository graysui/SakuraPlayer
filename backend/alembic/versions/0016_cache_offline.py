"""Add deterministic offline dispatch and claim fencing.

Revision ID: 0016_cache_offline
Revises: 0015_cache_jobs
Create Date: 2026-07-27
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0016_cache_offline"
down_revision: Union[str, Sequence[str], None] = "0015_cache_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ACTIVE_STATUSES = (
    "queued",
    "submitting",
    "offlining",
    "submit_uncertain",
    "resolving",
    "awaiting_selection",
    "ready",
    "cancelling",
    "cleaning",
    "cleanup_failed",
)


def upgrade() -> None:
    op.add_column(
        "cache_job",
        sa.Column("submit_started_at", sa.DateTime(timezone=True)),
    )
    op.drop_index("uq_cache_job_active_source_binding", table_name="cache_job")
    op.drop_constraint("ck_cache_job_state_capacity", "cache_job", type_="check")
    op.drop_constraint("ck_cache_job_status", "cache_job", type_="check")
    op.create_check_constraint(
        "ck_cache_job_status",
        "cache_job",
        "status IN ('queued', 'submitting', 'offlining', 'submit_uncertain', "
        "'resolving', 'awaiting_selection', 'ready', 'cancelling', 'cleaning', "
        "'cleanup_failed', 'failed', 'cleaned', 'detached')",
    )
    op.create_check_constraint(
        "ck_cache_job_state_capacity",
        "cache_job",
        "(status = 'queued' AND capacity_class = 'queued') OR "
        "(status IN ('submitting', 'offlining', 'submit_uncertain', 'resolving') "
        "AND capacity_class = 'running') OR "
        "(status IN ('awaiting_selection', 'ready', 'cleaning', 'cleanup_failed') "
        "AND capacity_class = 'ready') OR "
        "(status = 'cancelling' AND capacity_class IN ('queued', 'running', 'ready')) OR "
        "(status IN ('failed', 'cleaned', 'detached') AND capacity_class = 'released')",
    )
    op.create_check_constraint(
        "ck_cache_job_claim_shape",
        "cache_job",
        "(claim_owner IS NULL AND claim_token IS NULL AND claim_expires_at IS NULL) OR "
        "(claim_owner IS NOT NULL AND claim_token IS NOT NULL "
        "AND claim_expires_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_cache_job_submission_shape",
        "cache_job",
        "(submit_started_at IS NULL OR task_dir_cid IS NOT NULL) AND "
        "(remote_info_hash IS NULL OR "
        "(task_dir_cid IS NOT NULL AND submit_started_at IS NOT NULL)) AND "
        "(status <> 'submit_uncertain' OR "
        "(task_dir_cid IS NOT NULL AND submit_started_at IS NOT NULL "
        "AND remote_info_hash IS NULL "
        "AND failure_code = 'cloud115_submit_uncertain'))",
    )
    active = ", ".join(f"'{status}'" for status in _ACTIVE_STATUSES)
    op.create_index(
        "uq_cache_job_active_source_binding",
        "cache_job",
        ["source_id", "binding_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({active})"),
    )


def downgrade() -> None:
    op.execute(
        "UPDATE cache_job SET status = 'failed', capacity_class = 'released', "
        "claim_owner = NULL, claim_token = NULL, claim_expires_at = NULL "
        "WHERE status = 'submit_uncertain'"
    )
    op.drop_index("uq_cache_job_active_source_binding", table_name="cache_job")
    op.drop_constraint("ck_cache_job_submission_shape", "cache_job", type_="check")
    op.drop_constraint("ck_cache_job_claim_shape", "cache_job", type_="check")
    op.drop_constraint("ck_cache_job_state_capacity", "cache_job", type_="check")
    op.drop_constraint("ck_cache_job_status", "cache_job", type_="check")
    op.create_check_constraint(
        "ck_cache_job_status",
        "cache_job",
        "status IN ('queued', 'submitting', 'offlining', 'resolving', "
        "'awaiting_selection', 'ready', 'cancelling', 'cleaning', "
        "'cleanup_failed', 'failed', 'cleaned', 'detached')",
    )
    op.create_check_constraint(
        "ck_cache_job_state_capacity",
        "cache_job",
        "(status = 'queued' AND capacity_class = 'queued') OR "
        "(status IN ('submitting', 'offlining', 'resolving') "
        "AND capacity_class = 'running') OR "
        "(status IN ('awaiting_selection', 'ready', 'cleaning', 'cleanup_failed') "
        "AND capacity_class = 'ready') OR "
        "(status = 'cancelling' AND capacity_class IN ('queued', 'running', 'ready')) OR "
        "(status IN ('failed', 'cleaned', 'detached') AND capacity_class = 'released')",
    )
    old_active = tuple(
        status for status in _ACTIVE_STATUSES if status != "submit_uncertain"
    )
    active = ", ".join(f"'{status}'" for status in old_active)
    op.create_index(
        "uq_cache_job_active_source_binding",
        "cache_job",
        ["source_id", "binding_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({active})"),
    )
    op.drop_column("cache_job", "submit_started_at")
