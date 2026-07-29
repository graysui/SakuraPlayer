from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).with_name("task015_cleanup_gate.py")
PHASE1_MIGRATIONS = {
    "0001_initial_skeleton.py",
    "0002_identity.py",
    "0003_encrypted_settings.py",
    "0004_avdb_sync.py",
    "0005_resource_import.py",
    "0006_movie_source_management.py",
    "0007_metadata_queue.py",
    "0008_catalog_metadata.py",
    "0009_provider_snapshots.py",
    "0010_translation.py",
    "0011_catalog_discovery.py",
    "0012_ranking_snapshots.py",
    "0013_events_settings_diagnostics.py",
}


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task015_cleanup_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_is_limited_to_current_python_cleanup_scope() -> None:
    manifest = _load_gate().cleanup_manifest()

    assert manifest == sorted(set(manifest))
    assert "backend/alembic/env.py" in manifest
    assert "backend/src/sakuraplayer/api/app.py" in manifest
    assert "backend/tests/e2e/test_catalog_metadata_e2e.py" in manifest
    assert not any("/alembic/versions/" in path for path in manifest)
    assert all(path.endswith(".py") for path in manifest)


def test_baseline_captures_actual_interfaces_and_state_constraints() -> None:
    baseline = _load_gate().capture_baseline()

    assert "/api/v1/auth/bootstrap" in baseline["openapi"]["paths"]
    assert PHASE1_MIGRATIONS <= baseline["migrations"].keys()
    constraint_names = {
        item["name"] for item in baseline["state_machines"]["sql_check_constraints"]
    }
    assert "ck_metadata_job_status" in constraint_names
    assert baseline["state_machines"]["metadata_stages"][0] == "javdb_core"


def test_baseline_comparison_reports_changed_sections() -> None:
    gate = _load_gate()
    before = {"openapi": {"paths": {}}, "migrations": {}}
    after = {"openapi": {"paths": {"/changed": {}}}, "migrations": {}}

    assert gate.compare_baselines(before, before) == []
    assert gate.compare_baselines(before, after) == ["openapi"]
