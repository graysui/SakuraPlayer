from pathlib import Path

from sakuraplayer.catalog import models as catalog_models
from sakuraplayer.identity.models import Base


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_provider_snapshot_models_are_registered() -> None:
    assert catalog_models.Actor.__tablename__ == "actor"

    assert {
        "provider_snapshot_request",
        "actor_mapping_snapshot",
        "gfriends_snapshot",
        "gfriends_actor_asset",
    }.issubset(Base.metadata.tables)


def test_provider_snapshot_migration_creates_queue_snapshots_and_assets() -> None:
    migration = BACKEND_ROOT / "alembic" / "versions" / "0009_provider_snapshots.py"

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")
    assert 'revision: str = "0009_provider_snapshots"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0008_catalog_metadata"'
        in source
    )
    for table in (
        "provider_snapshot_request",
        "actor_mapping_snapshot",
        "gfriends_snapshot",
        "gfriends_actor_asset",
    ):
        assert f'"{table}"' in source


def test_provider_snapshot_migration_has_state_and_uniqueness_guards() -> None:
    migration = BACKEND_ROOT / "alembic" / "versions" / "0009_provider_snapshots.py"

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")

    for guard in (
        "uq_provider_snapshot_request_slot",
        "ck_provider_snapshot_request_state",
        "ck_actor_mapping_snapshot_state",
        "ck_gfriends_snapshot_state",
        "uq_actor_mapping_snapshot_current",
        "uq_gfriends_snapshot_current",
        "ck_gfriends_actor_asset_kind",
        "ck_gfriends_actor_asset_position",
        "uq_gfriends_actor_asset_owner_position",
        "uq_gfriends_actor_asset_url",
    ):
        assert guard in source
    assert 'op.drop_table("gfriends_actor_asset")' in source
    assert 'op.drop_table("provider_snapshot_request")' in source
