from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from sakuraplayer.cloud_cache.ttl_lru import (
    cache_timestamps,
    lru_order_key,
    refresh_timestamps,
)

NOW = datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("ttl_hours", [1, 24, 168])
def test_materialized_cache_initializes_server_timestamps(ttl_hours: int) -> None:
    timestamps = cache_timestamps(now=NOW, ttl_hours=ttl_hours)

    assert timestamps.ready_at == NOW
    assert timestamps.last_accessed_at == NOW
    assert timestamps.expires_at == NOW + timedelta(hours=ttl_hours)


@pytest.mark.parametrize("ttl_hours", [0, 169])
def test_ttl_rejects_values_outside_contract(ttl_hours: int) -> None:
    with pytest.raises(ValueError, match="ttl_hours"):
        cache_timestamps(now=NOW, ttl_hours=ttl_hours)


def test_ready_transition_preserves_existing_materialization_clock() -> None:
    original = cache_timestamps(now=NOW, ttl_hours=24)

    assert (
        cache_timestamps(
            now=NOW + timedelta(hours=3),
            ttl_hours=48,
            ready_at=original.ready_at,
            last_accessed_at=original.last_accessed_at,
            expires_at=original.expires_at,
        )
        == original
    )


def test_successful_access_refreshes_only_sliding_access_window() -> None:
    original = cache_timestamps(now=NOW, ttl_hours=24)
    refreshed = refresh_timestamps(
        original,
        now=NOW + timedelta(hours=4),
        ttl_hours=48,
    )

    assert refreshed.ready_at == NOW
    assert refreshed.last_accessed_at == NOW + timedelta(hours=4)
    assert refreshed.expires_at == NOW + timedelta(hours=52)


def test_lru_key_is_stable_for_null_and_equal_timestamps() -> None:
    first_id = uuid.UUID(int=1)
    second_id = uuid.UUID(int=2)
    created = NOW - timedelta(days=1)

    assert lru_order_key(None, None, created, first_id) < lru_order_key(
        NOW, NOW, created, first_id
    )
    assert lru_order_key(NOW, NOW, created, first_id) < lru_order_key(
        NOW, NOW, created, second_id
    )
