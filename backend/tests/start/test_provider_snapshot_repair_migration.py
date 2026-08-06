from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_provider_snapshot_repair_migration_is_linear_and_deterministic() -> None:
    migration = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "0022_provider_snapshot_repair.py"
    )

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")
    assert 'revision: str = "0022_provider_snapshot_repair"' in source
    assert (
        "down_revision: Union[str, Sequence[str], None] = "
        '"0021_metadata_worker_control"'
    ) in source
    assert "03260000-0000-4000-8000-000000000001" in source
    assert "provider_snapshot_request" in source
    assert "actor_mapping_snapshot" in source
    assert "gfriends_snapshot" in source
    assert "status IN ('queued', 'claimed')" in source
    assert "ON CONFLICT DO NOTHING" in source


def test_provider_snapshot_repair_migration_only_removes_its_queue_fact() -> None:
    source = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "0022_provider_snapshot_repair.py"
    ).read_text(encoding="utf-8")

    assert "DELETE FROM provider_snapshot_request" in source
    for protected_table in (
        "actor",
        "actor_alias",
        "movie",
        "encrypted_setting",
        "gfriends_actor_asset",
        "actor_mapping_snapshot",
        "gfriends_snapshot",
    ):
        assert f"DELETE FROM {protected_table}" not in source
