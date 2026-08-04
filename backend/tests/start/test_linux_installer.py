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
LATEST_INSTALLER = BACKEND_ROOT / "install-latest.sh"
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
    publish_host: str | None = None,
    api_port: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAKE_DOCKER_LOG"] = str(docker_log)
    env["FAKE_DOCKER_SLEEP"] = str(sleep)
    env["FAKE_DOCKER_FAIL_PHASE"] = fail_phase
    if publish_host is not None:
        env["SAKURAPLAYER_INSTALLER_PUBLISH_HOST"] = publish_host
    if api_port is not None:
        env["SAKURAPLAYER_INSTALLER_API_PORT"] = api_port
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


def test_installer_uses_selected_network_configuration(tmp_path: Path) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)

    result = _run_installer(
        deployment,
        fake_bin,
        docker_log,
        cwd=tmp_path,
        publish_host="192.168.1.50",
        api_port="8000",
    )

    assert result.returncode == 0, result.stderr
    env_text = (deployment / ".env").read_text(encoding="utf-8")
    assert "SAKURAPLAYER_PUBLISH_HOST=192.168.1.50" in env_text
    assert "SAKURAPLAYER_API_PORT=8000" in env_text
    assert "http://192.168.1.50:8000" in result.stdout


@pytest.mark.parametrize(
    ("publish_host", "api_port"),
    [("0.0.0.0", "8000"), ("192.168.1.50", "65536")],
)
def test_installer_rejects_invalid_selected_network_configuration(
    tmp_path: Path, publish_host: str, api_port: str
) -> None:
    deployment, fake_bin, docker_log = _prepare_deployment(tmp_path)

    result = _run_installer(
        deployment,
        fake_bin,
        docker_log,
        cwd=tmp_path,
        publish_host=publish_host,
        api_port=api_port,
    )

    assert result.returncode != 0
    assert "network_" in result.stderr
    assert not (deployment / ".env").exists()
    calls = docker_log.read_text(encoding="utf-8").splitlines()
    assert not any(" config --quiet" in call for call in calls)
    assert not any(call.endswith(" pull") for call in calls)
    assert not any(call.endswith(" up -d --no-build --wait") for call in calls)


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


