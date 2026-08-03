from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VERIFY_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "verify.yml"
RELEASE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "release.yml"
VERSION_TOOL = REPOSITORY_ROOT / "tools" / "release" / "validate_version.py"
COMPOSE_FILE = REPOSITORY_ROOT / "backend" / "docker-compose.yml"
DOCKERFILE = REPOSITORY_ROOT / "backend" / "docker" / "api.Dockerfile"


def _read(path: Path) -> str:
    assert path.is_file(), f"required release file is missing: {path}"
    return path.read_text(encoding="utf-8")


def _load_version_tool():
    assert VERSION_TOOL.is_file(), "release version validator is missing"
    spec = importlib.util.spec_from_file_location("release_version", VERSION_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_version_matches_flutter_semver_and_preserves_build_number() -> None:
    module = _load_version_tool()

    version = module.validate_release_version(
        tag="v1.0.0",
        pubspec_path=REPOSITORY_ROOT / "windows" / "pubspec.yaml",
    )

    assert version.semver == "1.0.0"
    assert version.build_number == "1"
    assert version.artifact_version == "1.0.0-1"
    assert version.archive_name == "SakuraPlayer-Windows-1.0.0-1.zip"


@pytest.mark.parametrize("tag", ["1.0.0", "v1.0", "v1.0.0-rc.1", "v01.0.0"])
def test_release_version_rejects_noncanonical_tags(tag: str) -> None:
    module = _load_version_tool()

    with pytest.raises(ValueError, match="tag"):
        module.validate_release_version(
            tag=tag,
            pubspec_path=REPOSITORY_ROOT / "windows" / "pubspec.yaml",
        )


def test_release_version_rejects_pubspec_mismatch(tmp_path: Path) -> None:
    module = _load_version_tool()
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("version: 2.0.0+7\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        module.validate_release_version(tag="v1.0.0", pubspec_path=pubspec)


def test_verify_workflow_covers_main_pull_requests_and_release_builds() -> None:
    workflow = _read(VERIFY_WORKFLOW)

    assert "workflow_call:" in workflow
    assert "pull_request:" in workflow
    assert re.search(r"push:\s*\n\s+branches:\s*\[main\]", workflow)
    assert "permissions:\n  contents: read" in workflow
    assert "--target test" in workflow
    assert (
        "pytest tests/start tests/unit tests/integration/api tests/integration/events"
        in workflow
    )
    assert "--target runtime" in workflow
    assert "flutter analyze" in workflow
    assert "flutter test" in workflow
    assert "flutter build windows --release" in workflow


def test_release_workflow_has_atomic_tag_release_and_attestations() -> None:
    workflow = _read(RELEASE_WORKFLOW)

    assert re.search(r"tags:\s*\[.?v\*.?\]", workflow)
    assert "validate_version.py" in workflow
    assert "uses: ./.github/workflows/verify.yml" in workflow
    assert "archive_name: ${{ steps.version.outputs.archive_name }}" in workflow
    assert "windows/dist/${{ needs.validate.outputs.archive_name }}" in workflow
    assert "ghcr.io/graysui/sakuraplayer-backend" in workflow
    assert "docker.io/graysui/sakuraplayer-backend" in workflow
    assert "Log in to Docker Hub" in workflow
    assert "username: graysui" in workflow
    assert "password: ${{ secrets.DOCKERHUB_TOKEN }}" in workflow
    for tag_rule in (
        "type=semver,pattern={{version}}",
        "pattern={{major}}.{{minor}}",
        "pattern={{major}}",
        "type=sha",
    ):
        assert tag_rule in workflow
    assert "actions/attest-build-provenance" in workflow
    assert workflow.count("push-to-registry: true") == 2
    assert "needs: [validate, quality, windows, docker]" in workflow
    assert "gh release create" in workflow
    assert "--generate-notes" in workflow
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", workflow)) == {"DOCKERHUB_TOKEN"}


def test_all_actions_are_pinned_to_immutable_commits() -> None:
    for path in (VERIFY_WORKFLOW, RELEASE_WORKFLOW):
        workflow = _read(path)
        uses_lines = [line.strip() for line in workflow.splitlines() if "uses:" in line]
        assert uses_lines
        for line in uses_lines:
            if "uses: ./" in line:
                assert line == "uses: ./.github/workflows/verify.yml"
                continue
            assert re.search(r"uses:\s+[^\s@]+@[0-9a-f]{40}\s+#\s+v\d", line), line
        assert workflow.count("uses: actions/checkout@") == workflow.count(
            "persist-credentials: false"
        )


def test_release_build_environment_avoids_moving_runner_and_base_tags() -> None:
    workflows = _read(VERIFY_WORKFLOW) + _read(RELEASE_WORKFLOW)
    dockerfile = _read(DOCKERFILE)

    assert "-latest" not in workflows
    assert "runs-on: ubuntu-24.04" in workflows
    assert "runs-on: windows-2022" in workflows
    assert re.search(
        r"^FROM python:3\.10\.16-slim@sha256:[0-9a-f]{64} AS base$",
        dockerfile,
        re.MULTILINE,
    )
    assert re.search(
        r"quality:\s*\n\s+name: Run release quality gates\s*\n\s+needs: validate",
        _read(RELEASE_WORKFLOW),
    )


def test_compose_reuses_one_configurable_backend_image() -> None:
    compose = _read(COMPOSE_FILE)
    image_setting = "image: ${SAKURAPLAYER_BACKEND_IMAGE:-sakuraplayer-backend:local}"

    assert compose.count(image_setting) == 4
    for service in ("api", "migrate", "worker", "scheduler"):
        assert re.search(
            rf"^  {service}:.*?^    {re.escape(image_setting)}$", compose, re.M | re.S
        )
