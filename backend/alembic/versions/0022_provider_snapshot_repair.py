"""Queue one provider snapshot repair for incomplete existing deployments.

Revision ID: 0022_provider_snapshot_repair
Revises: 0021_metadata_worker_control
Create Date: 2026-08-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0022_provider_snapshot_repair"
down_revision: Union[str, Sequence[str], None] = "0021_metadata_worker_control"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REPAIR_REQUEST_ID = "03260000-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO provider_snapshot_request (
            id,
            scheduled_for,
            status,
            claim_owner,
            claim_token,
            claim_expires_at,
            attempt_count,
            created_at,
            completed_at,
            failure_code
        )
        SELECT
            '{_REPAIR_REQUEST_ID}',
            TIMESTAMPTZ '2026-08-06 00:00:32+00',
            'queued',
            NULL,
            NULL,
            NULL,
            0,
            TIMESTAMPTZ '2026-08-06 00:00:32+00',
            NULL,
            NULL
        WHERE (
            NOT EXISTS (
                SELECT 1 FROM actor_mapping_snapshot WHERE status = 'current'
            )
            OR NOT EXISTS (
                SELECT 1 FROM gfriends_snapshot WHERE status = 'current'
            )
        )
        AND NOT EXISTS (
            SELECT 1
            FROM provider_snapshot_request
            WHERE status IN ('queued', 'claimed')
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM provider_snapshot_request "
        f"WHERE id = '{_REPAIR_REQUEST_ID}'"
    )
