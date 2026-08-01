from __future__ import annotations

import html
import json
import re
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from sakuraplayer.catalog.providers._html import parse_html
from sakuraplayer.catalog.providers.javdb import MetadataProviderProblem
from sakuraplayer.resources.number_normalizer import normalize_movie_number

_BASE_URL = "https://www.dmm.co.jp"
_MAX_HTML_BYTES = 2 * 1024 * 1024
_BACKEND_DETAIL_URL = re.compile(
    r'"(?:detailUrl|detail_url)"\s*:\s*"(?P<url>[^"]+)"',
    re.IGNORECASE,
)
_CID = re.compile(r"cid=([^/?&#]+)", re.IGNORECASE)
_PADDED_CID_NUMBER = re.compile(
    r"(?<![A-Za-z])(?P<prefix>[A-Za-z]{2,16})00(?P<number>[0-9]{2,10})(?![0-9])",
    re.IGNORECASE,
)
_COMPACT_CID_NUMBER = re.compile(
    r"(?<![A-Za-z])(?P<prefix>[A-Za-z]{2,16})(?P<number>[0-9]{2,10})(?![0-9])",
    re.IGNORECASE,
)
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
        number = normalize_movie_number(normalized_number)
        if number is None:
            raise ValueError("invalid normalized movie number")
        search = self._get(
            f"{_BASE_URL}/search/=/searchstr={quote(number, safe='')}/"
            "limit=30/sort=date/"
        )
        if search is None:
            return None
        for detail_url in reversed(self._matching_detail_urls(search, number)):
            detail = self._get(detail_url)
            if detail is None:
                continue
            description = self._description(detail_url, detail)
            if description:
                return description
        return None

    def probe(self) -> None:
        if not self.fetch_description("SONE-248"):
            raise MetadataProviderProblem("dmm_upstream_error")

    def _get(self, url: str) -> str | None:
        if not _is_safe_dmm_url(url):
            raise MetadataProviderProblem("dmm_upstream_error")
        try:
            response = self._http.get(
                url,
                headers=_REQUEST_HEADERS,
                timeout=httpx.Timeout(30.0, connect=10.0, pool=10.0),
            )
        except httpx.HTTPError:
            raise MetadataProviderProblem("dmm_upstream_error") from None
        if response.status_code == 404:
            return None
        if response.status_code != 200 or len(response.content) > _MAX_HTML_BYTES:
            raise MetadataProviderProblem("dmm_upstream_error")
        return response.text

    @classmethod
    def _matching_detail_urls(cls, search: str, number: str) -> tuple[str, ...]:
        matches: list[str] = []
        seen: set[str] = set()
        raw_urls = [
            match.group("url") for match in _BACKEND_DETAIL_URL.finditer(search)
        ]
        raw_urls.extend(
            node.attrs.get("href", "") for node in parse_html(search).descendants("a")
        )
        for raw_url in raw_urls:
            url = _canonical_detail_url(_decode_detail_url(raw_url))
            if url is None or url in seen:
                continue
            if _number_from_detail_url(url) != number:
                continue
            seen.add(url)
            matches.append(url)
        return tuple(matches)

    @staticmethod
    def _description(detail_url: str, detail: str) -> str | None:
        root = parse_html(detail)
        if "/rental/" in urlsplit(detail_url).path:
            for node in root.descendants("script"):
                if node.attrs.get("type", "").lower() != "application/ld+json":
                    continue
                raw = "".join(
                    child for child in node.children if isinstance(child, str)
                ).strip()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if description := _product_description(payload):
                    return description
            return None
        for node in root.descendants():
            if {"mg-b20", "lh4"}.issubset(node.classes()):
                paragraphs = [
                    child
                    for child in node.descendants("p")
                    if "mg-b20" in child.classes()
                ]
                target = paragraphs[0] if paragraphs else node
                return target.text() or None
        return None


def _decode_detail_url(value: str) -> str:
    decoded = (
        value.replace(r"\/", "/")
        .replace(r"\u0026", "&")
        .replace(r"\u003d", "=")
        .replace(r"\u002f", "/")
    )
    return html.unescape(decoded)


def _is_safe_dmm_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "www.dmm.co.jp"
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
        and not parsed.query
        and not parsed.fragment
    )


def _canonical_detail_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.dmm.co.jp"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or "/detail/=/cid=" not in parsed.path
    ):
        return None
    return urlunsplit(("https", "www.dmm.co.jp", parsed.path, "", ""))


def _number_from_detail_url(value: str) -> str | None:
    match = _CID.search(urlsplit(value).path)
    if match is None:
        return None
    cid = html.unescape(match.group(1))
    padded = _PADDED_CID_NUMBER.search(cid)
    if padded is not None:
        return normalize_movie_number(
            f"{padded.group('prefix')}-{padded.group('number')}"
        )
    compact = _COMPACT_CID_NUMBER.search(cid)
    if compact is not None:
        return normalize_movie_number(
            f"{compact.group('prefix')}-{compact.group('number')}"
        )
    return normalize_movie_number(cid)


def _product_description(payload: object) -> str | None:
    if isinstance(payload, list):
        for item in payload:
            if description := _product_description(item):
                return description
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("@type", "")).lower() == "product":
        value = payload.get("description")
        if isinstance(value, str) and (description := html.unescape(value).strip()):
            return description
    for value in payload.values():
        if description := _product_description(value):
            return description
    return None


__all__ = ["DmmProvider"]
