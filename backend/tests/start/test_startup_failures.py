from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _production_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "SAKURAPLAYER_ENV": "production-private",
            "SAKURAPLAYER_DATABASE_URL": (
                "postgresql+psycopg://test-user:test-password@127.0.0.1:1/test"
                "?connect_timeout=1"
            ),
            "SAKURAPLAYER_SETTINGS_KEY": _b64(b"s" * 32),
            "SAKURAPLAYER_TOKEN_KEY": _b64(b"t" * 32),
            "SAKURAPLAYER_PLAYBACK_KEY": _b64(b"p" * 32),
            "SAKURAPLAYER_BOOTSTRAP_TOKEN": _b64(b"b" * 32),
        }
    )
    return environment


@pytest.mark.parametrize(
    ("module", "component"),
    [
        ("sakuraplayer.api", "api"),
        ("sakuraplayer.worker", "worker"),
        ("sakuraplayer.scheduler", "scheduler"),
        ("sakuraplayer.shared.migration", "migrate"),
    ],
)
def test_entrypoint_reports_safe_schema_startup_failure(
    module: str,
    component: str,
) -> None:
    result = subprocess.run(
        [sys.executable, "-m", module],
        cwd=BACKEND_ROOT,
        env=_production_environment(),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        f"startup_failed component={component} code=database_unavailable\n"
    )


def test_entrypoint_reports_safe_configuration_failure() -> None:
    environment = _production_environment()
    environment.pop("SAKURAPLAYER_DATABASE_URL")

    result = subprocess.run(
        [sys.executable, "-m", "sakuraplayer.api"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "startup_failed component=api code=startup_configuration_invalid\n"
    )
