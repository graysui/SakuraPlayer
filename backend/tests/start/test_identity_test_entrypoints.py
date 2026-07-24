from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_test_image_and_compose_workflow_include_task002_suites() -> None:
    dockerfile = (REPO_ROOT / "backend/docker/api.Dockerfile").read_text(
        encoding="utf-8"
    )
    compose_workflow = (REPO_ROOT / "backend/tests/run-compose.ps1").read_text(
        encoding="utf-8"
    )

    for path in (
        "tests/start",
        "tests/unit",
        "tests/integration/identity/test_auth_api.py",
    ):
        assert path in dockerfile
        assert path in compose_workflow
    assert "tests/integration -m 'integration'" in compose_workflow
