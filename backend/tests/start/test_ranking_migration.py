from pathlib import Path

from sakuraplayer.discovery import models as discovery_models
from sakuraplayer.identity.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_ranking_models_are_registered() -> None:
    assert discovery_models.RankingSyncRequest.__tablename__ == "ranking_sync_request"
    assert discovery_models.RankingSnapshot.__tablename__ == "ranking_snapshot"
    assert discovery_models.RankingEntry.__tablename__ == "ranking_entry"
    assert {
        "ranking_sync_request",
        "ranking_snapshot",
        "ranking_entry",
    } <= set(Base.metadata.tables)


def test_ranking_migration_owns_request_snapshot_and_entry_schema() -> None:
    migration = BACKEND_ROOT / "alembic" / "versions" / "0012_ranking_snapshots.py"

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")
    assert 'revision: str = "0012_ranking_snapshots"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0011_catalog_discovery"'
        in source
    )
    for expected in (
        '"ranking_sync_request"',
        '"ranking_snapshot"',
        '"ranking_entry"',
        "uq_ranking_request_slot",
        "uq_ranking_request_active_scope",
        "uq_ranking_snapshot_current_scope",
        "uq_ranking_entry_number",
        "ck_ranking_request_state",
        "ck_ranking_snapshot_scope",
    ):
        assert expected in source
    assert 'op.drop_table("ranking_sync_request")' in source
    assert 'op.drop_table("ranking_snapshot")' in source
    assert 'op.drop_table("ranking_entry")' in source


def test_ranking_model_column_shapes() -> None:
    request = Base.metadata.tables["ranking_sync_request"].columns
    snapshot = Base.metadata.tables["ranking_snapshot"].columns
    entry = Base.metadata.tables["ranking_entry"].columns

    assert set(request.keys()) == {
        "id",
        "board",
        "year",
        "scheduled_for",
        "status",
        "claim_owner",
        "claim_token",
        "claim_expires_at",
        "attempt_count",
        "snapshot_id",
        "completed_at",
        "failure_code",
        "created_at",
    }
    assert set(snapshot.keys()) == {
        "id",
        "board",
        "year",
        "status",
        "source_synced_at",
        "created_at",
    }
    assert set(entry.keys()) == {
        "snapshot_id",
        "rank",
        "normalized_number",
        "movie_id",
    }
