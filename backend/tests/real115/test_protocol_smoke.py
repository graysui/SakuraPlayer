from __future__ import annotations

import pytest

from sakuraplayer.cloud_cache.infrastructure.cloud115.adapter import Cloud115Adapter
from sakuraplayer.cloud_cache.ports.cloud115 import CloudCredentialStatus

pytestmark = [pytest.mark.real115, pytest.mark.asyncio]


async def test_credentials_and_managed_root_are_readable(
    real115_configuration: tuple[str, str],
) -> None:
    cookie, root_cid = real115_configuration
    async with Cloud115Adapter(cookies=cookie) as adapter:
        probe = await adapter.probe_credentials()
        assert probe.status is CloudCredentialStatus.ALIVE
        root = await adapter.directory_info(root_cid)
    assert root.cid == root_cid
