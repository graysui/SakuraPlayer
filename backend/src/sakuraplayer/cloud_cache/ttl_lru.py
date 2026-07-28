from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class CacheTimestamps:
    ready_at: datetime
    last_accessed_at: datetime
    expires_at: datetime


def cache_timestamps(
    *,
    now: datetime,
    ttl_hours: int,
    ready_at: datetime | None = None,
    last_accessed_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> CacheTimestamps:
    _validate_ttl(ttl_hours)
    if ready_at is None and last_accessed_at is None and expires_at is None:
        return CacheTimestamps(now, now, now + timedelta(hours=ttl_hours))
    if ready_at is None or last_accessed_at is None or expires_at is None:
        raise ValueError("materialized cache timestamps must be all null or all set")
    return CacheTimestamps(ready_at, last_accessed_at, expires_at)


def refresh_timestamps(
    timestamps: CacheTimestamps,
    *,
    now: datetime,
    ttl_hours: int,
) -> CacheTimestamps:
    _validate_ttl(ttl_hours)
    return CacheTimestamps(
        timestamps.ready_at,
        now,
        now + timedelta(hours=ttl_hours),
    )


def lru_order_key(
    last_accessed_at: datetime | None,
    ready_at: datetime | None,
    created_at: datetime,
    job_id: uuid.UUID,
) -> tuple[bool, datetime, bool, datetime, datetime, int]:
    return (
        last_accessed_at is not None,
        last_accessed_at or datetime.min.replace(tzinfo=created_at.tzinfo),
        ready_at is not None,
        ready_at or datetime.min.replace(tzinfo=created_at.tzinfo),
        created_at,
        job_id.int,
    )


def _validate_ttl(ttl_hours: int) -> None:
    if isinstance(ttl_hours, bool) or not 1 <= ttl_hours <= 168:
        raise ValueError("ttl_hours must be between 1 and 168")


__all__ = [
    "CacheTimestamps",
    "cache_timestamps",
    "lru_order_key",
    "refresh_timestamps",
]
