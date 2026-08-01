from __future__ import annotations

from urllib.parse import quote

import httpx

from sakuraplayer.catalog.providers._html import parse_html
from sakuraplayer.catalog.providers.javdb import MetadataProviderProblem

_BASE_URL = "https://www.dmm.co.jp"
_MAX_HTML_BYTES = 2 * 1024 * 1024
_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cookie": "age_check_done=1; ckcy=1",
}


class DmmProvider:
    def __init__(self, *, http_client: httpx.Client) -> None:
        self._http = http_client

    def fetch_description(self, normalized_number: str) -> str | None:
        number = " ".join(normalized_number.split()).upper()
        if not number or len(number) > 128:
            raise ValueError("invalid normalized movie number")
        try:
            response = self._http.get(
                f"{_BASE_URL}/search/=/searchstr={quote(number, safe='')}/"
                "limit=30/sort=date/",
                headers=_REQUEST_HEADERS,
                timeout=httpx.Timeout(30.0, connect=10.0, pool=10.0),
            )
        except httpx.HTTPError:
            raise MetadataProviderProblem("dmm_upstream_error") from None
        if response.status_code == 404:
            return None
        if response.status_code != 200 or len(response.content) > _MAX_HTML_BYTES:
            raise MetadataProviderProblem("dmm_upstream_error")
        root = parse_html(response.text)
        candidates = [
            node
            for node in root.descendants()
            if node.attrs.get("itemprop") == "description"
            or {"mg-b20", "lh4"}.issubset(node.classes())
        ]
        if not candidates:
            raise MetadataProviderProblem("dmm_upstream_error")
        return candidates[0].text() or None

    def probe(self) -> None:
        self.fetch_description("SONE-248")


__all__ = ["DmmProvider"]
