from __future__ import annotations

from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem
from sakuraplayer.playback.fallback_policy import should_fallback_to_hls
from sakuraplayer.playback.hls import HlsStreamResolver
from sakuraplayer.playback.original import OriginalStreamResolver
from sakuraplayer.playback.session import StreamContext


class PlaybackStreamResolver:
    def __init__(
        self,
        original: OriginalStreamResolver,
        hls: HlsStreamResolver,
    ) -> None:
        self._original = original
        self._hls = hls

    async def resolve(self, context: StreamContext) -> str:
        if context.mode == "compatibility":
            return await self._hls.resolve(context)
        if context.mode != "original":
            raise Cloud115Problem("cloud115_protocol_error")
        try:
            return await self._original.resolve(context)
        except Cloud115Problem as error:
            if not should_fallback_to_hls(error.code):
                raise
        return await self._hls.resolve(context)


__all__ = ["PlaybackStreamResolver"]