def _prepare_latest_bootstrap(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    package_root = tmp_path / "SakuraPlayer-Docker-1.2.3"
    package_root.mkdir()
    package_installer = package_root / "install.sh"
    package_installer.write_text(
        "#!/bin/bash\n"
        "set -eu\n"
        "printf '%s\\n' package-installer-ran > \"$BOOTSTRAP_MARKER\"\n",
        encoding="ascii",
    )
    package_installer.chmod(0o755)
    for name in (
        "docker-compose.yml",
        ".env.example",
        ".release-version",
        "install-latest.sh",
        "README.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
    ):
        (package_root / name).write_text("fixture\n", encoding="ascii")
    archive = tmp_path / "SakuraPlayer-Docker-1.2.3.tar.gz"
    subprocess.run(
        ["tar", "-czf", str(archive), "-C", str(tmp_path), package_root.name],
        check=True,
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'printf \'%s\\n\' "$*" >> "$FAKE_CURL_LOG"\n'
        'case " $* " in\n'
        "  *'%{url_effective}'*) printf '%s' \"$FAKE_RELEASE_URL\" ;;\n"
        "  *)\n"
        "    output=''\n"
        "    previous=''\n"
        '    for argument in "$@"; do\n'
        '      if [ "$previous" = \'-o\' ]; then output="$argument"; fi\n'
        '      previous="$argument"\n'
        "    done\n"
        '    test -n "$output"\n'
        '    cp "$FAKE_ARCHIVE" "$output"\n'
        "    ;;\n"
        "esac\n",
        encoding="ascii",
    )
    curl.chmod(0o755)
    marker = tmp_path / "bootstrap-marker"
    return archive, fake_bin, marker, tmp_path / "curl.log"


def _run_latest_installer(
    fake_bin: Path,
    archive: Path,
    marker: Path,
    curl_log: Path,
    *,
    release_url: str,
    container_secrets: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    target = archive.parent / "deployment"
    target.mkdir()
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAKE_ARCHIVE"] = str(archive)
    env["FAKE_CURL_LOG"] = str(curl_log)
    env["FAKE_RELEASE_URL"] = release_url
    env["BOOTSTRAP_MARKER"] = str(marker)
    env["TMPDIR"] = str(archive.parent)
    if container_secrets is not None:
        env["FAKE_CONTAINER_SECRETS"] = str(container_secrets)
    return subprocess.run(
        ["/bin/bash", str(LATEST_INSTALLER)],
        cwd=target,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )


def test_latest_installer_downloads_latest_release_without_checksum(
    tmp_path: Path,
) -> None:
    archive, fake_bin, marker, curl_log = _prepare_latest_bootstrap(tmp_path)

    result = _run_latest_installer(
        fake_bin,
        archive,
        marker,
        curl_log,
        release_url="https://github.com/graysui/SakuraPlayer/releases/tag/v1.2.3",
    )

    assert result.returncode == 0, result.stderr
    assert marker.read_text(encoding="ascii") == "package-installer-ran\n"
    target = archive.parent / "deployment"
    assert (target / "install.sh").is_file()
    assert (target / "docker-compose.yml").is_file()
    assert (target / ".env.example").is_file()
    assert (target / ".release-version").read_text(encoding="ascii") == "fixture\n"
    calls = curl_log.read_text(encoding="ascii").splitlines()
    assert calls[0].endswith("https://github.com/graysui/SakuraPlayer/releases/latest")
    assert calls[1].endswith(
        "/releases/download/v1.2.3/SakuraPlayer-Docker-1.2.3.tar.gz"
    )
    assert "sha256" not in "\n".join(calls).lower()
    assert "sha256" not in result.stdout.lower()
    assert "sha256" not in result.stderr.lower()
    assert not list(archive.parent.glob("sakuraplayer-install.*"))


def test_latest_installer_rejects_unversioned_latest_release(tmp_path: Path) -> None:
    archive, fake_bin, marker, curl_log = _prepare_latest_bootstrap(tmp_path)

    result = _run_latest_installer(
        fake_bin,
        archive,
        marker,
        curl_log,
        release_url="https://github.com/graysui/SakuraPlayer/releases/tag/main",
    )

    assert result.returncode != 0
    assert "release_version_invalid" in result.stderr
    assert not marker.exists()
    assert not any((archive.parent / "deployment").iterdir())
    assert len(curl_log.read_text(encoding="ascii").splitlines()) == 1
    assert not list(archive.parent.glob("sakuraplayer-install.*"))


def test_latest_installer_recovers_secrets_from_running_compose_container(
    tmp_path: Path,
) -> None:
    archive, fake_bin, marker, curl_log = _prepare_latest_bootstrap(tmp_path)
    secret_source = tmp_path / "container-secrets"
    secret_source.mkdir()
    for index, (name, length) in enumerate(SECRET_LENGTHS.items()):
        secret_source.joinpath(name.removesuffix(".txt")).write_text(
            chr(ord("a") + index) * length, encoding="ascii"
        )
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'case "$1" in\n'
        "  ps) printf '%s\\n' old-container ;;\n"
        "  cp)\n"
        '    name="${2##*/}"\n'
        '    cp "$FAKE_CONTAINER_SECRETS/$name" "$3"\n'
        "    ;;\n"
        "esac\n",
        encoding="ascii",
    )
    docker.chmod(0o755)

    result = _run_latest_installer(
        fake_bin,
        archive,
        marker,
        curl_log,
        release_url="https://github.com/graysui/SakuraPlayer/releases/tag/v1.2.3",
        container_secrets=secret_source,
    )

    assert result.returncode == 0, result.stderr
    target = archive.parent / "deployment"
    for index, (name, length) in enumerate(SECRET_LENGTHS.items()):
        assert (target / "secrets" / name).read_text(encoding="ascii") == chr(
            ord("a") + index
        ) * length
