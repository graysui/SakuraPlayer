from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from sakuraplayer.catalog.providers.dmm import DmmProvider
from sakuraplayer.catalog.providers.javdb import MetadataProviderProblem


FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "metadata"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def provider(handler) -> DmmProvider:
    return DmmProvider(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_extracts_text_only_description() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.dmm.co.jp"
        assert request.url.params["searchstr"] == "ABP-123"
        return httpx.Response(200, text=fixture("dmm-description.html"))

    description = provider(handler).fetch_description("ABP-123")

    assert description == "Fixture first line. Fixture second line."
    assert "script" not in description
    assert "secretLikeValue" not in description


def test_empty_or_not_found_description_is_terminal_not_found() -> None:
    empty = provider(
        lambda request: httpx.Response(200, text=fixture("dmm-empty.html"))
    )
    missing = provider(lambda request: httpx.Response(404))

    assert empty.fetch_description("ABP-123") is None
    assert missing.fetch_description("ABP-123") is None


def test_unavailable_or_changed_response_is_warning_error() -> None:
    unavailable = provider(lambda request: httpx.Response(503))
    changed = provider(lambda request: httpx.Response(200, text="<html></html>"))

    for dmm in (unavailable, changed):
        with pytest.raises(MetadataProviderProblem) as error:
            dmm.fetch_description("ABP-123")
        assert error.value.code == "dmm_upstream_error"
