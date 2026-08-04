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
INSTALLER_SCRIPT = REPOSITORY_ROOT / "windows" / "tool" / "package" / "SakuraPlayer.iss"
INSTALLER_BUILDER = REPOSITORY_ROOT / "windows" / "tool" / "build_windows_installer.ps1"


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
    assert version.installer_name == "SakuraPlayer-Windows-1.0.0-1-Setup.exe"
    assert version.docker_archive_name == "SakuraPlayer-Docker-1.0.0.tar.gz"


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
    assert "installer_name: ${{ steps.version.outputs.installer_name }}" in workflow
    assert (
        "docker_archive_name: ${{ steps.version.outputs.docker_archive_name }}"
        in workflow
    )
    assert "windows/dist/${{ needs.validate.outputs.archive_name }}" in workflow
    assert "windows/dist/${{ needs.validate.outputs.installer_name }}" in workflow
    assert "Build Windows installer" in workflow
    assert "jrsoftware/issrc/releases/download/is-6_4_2/innosetup-6.4.2.exe" in workflow
    assert "Inno Setup 6.4.2" in workflow
    assert (
        "238e2cf82c212a3879a050e02d787283c54bcb72d5cb6070830942de56627d5b" in workflow
    )
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
    assert "build_docker_bundle.py" in workflow
    assert "bash -n backend/install.sh" in workflow
    assert "name: docker-deployment" in workflow
    assert "SakuraPlayer-Docker-" in workflow
    assert 'diff -u "$expected" "$actual"' in workflow
    assert (
        'test "$(tar -xOzf "$archive" "$root/.release-version")" = "$RELEASE_VERSION"'
        in workflow
    )
    assert "needs: [validate, quality, windows, deployment, docker]" in workflow
    assert "Download Linux Docker deployment assets" in workflow
    assert "gh release create" in workflow
    assert "--generate-notes" in workflow
    assert set(re.findall(r"secrets\.([A-Z0-9_]+)", workflow)) == {"DOCKERHUB_TOKEN"}
    assert workflow.count("actions/attest-build-provenance") == 4


def test_windows_installer_reuses_verified_bundle_and_is_per_user() -> None:
    installer = _read(INSTALLER_SCRIPT)
    builder = _read(INSTALLER_BUILDER)

    assert "PrivilegesRequired=lowest" in installer
    assert "DefaultDirName={localappdata}\\Programs\\SakuraPlayer" in installer
    assert 'Source: "{#SourceDir}\\*"' in installer
    assert "ArchitecturesAllowed=x64" in installer
    assert "build_private_release.ps1" in builder
    assert "Expand-Archive" in builder
    assert "ISCC.exe" in builder
    assert "Get-FileHash" in builder
    assert "-Setup.exe" in builder
    assert "CertificateThumbprint" in builder
    assert "Set-AuthenticodeSignature" in builder


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
