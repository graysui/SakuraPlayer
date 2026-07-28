from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

EMBEDDED_TRACKS_SOURCE: Literal["client_player"] = "client_player"
CACHE_CLEANED_EVENT = "cache.job.cleaned.v1"


@dataclass(frozen=True, slots=True)
class SubtitleLifecycle:
    cache_job_id: uuid.UUID
    expires_at: datetime
    embedded_tracks_source: Literal["client_player"] = EMBEDDED_TRACKS_SOURCE

    def is_expired(self, *, now: datetime) -> bool:
        return _as_utc(now) >= _as_utc(self.expires_at)

    def matches_cache_event(self, *, event_type: str, resource_id: uuid.UUID) -> bool:
        return event_type == CACHE_CLEANED_EVENT and resource_id == self.cache_job_id


def create_subtitle_lifecycle(
    *, cache_job_id: uuid.UUID, session_expires_at: datetime
) -> SubtitleLifecycle:
    return SubtitleLifecycle(
        cache_job_id=cache_job_id,
        expires_at=_as_utc(session_expires_at),
    )


def _as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


__all__ = [
    "CACHE_CLEANED_EVENT",
    "EMBEDDED_TRACKS_SOURCE",
    "SubtitleLifecycle",
    "create_subtitle_lifecycle",
]
