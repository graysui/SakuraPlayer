from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from uvicorn.protocols.websockets.websockets_impl import WebSocketProtocol

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_runtime_declares_and_installs_websocket_implementation() -> None:
    pyproject = (REPOSITORY_ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")

    assert '"websockets==12.0"' in pyproject
    assert version("websockets") == "12.0"
    assert WebSocketProtocol.__name__ == "WebSocketProtocol"
