from __future__ import annotations

from pathlib import Path

import pytest

from sakuraplayer.cloud_cache.binding_service import (
    CACHE_ROOT_NAME,
    CACHE_ROOT_PARENT_CID,
)

BACKEND_ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.integration


def test_cache_root_scope_is_frozen_to_top_level_direct_child() -> None:
    assert CACHE_ROOT_PARENT_CID == "0"
    assert CACHE_ROOT_NAME == "SakuraPlayer-Cache"
    contract = (
        BACKEND_ROOT.parent
        / "docs"
        / "specs"
        / "001-sakuraplayer-v1"
        / "contracts"
        / "cloud115-port.md"
    ).read_text(encoding="utf-8")
    assert "顶层 CID `0` 的直接子级" in contract
    assert "async mutex" in contract
    assert "PostgreSQL advisory transaction lock" in contract
