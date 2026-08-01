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


def test_searches_exact_cid_then_extracts_mono_text_description() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.dmm.co.jp"
        assert request.headers["cookie"] == "age_check_done=1; ckcy=1"
        assert "Mozilla/5.0" in request.headers["user-agent"]
        seen.append(request.url.path)
        if request.url.path.startswith("/search/"):
            return httpx.Response(200, text=fixture("dmm-search.html"))
        assert request.url.path == "/digital/video/-/detail/=/cid=abp00123/"
        return httpx.Response(200, text=fixture("dmm-mono-detail.html"))

    description = provider(handler).fetch_description("ABP-123")

    assert description == "Fixture first line. Fixture second line."
    assert "script" not in description
    assert "secretLikeValue" not in description
    assert seen == [
        "/search/=/searchstr=ABP-123/limit=30/sort=date/",
        "/digital/video/-/detail/=/cid=abp00123/",
    ]


def test_extracts_rental_product_json_ld_description() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/search/"):
            return httpx.Response(
                200,
                text=fixture("dmm-rental-search.html"),
            )
        assert request.url.path == "/rental/-/detail/=/cid=abp00123/"
        return httpx.Response(200, text=fixture("dmm-rental-detail.html"))

    assert provider(handler).fetch_description("ABP-123") == "Rental fixture desc."


def test_unmatched_or_not_found_search_is_terminal_not_found() -> None:
    unmatched = provider(
        lambda request: httpx.Response(200, text=fixture("dmm-unmatched-search.html"))
    )
    missing = provider(lambda request: httpx.Response(404))

    assert unmatched.fetch_description("ABP-123") is None
    assert missing.fetch_description("ABP-123") is None


def test_unsafe_detail_link_is_ignored_without_requesting_it() -> None:
    seen = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen
        seen += 1
        return httpx.Response(200, text=fixture("dmm-unsafe-search.html"))

    assert provider(handler).fetch_description("ABP-123") is None
    assert seen == 1


def test_prefixed_compact_cid_still_requires_exact_number() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/search/"):
            return httpx.Response(
                200,
                text=(
                    '<a href="https://www.dmm.co.jp/mono/dvd/-/detail/=/cid=4sone248/">'
                    "match</a>"
                ),
            )
        assert request.url.path.endswith("/cid=4sone248/")
        return httpx.Response(200, text=fixture("dmm-mono-detail.html"))

    assert provider(handler).fetch_description("SONE-248") is not None
    assert provider(handler).fetch_description("SONE-249") is None


def test_unavailable_or_oversized_response_is_warning_error() -> None:
    unavailable = provider(lambda request: httpx.Response(503))
    oversized = provider(
        lambda request: httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))
    )

    for dmm in (unavailable, oversized):
        with pytest.raises(MetadataProviderProblem) as error:
            dmm.fetch_description("ABP-123")
        assert error.value.code == "dmm_upstream_error"


def test_probe_is_read_only_and_requires_fixed_description() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.startswith("/search/"):
            return httpx.Response(
                200,
                text=fixture("dmm-probe-search.html"),
            )
        return httpx.Response(200, text=fixture("dmm-mono-detail.html"))

    assert provider(handler).probe() is None
    assert len(seen) == 2
    assert all(request.method == "GET" for request in seen)

    changed = provider(lambda request: httpx.Response(200, text="<html></html>"))
    with pytest.raises(MetadataProviderProblem) as error:
        changed.probe()
    assert error.value.code == "dmm_upstream_error"
