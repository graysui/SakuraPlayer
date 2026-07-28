from __future__ import annotations

from sakuraplayer.cloud_cache.binding_service import BindingService
from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem
from sakuraplayer.playback.session import StreamContext


class OriginalStreamResolver:
    def __init__(self, binding_service: BindingService) -> None:
        self._binding_service = binding_service

    async def resolve(self, context: StreamContext) -> str:
        async with self._binding_service.cache_operation_scope(
            binding_id=context.binding_id,
            account_key=context.account_key,
            cache_root_cid=context.cache_root_cid,
        ) as cloud:
            original = await cloud.resolve_original(
                context.pickcode, context.user_agent
            )
        if (
            original.pickcode != context.pickcode
            or original.user_agent != context.user_agent
        ):
            raise Cloud115Problem("cloud115_protocol_error")
        return original.url


__all__ = ["OriginalStreamResolver"]
