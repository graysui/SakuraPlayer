from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
INSTALLER = BACKEND_ROOT / "install.sh"
SECRET_LENGTHS = {
    "postgres_password.txt": 43,
    "settings_key.txt": 43,
    "token_key.txt": 64,
    "playback_key.txt": 64,
    "bootstrap_token.txt": 64,
}


def _prepare_deployment(tmp_path: Path) -> tuple[Path, Path, Path]:
    deployment = tmp_path / "SakuraPlayer-Docker-1.2.3"
    deployment.mkdir()
    shutil.copy2(INSTALLER, deployment / "install.sh")
    shutil.copy2(BACKEND_ROOT / "docker-compose.yml", deployment)
    shutil.copy2(BACKEND_ROOT / ".env.example", deployment)
    (deployment / ".release-version").write_text("1.2.3\n", encoding="ascii")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$FAKE_DOCKER_LOG"
case " $* " in
  *" pull "*)
    if [ "${FAKE_DOCKER_SLEEP:-0}" != "0" ]; then
      sleep "$FAKE_DOCKER_SLEEP"
    fi
    ;;
esac
if [ -n "${FAKE_DOCKER_FAIL_PHASE:-}" ]; then
  case " $* " in
    *" ${FAKE_DOCKER_FAIL_PHASE} "*)
      printf 'FAKE_DOCKER_SECRET\\n' >&2
      exit 42
      ;;
  esac
