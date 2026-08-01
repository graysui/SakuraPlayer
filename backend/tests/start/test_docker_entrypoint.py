from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:
    pytest = None


BACKEND_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = BACKEND_ROOT / "docker-compose.yml"
DEVELOPMENT_COMPOSE_FILE = BACKEND_ROOT / "docker-compose.dev.yml"
RUN_COMPOSE_SCRIPT = BACKEND_ROOT / "tests" / "run-compose.ps1"
pytestmark = pytest.mark.host_docker if pytest is not None else None


def _compose_config() -> dict:
    environment = os.environ.copy()
    environment.update(
        {
            "SAKURAPLAYER_POSTGRES_PASSWORD_SECRET_FILE": "./tests/fixtures/postgres_password.txt",
            "SAKURAPLAYER_SETTINGS_KEY_SECRET_FILE": "./tests/fixtures/settings_key.txt",
            "SAKURAPLAYER_TOKEN_KEY_SECRET_FILE": "./tests/fixtures/token_key.txt",
            "SAKURAPLAYER_PLAYBACK_KEY_SECRET_FILE": "./tests/fixtures/playback_key.txt",
            "SAKURAPLAYER_BOOTSTRAP_TOKEN_SECRET_FILE": "./tests/fixtures/bootstrap_token.txt",
        }
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "config",
            "--format",
            "json",
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _development_compose_config() -> dict:
    environment = os.environ.copy()
    environment.update(
        {
            "SAKURAPLAYER_POSTGRES_PASSWORD_SECRET_FILE": "./tests/fixtures/postgres_password.txt",
            "SAKURAPLAYER_SETTINGS_KEY_SECRET_FILE": "./tests/fixtures/settings_key.txt",
            "SAKURAPLAYER_TOKEN_KEY_SECRET_FILE": "./tests/fixtures/token_key.txt",
            "SAKURAPLAYER_PLAYBACK_KEY_SECRET_FILE": "./tests/fixtures/playback_key.txt",
            "SAKURAPLAYER_BOOTSTRAP_TOKEN_SECRET_FILE": "./tests/fixtures/bootstrap_token.txt",
        }
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "-f",
            str(DEVELOPMENT_COMPOSE_FILE),
            "config",
            "--format",
            "json",
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_compose_has_isolated_processes_and_pinned_postgres() -> None:
    config = _compose_config()
    services = config["services"]

    assert set(services) == {"api", "migrate", "scheduler", "worker", "postgres"}
    assert services["postgres"]["image"] == "postgres:17.5"
    assert "ports" not in services["postgres"]
    assert services["api"]["ports"][0]["host_ip"] == "127.0.0.1"
    assert services["api"]["ports"][0]["published"] == "8000"
    assert services["api"]["ports"][0]["target"] == 8000
    assert services["api"]["command"] != services["worker"]["command"]
    assert services["worker"]["command"] != services["scheduler"]["command"]
    assert services["migrate"]["command"] == [
        "python",
        "-m",
        "sakuraplayer.shared.migration",
    ]
    assert services["api"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["migrate"]["restart"] == "no"


def test_compose_has_required_volumes_and_healthchecks() -> None:
    config = _compose_config()

    assert set(config["volumes"]) == {
        "app-logs",
        "catalog-images",
        "db-data",
        "provider-cache",
    }
    for service_name in ("api", "scheduler", "worker", "postgres"):
        assert "healthcheck" in config["services"][service_name]


def test_development_compose_watches_all_and_only_long_running_app_services() -> None:
    production = _compose_config()
    development = _development_compose_config()

    for service_name in ("postgres", "migrate"):
        assert "develop" not in development["services"][service_name]
    for service_name in ("api", "worker", "scheduler"):
        assert "develop" not in production["services"][service_name]
        watch = development["services"][service_name]["develop"]["watch"]
        assert len(watch) == 4
        assert watch[0]["action"] == "sync+restart"
        assert watch[0]["path"] == str(BACKEND_ROOT / "src")
        assert watch[0]["target"] == "/workspace/backend/src"
        assert watch[0]["ignore"] == ["**/__pycache__/**", "**/*.pyc"]
        assert {item["path"] for item in watch[1:]} == {
            str(BACKEND_ROOT / "pyproject.toml"),
            str(BACKEND_ROOT / "docker" / "api.Dockerfile"),
            str(BACKEND_ROOT / "docker" / "entrypoint.sh"),
        }
        assert {item["action"] for item in watch[1:]} == {"rebuild"}


def test_entrypoint_percent_encodes_database_password() -> None:
    source = (BACKEND_ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    assert "urllib.parse" in source
    assert "quote(" in source
    assert "sys.argv[2]" in source
    assert "sys.argv[3]" in source


def test_powershell_verbose_alias_consumes_short_volume_flag() -> None:
    command = r"""
function Invoke-Probe {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments)] [string[]] $Arguments)
    $Arguments -join '|'
}
Invoke-Probe down -v --remove-orphans
"""
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "down|--remove-orphans"


def test_compose_cleanup_uses_unambiguous_volume_and_image_flags() -> None:
    source = RUN_COMPOSE_SCRIPT.read_text(encoding="utf-8")

    assert "Invoke-Compose down --volumes --remove-orphans --rmi local" in source
    assert "docker image rm $testImage" in source


def test_final_postgres_step_collects_task014_e2e_once() -> None:
    source = RUN_COMPOSE_SCRIPT.read_text(encoding="utf-8")

    command = "-m pytest tests/integration tests/e2e -m 'integration' -q"
    assert source.count(command) == 1
    assert source.count("Invoke-Compose up -d --build") == 1


def test_compose_cleanup_verifies_only_project_scoped_resources_are_gone() -> None:
    source = RUN_COMPOSE_SCRIPT.read_text(encoding="utf-8")

    assert "Assert-NoProjectResources" in source
    assert source.index("Assert-NoProjectResources") < source.index("finally {")
    finally_block = source[source.index("finally {") :]
    assert "Assert-NoProjectResources" in finally_block
    assert "com.docker.compose.project=$projectName" in source
    for resource_command in (
        "docker ps -a",
        "docker network ls",
        "docker volume ls",
        "docker image ls",
    ):
        assert resource_command in source


def test_compose_finally_covers_secret_setup_and_skips_down_without_env_file() -> None:
    source = RUN_COMPOSE_SCRIPT.read_text(encoding="utf-8")

    try_index = source.index("try {")
    finally_index = source.index("finally {")
    assert try_index < source.index("New-Item -ItemType Directory") < finally_index
    assert try_index < source.index("[IO.File]::WriteAllText") < finally_index
    assert try_index < source.index("[IO.File]::WriteAllLines") < finally_index
    assert "$envFileReady = $false" in source
    assert "$envFileReady = $true" in source
    finally_block = source[finally_index:]
    assert "if ($envFileReady)" in finally_block
    assert finally_block.index("if ($envFileReady)") < finally_block.index(
        "Invoke-Compose down"
    )
    assert "failed to remove the temporary secret directory" in finally_block
    assert "Test-Path -LiteralPath $tempRoot" in finally_block


if __name__ == "__main__":
    test_compose_has_isolated_processes_and_pinned_postgres()
    test_compose_has_required_volumes_and_healthchecks()
    test_development_compose_watches_all_and_only_long_running_app_services()
    test_entrypoint_percent_encodes_database_password()
    test_powershell_verbose_alias_consumes_short_volume_flag()
    test_compose_cleanup_uses_unambiguous_volume_and_image_flags()
    test_final_postgres_step_collects_task014_e2e_once()
    test_compose_cleanup_verifies_only_project_scoped_resources_are_gone()
    test_compose_finally_covers_secret_setup_and_skips_down_without_env_file()
