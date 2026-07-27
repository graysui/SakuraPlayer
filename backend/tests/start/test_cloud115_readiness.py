from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_ROOT = REPO_ROOT / "docs/specs/001-sakuraplayer-v1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_architecture_approves_actual_cloud115_reference_symbols() -> None:
    architecture = _read(REPO_ROOT / "docs/specs/architecture.md")

    for symbol in (
        "Cloud115QrLogin.get_token",
        "Cloud115QrLogin.get_qrcode_image",
        "Cloud115QrLogin.get_qrcode_status",
        "Cloud115QrLogin.fetch_result",
        "Cloud115Client.dir_info",
    ):
        assert symbol in architecture
    assert "670ca75b2d35b606ffc0caa6fd47fd04c4c95870" in architecture
    assert "TASK-213" in architecture


def test_cloud115_contract_freezes_port_and_sensitive_boundaries() -> None:
    contract = _read(SPEC_ROOT / "contracts/cloud115-port.md")

    for method in (
        "create_qr_session",
        "poll_qr_session",
        "finish_qr_session",
        "probe_credentials",
        "credential_snapshot",
        "find_or_create_directory",
        "directory_info",
        "submit_offline",
        "list_offline_tasks",
        "cancel_offline",
        "list_files_recursive",
        "resolve_original",
        "resolve_hls",
        "download_small_file",
        "delete_managed_entries",
    ):
        assert f"def {method}" in contract

    assert "OfflineTaskSnapshot" in contract
    assert "delete_source_files=False" in contract
    assert "TASK-101 不读取 credential version" in contract
    assert "TASK-102" in contract and "CAS" in contract
    assert "不得\n包含磁力、原始 source URL" in contract
    assert "my.115.com" in contract
    assert "follow_redirects=True" in contract
    assert "禁止" in contract


def test_cloud115_stable_errors_are_catalogued() -> None:
    errors = _read(SPEC_ROOT / "contracts/error-codes.md")

    for code in (
        "cloud115_protocol_error",
        "cloud115_directory_ambiguous",
        "cloud115_offline_invalid",
        "cloud115_offline_quota_exceeded",
        "cloud115_offline_task_not_found",
        "cloud115_file_not_found",
        "cloud115_small_file_too_large",
        "cloud115_submit_uncertain",
        "cloud115_original_unavailable",
        "cloud115_hls_membership_required",
        "cloud115_hls_not_ready",
    ):
        assert f"`{code}`" in errors


def test_protocol_fixtures_and_real115_have_separate_collection_gates() -> None:
    task = _read(SPEC_ROOT / "tasks/TASK-101.md")
    pyproject = _read(REPO_ROOT / "backend/pyproject.toml")
    test_readme = _read(REPO_ROOT / "backend/tests/README.md")
    dockerfile = _read(REPO_ROOT / "backend/docker/api.Dockerfile")
    compose = _read(REPO_ROOT / "backend/tests/run-compose.ps1")

    assert "backend/tests/unit/cloud115/test_protocol_fixtures.py" in task
    assert "backend/tests/lib/cloud115" not in task
    assert '"real115:' in pyproject
    assert 'norecursedirs = ["tests/real115"]' in pyproject
    assert "SAKURAPLAYER_RUN_REAL115=1" in test_readme
    assert "tests/real115" not in dockerfile
    assert "tests/real115" not in compose
    assert "COPY docs /workspace/docs" in dockerfile
    dockerignore_path = REPO_ROOT / ".dockerignore"
    if dockerignore_path.is_file():
        assert "!docs/specs/**" in _read(dockerignore_path)
    else:
        assert (REPO_ROOT / "docs/specs/architecture.md").is_file()
    assert (REPO_ROOT / "backend/tests/real115/README.md").is_file()
    assert (REPO_ROOT / "backend/tests/real115/conftest.py").is_file()
    assert (REPO_ROOT / "backend/tests/real115/test_protocol_smoke.py").is_file()


def test_task_boundaries_assign_snapshot_and_cas_to_the_right_tasks() -> None:
    task101 = _read(SPEC_ROOT / "tasks/TASK-101.md")
    task102 = _read(SPEC_ROOT / "tasks/TASK-102.md")
    task104 = _read(SPEC_ROOT / "tasks/TASK-104.md")
    change = _read(SPEC_ROOT / "changes/2026-07-27--task-101-cloud115-readiness.md")

    assert "只产生 Cookie snapshot" in task101
    assert "credential_version 加密 CAS" in task102
    assert "OfflineTaskPage" in task104
    assert "delete_source_files=False" in task104
    assert "**Status**: Accepted" in change
    for requirement in range(128, 137):
        assert f"REQ-CHG-{requirement}" in change


def test_task101_adapter_has_no_database_or_source_payload_dependency() -> None:
    source_root = REPO_ROOT / "backend/src/sakuraplayer/cloud_cache"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(source_root.rglob("*.py"))
    ).lower()

    assert "sqlalchemy" not in source
    assert "credential_version" not in source
    assert "source_url" not in source
