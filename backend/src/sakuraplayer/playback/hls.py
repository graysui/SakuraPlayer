from __future__ import annotations

from sakuraplayer.cloud_cache.binding_service import BindingService
from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem, HlsVariant
from sakuraplayer.playback.session import StreamContext


class HlsStreamResolver:
    def __init__(self, binding_service: BindingService) -> None:
        self._binding_service = binding_service

    async def resolve(self, context: StreamContext) -> str:
        async with self._binding_service.cache_operation_scope(
            binding_id=context.binding_id,
            account_key=context.account_key,
            cache_root_cid=context.cache_root_cid,
        ) as cloud:
            info = await cloud.resolve_hls(context.pickcode, context.user_agent)
        if info.pickcode != context.pickcode:
            raise Cloud115Problem("cloud115_protocol_error")
        if not info.variants:
            raise Cloud115Problem("cloud115_hls_unavailable")
        if any(item.user_agent != context.user_agent for item in info.variants):
            raise Cloud115Problem("cloud115_protocol_error")
        return _highest_bandwidth(info.variants).url


def _highest_bandwidth(variants: tuple[HlsVariant, ...]) -> HlsVariant:
    return max(variants, key=lambda item: item.bandwidth)


__all__ = ["HlsStreamResolver"]
