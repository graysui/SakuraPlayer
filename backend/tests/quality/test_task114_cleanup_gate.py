from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).with_name("task114_cleanup_gate.py")


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task114_cleanup_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_is_fixed_to_phase2_python_scope() -> None:
    gate = _load_gate()
    manifest = gate.cleanup_manifest()

    assert manifest == sorted(set(manifest))
    assert len(manifest) == 126
    assert len([path for path in manifest if path.startswith("backend/src/")]) == 61
    assert len([path for path in manifest if path.startswith("backend/tests/")]) == 64
    assert "backend/alembic/env.py" in manifest
    assert "backend/src/sakuraplayer/cloud_cache/ports/cloud115.py" in manifest
    assert "backend/src/sakuraplayer/playback/session.py" in manifest
    assert "backend/tests/real115/test_protocol_smoke.py" in manifest
    assert not any("/alembic/versions/" in path for path in manifest)
    assert all((gate.REPOSITORY_ROOT / path).is_file() for path in manifest)


def test_mypy_files_are_the_green_production_subset() -> None:
    gate = _load_gate()
    manifest = set(gate.cleanup_manifest())
    mypy = gate.mypy_files()

    assert mypy == sorted(set(mypy))
    assert len(mypy) == 57
    assert all(f"backend/{path}" in manifest for path in mypy)
    assert "src/sakuraplayer/cloud_cache/ports/cloud115.py" in mypy
    assert "src/sakuraplayer/playback/session.py" in mypy
    assert "src/sakuraplayer/api/app.py" not in mypy
    assert "src/sakuraplayer/worker/__main__.py" not in mypy


def test_baseline_captures_phase2_interfaces_and_guards() -> None:
    baseline = _load_gate().capture_baseline()

    paths = baseline["openapi"]["paths"]
    assert any(path.startswith("/api/v1/cloud115/") for path in paths)
    assert any(path.startswith("/api/v1/cache-jobs") for path in paths)
    assert any(path.startswith("/api/v1/playback/") for path in paths)
    assert len(baseline["migrations"]) == 20
    constraints = {
        item["name"] for item in baseline["state_machines"]["sql_check_constraints"]
    }
    assert "ck_cache_job_status" in constraints
    assert "ck_playback_session_mode" in constraints
    assert "delete_managed_entries" in baseline["cloud115_interface"]["methods"]
    assert "ready" in baseline["state_machines"]["cache_statuses"]
    assert "cloud115_protocol_error" in baseline["stable_error_codes"]
    assert "playback_signature_invalid" in baseline["stable_error_codes"]
    assert any(path.endswith("NOTICE.md") for path in baseline["guard_files"])
    assert any("tests/real115" in path for path in baseline["guard_files"])


def test_baseline_comparison_reports_changed_sections() -> None:
    gate = _load_gate()
    before = {"openapi": {"paths": {}}, "migrations": {}}
    after = {"openapi": {"paths": {"/changed": {}}}, "migrations": {}}

    assert gate.compare_baselines(before, before) == []
    assert gate.compare_baselines(before, after) == ["openapi"]
