from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest

from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    HlsInfo,
    HlsVariant,
    OriginalUrl,
)
from sakuraplayer.playback.fallback_policy import should_fallback_to_hls
from sakuraplayer.playback.hls import HlsStreamResolver
from sakuraplayer.playback.original import OriginalStreamResolver
from sakuraplayer.playback.resolver import PlaybackStreamResolver
from sakuraplayer.playback.session import StreamContext
from sakuraplayer.playback.stream_api import (
    PlaybackManifestOutput,
    PlaybackSessionInput,
)
from sakuraplayer.playback.user_agents import WINDOWS_USER_AGENT
from tests.fakes.cloud115 import FakeCloud115


class CloudScopeStub:
    def __init__(self, fake: FakeCloud115) -> None:
        self._fake = fake

    @asynccontextmanager
    async def cache_operation_scope(
        self, **_kwargs: object
    ) -> AsyncIterator[FakeCloud115]:
        yield self._fake


def _context(mode: str = "compatibility") -> StreamContext:
    return StreamContext(
        binding_id=uuid.uuid4(),
        account_key="account",
        cache_root_cid="root",
        pickcode="pickcode",
        user_agent=WINDOWS_USER_AGENT,
        mode=mode,
    )


def _variant(url: str, bandwidth: int, *, user_agent: str = WINDOWS_USER_AGENT):
    return HlsVariant(
        url=url,
        bandwidth=bandwidth,
        resolution="1920x1080",
        label="fixture",
        user_agent=user_agent,
    )


@pytest.mark.asyncio
async def test_hls_selects_first_highest_bandwidth_variant() -> None:
    fake = FakeCloud115(
        hls_infos=[
            HlsInfo(
                pickcode="pickcode",
                variants=(
                    _variant("https://cdn.115.com/720.m3u8", 1_800_000),
                    _variant("https://cdn.115.com/1080-first.m3u8", 3_600_000),
                    _variant("https://cdn.115.com/1080-second.m3u8", 3_600_000),
                ),
            )
        ]
    )

    location = await HlsStreamResolver(CloudScopeStub(fake)).resolve(_context())  # type: ignore[arg-type]

    assert location == "https://cdn.115.com/1080-first.m3u8"
    assert fake.calls[0].operation == "resolve_hls"
    assert fake.calls[0].safe_arguments == ("pickcode", WINDOWS_USER_AGENT)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("info", "expected_code"),
    [
        (HlsInfo(pickcode="wrong", variants=()), "cloud115_protocol_error"),
        (HlsInfo(pickcode="pickcode", variants=()), "cloud115_hls_unavailable"),
        (
            HlsInfo(
                pickcode="pickcode",
                variants=(
                    _variant(
                        "https://cdn.115.com/wrong-ua.m3u8",
                        3_600_000,
                        user_agent="wrong-user-agent",
                    ),
                ),
            ),
            "cloud115_protocol_error",
        ),
    ],
)
async def test_hls_rejects_invalid_typed_result(
    info: HlsInfo, expected_code: str
) -> None:
    resolver = HlsStreamResolver(  # type: ignore[arg-type]
        CloudScopeStub(FakeCloud115(hls_infos=[info]))
    )

    with pytest.raises(Cloud115Problem, match=expected_code):
        await resolver.resolve(_context())


@pytest.mark.parametrize(
    "code",
    [
        "cloud115_credentials_expired",
        "cloud115_file_not_found",
        "cloud115_rate_limited",
        "cloud115_unavailable",
        "cloud115_protocol_error",
    ],
)
def test_only_original_unavailable_is_automatically_fallbackable(code: str) -> None:
    assert should_fallback_to_hls(code) is False


def test_original_unavailable_is_automatically_fallbackable() -> None:
    assert should_fallback_to_hls("cloud115_original_unavailable") is True


def test_public_contract_only_exposes_original_and_compatibility() -> None:
    expected = ["original", "compatibility"]

    assert (
        PlaybackSessionInput.model_json_schema()["properties"]["mode"]["enum"]
        == expected
    )
    assert (
        PlaybackManifestOutput.model_json_schema()["properties"]["mode"]["enum"]
        == expected
    )


@pytest.mark.asyncio
async def test_original_success_does_not_call_hls() -> None:
    fake = FakeCloud115(
        original_urls=[
            OriginalUrl(
                url="https://cdn.115.com/original",
                expires_at=None,
                file_id="file",
                file_name="movie.mkv",
                file_size_bytes=300_000_000,
                sha1="sha1",
                pickcode="pickcode",
                user_agent=WINDOWS_USER_AGENT,
            )
        ]
    )
    resolver = PlaybackStreamResolver(
        OriginalStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
        HlsStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
    )

    location = await resolver.resolve(_context("original"))

    assert location == "https://cdn.115.com/original"
    assert [call.operation for call in fake.calls] == ["resolve_original"]


@pytest.mark.asyncio
async def test_concurrent_original_resolves_use_independent_capability_urls() -> None:
    urls = [f"https://cdn.115.com/original-{index}" for index in range(3)]
    fake = FakeCloud115(
        original_urls=[
            OriginalUrl(
                url=url,
                expires_at=None,
                file_id="file",
                file_name="movie.mkv",
                file_size_bytes=300_000_000,
                sha1="sha1",
                pickcode="pickcode",
                user_agent=WINDOWS_USER_AGENT,
            )
            for url in urls
        ]
    )
    resolver = OriginalStreamResolver(CloudScopeStub(fake))  # type: ignore[arg-type]
    context = _context("original")

    assert await asyncio.gather(*(resolver.resolve(context) for _ in range(3))) == urls
    assert [call.operation for call in fake.calls] == ["resolve_original"] * 3


@pytest.mark.asyncio
async def test_original_unavailable_falls_back_to_hls() -> None:
    fake = FakeCloud115(
        original_urls=[Cloud115Problem("cloud115_original_unavailable")],
        hls_infos=[
            HlsInfo(
                pickcode="pickcode",
                variants=(_variant("https://cdn.115.com/compat.m3u8", 3_600_000),),
            )
        ],
    )
    resolver = PlaybackStreamResolver(
        OriginalStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
        HlsStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
    )

    location = await resolver.resolve(_context("original"))

    assert location == "https://cdn.115.com/compat.m3u8"
    assert [call.operation for call in fake.calls] == [
        "resolve_original",
        "resolve_hls",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code",
    [
        "cloud115_credentials_expired",
        "cloud115_file_not_found",
        "cloud115_rate_limited",
        "cloud115_unavailable",
        "cloud115_protocol_error",
    ],
)
async def test_non_allowlisted_original_error_does_not_call_hls(code: str) -> None:
    fake = FakeCloud115(original_urls=[Cloud115Problem(code)])
    resolver = PlaybackStreamResolver(
        OriginalStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
        HlsStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
    )

    with pytest.raises(Cloud115Problem, match=code):
        await resolver.resolve(_context("original"))

    assert [call.operation for call in fake.calls] == ["resolve_original"]


@pytest.mark.asyncio
async def test_compatibility_calls_hls_without_original() -> None:
    fake = FakeCloud115(
        hls_infos=[
            HlsInfo(
                pickcode="pickcode",
                variants=(_variant("https://cdn.115.com/compat.m3u8", 3_600_000),),
            )
        ]
    )
    resolver = PlaybackStreamResolver(
        OriginalStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
        HlsStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
    )

    location = await resolver.resolve(_context())

    assert location == "https://cdn.115.com/compat.m3u8"
    assert [call.operation for call in fake.calls] == ["resolve_hls"]
