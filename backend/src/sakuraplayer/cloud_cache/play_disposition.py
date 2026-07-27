from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

DispositionName = Literal["ready", "started", "queued", "reused"]
CLIENT_WAIT = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class PlayDisposition:
    name: DispositionName
    wait_deadline: datetime | None = None


def play_disposition(
    status: str,
    *,
    created: bool,
    replayed: bool = False,
    now: datetime,
) -> PlayDisposition:
    if replayed:
        return PlayDisposition("reused")
    if created and status == "submitting":
        return PlayDisposition("started", now + CLIENT_WAIT)
    if created and status == "queued":
        return PlayDisposition("queued")
    if status == "ready":
        return PlayDisposition("ready")
    return PlayDisposition("reused")


__all__ = ["CLIENT_WAIT", "DispositionName", "PlayDisposition", "play_disposition"]