fi
""",
        encoding="ascii",
    )
    docker.chmod(0o755)
    return deployment, fake_bin, tmp_path / "docker.log"


def _run_installer(
    deployment: Path,
    fake_bin: Path,
    docker_log: Path,
    *,
    cwd: Path,
    sleep: int = 0,
    fail_phase: str = "",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAKE_DOCKER_LOG"] = str(docker_log)
    env["FAKE_DOCKER_SLEEP"] = str(sleep)
    env["FAKE_DOCKER_FAIL_PHASE"] = fail_phase
    return subprocess.run(
        ["/bin/bash", str(deployment / "install.sh")],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )


def _secret_values(deployment: Path) -> dict[str, str]:
    return {
        name: (deployment / "secrets" / name).read_text(encoding="ascii")
        for name in SECRET_LENGTHS
    }


def test_installer_generates_private_secrets_and_is_idempotent(tmp_path: Path) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    first = _run_installer(deployment, fake_bin, docker_log, cwd=outside)

    assert first.returncode == 0, first.stderr
    env_text = (deployment / ".env").read_text(encoding="utf-8")
    assert (
        "SAKURAPLAYER_BACKEND_IMAGE=docker.io/graysui/sakuraplayer-backend:1.2.3"
    ) in env_text
    assert "SAKURAPLAYER_PUBLISH_HOST=127.0.0.1" in env_text

    secrets = _secret_values(deployment)
    assert len(set(secrets.values())) == len(secrets)
    for name, expected_length in SECRET_LENGTHS.items():
        value = secrets[name]
        assert len(value) == expected_length
        assert re.fullmatch(r"[A-Za-z0-9_-]+", value)
        assert stat.S_IMODE((deployment / "secrets" / name).stat().st_mode) == 0o600
        assert value not in first.stdout
        assert value not in first.stderr
    assert stat.S_IMODE((deployment / "secrets").stat().st_mode) == 0o700
    assert "bootstrap_token.txt" in first.stdout
    assert "postgres_password.txt" not in first.stdout
    assert "settings_key.txt" not in first.stdout
    assert "token_key.txt" not in first.stdout
    assert "playback_key.txt" not in first.stdout

    env_before = (deployment / ".env").read_bytes()
    second = _run_installer(deployment, fake_bin, docker_log, cwd=outside)

    assert second.returncode == 0, second.stderr
    assert (deployment / ".env").read_bytes() == env_before
    assert _secret_values(deployment) == secrets
    for value in secrets.values():
        assert value not in second.stdout
        assert value not in second.stderr

    calls = docker_log.read_text(encoding="utf-8").splitlines()
    assert sum(call == "info" for call in calls) == 2
    assert sum(call == "compose version" for call in calls) == 2
    assert sum(" config --quiet" in call for call in calls) == 2
    assert sum(call.endswith(" pull") for call in calls) == 2
    assert sum(call.endswith(" up -d --no-build --wait") for call in calls) == 2


def test_installer_accepts_crlf_release_template(tmp_path: Path) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)
    template = deployment / ".env.example"
    normalized = template.read_bytes().replace(b"\r\n", b"\n")
    template.write_bytes(normalized.replace(b"\n", b"\r\n"))

    result = _run_installer(deployment, fake_bin, docker_log, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    env_bytes = (deployment / ".env").read_bytes()
    assert b"\r" not in env_bytes
    assert b"SAKURAPLAYER_PUBLISH_HOST=127.0.0.1\n" in env_bytes


def test_installer_preserves_configuration_and_secrets_after_compose_failure(
    tmp_path: Path,
) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)

    failed = _run_installer(
        deployment,
        fake_bin,
        docker_log,
        cwd=tmp_path,
        fail_phase="pull",
    )

    assert failed.returncode != 0
    assert "compose_pull_failed" in failed.stderr
    assert "FAKE_DOCKER_SECRET" not in failed.stdout
    assert "FAKE_DOCKER_SECRET" not in failed.stderr
    env_before = (deployment / ".env").read_bytes()
    secrets_before = _secret_values(deployment)

    retried = _run_installer(deployment, fake_bin, docker_log, cwd=tmp_path)

    assert retried.returncode == 0, retried.stderr
    assert (deployment / ".env").read_bytes() == env_before
    assert _secret_values(deployment) == secrets_before


@pytest.mark.parametrize(
    ("name", "contents"),
    [
        ("settings_key.txt", "not-base64url"),
        ("token_key.txt", "a" * 63),
        ("bootstrap_token.txt", "=" * 64),
    ],
)
def test_installer_rejects_invalid_existing_secret_before_generation(
    tmp_path: Path, name: str, contents: str
) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)
    secret_dir = deployment / "secrets"
    secret_dir.mkdir()
    (secret_dir / name).write_text(contents, encoding="ascii")

    result = _run_installer(deployment, fake_bin, docker_log, cwd=tmp_path)

    assert result.returncode != 0
    assert "secret_invalid" in result.stderr
    assert contents not in result.stderr
    assert sorted(path.name for path in secret_dir.glob("*.txt")) == [name]
    calls = docker_log.read_text(encoding="utf-8").splitlines()
    assert not any(call.endswith(" pull") for call in calls)
    assert not any(" up -d " in call for call in calls)


def test_installer_rejects_symlink_without_touching_target(tmp_path: Path) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)
    secret_dir = deployment / "secrets"
    secret_dir.mkdir()
    target = tmp_path / "outside-secret"
    original = "a" * 43
    target.write_text(original, encoding="ascii")
    (secret_dir / "settings_key.txt").symlink_to(target)

    result = _run_installer(deployment, fake_bin, docker_log, cwd=tmp_path)

    assert result.returncode != 0
    assert "secret_unsafe_path" in result.stderr
    assert target.read_text(encoding="ascii") == original
    assert original not in result.stderr


@pytest.mark.parametrize("unsafe_name", [".env", "secrets"])
def test_installer_rejects_unsafe_top_level_path(
    tmp_path: Path, unsafe_name: str
) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)
    target = tmp_path / f"outside-{unsafe_name.lstrip('.')}"
    if unsafe_name == "secrets":
        target.mkdir()
    else:
        target.write_text("do-not-touch", encoding="ascii")
    (deployment / unsafe_name).symlink_to(target, target_is_directory=target.is_dir())

    result = _run_installer(deployment, fake_bin, docker_log, cwd=tmp_path)

    assert result.returncode != 0
    assert "unsafe_path" in result.stderr
    if target.is_file():
        assert target.read_text(encoding="ascii") == "do-not-touch"


def test_installer_rejects_reused_secret_material(tmp_path: Path) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)
    secret_dir = deployment / "secrets"
    secret_dir.mkdir()
    duplicate = "a" * 43
    (secret_dir / "postgres_password.txt").write_text(duplicate, encoding="ascii")
    (secret_dir / "settings_key.txt").write_text(duplicate, encoding="ascii")

    result = _run_installer(deployment, fake_bin, docker_log, cwd=tmp_path)

    assert result.returncode != 0
    assert "secret_reused" in result.stderr
    assert duplicate not in result.stderr
    assert sorted(path.name for path in secret_dir.glob("*.txt")) == [
        "postgres_password.txt",
        "settings_key.txt",
    ]


def test_installer_rejects_concurrent_execution(tmp_path: Path) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAKE_DOCKER_LOG"] = str(docker_log)
    env["FAKE_DOCKER_SLEEP"] = "2"
    first = subprocess.Popen(
        ["/bin/bash", str(deployment / "install.sh")],
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if docker_log.exists() and " pull\n" in f" {docker_log.read_text()}":
            break
        time.sleep(0.05)
    else:
        first.kill()
        pytest.fail("first installer did not reach the pull phase")

    second = _run_installer(deployment, fake_bin, docker_log, cwd=tmp_path)
    first_stdout, first_stderr = first.communicate(timeout=10)

    assert first.returncode == 0, first_stderr
    assert second.returncode != 0
    assert "install_locked" in second.stderr
    for value in _secret_values(deployment).values():
        assert value not in first_stdout
        assert value not in first_stderr
        assert value not in second.stdout
        assert value not in second.stderr
