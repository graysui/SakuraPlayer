from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.models import CacheJob
from sakuraplayer.cloud_cache.ttl_lru import cache_timestamps, refresh_timestamps
from sakuraplayer.identity.domain import CurrentAdmin
from sakuraplayer.playback.lease import DEFAULT_LEASE_DURATION
from sakuraplayer.playback.models import PlaybackLease, PlaybackSession
from sakuraplayer.playback.progress import (
    MoviePlaybackStateService,
    MoviePlaybackStateView,
    ProgressUpdate,
)


class PlaybackHeartbeatProblem(RuntimeError):
    code = "state_conflict"


@dataclass(frozen=True, slots=True)
class PlaybackHeartbeatResult:
    lease_expires_at: datetime | None
    progress: MoviePlaybackStateView | None


class PlaybackHeartbeatService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        progress_service: MoviePlaybackStateService,
        now: Callable[[], datetime] | None = None,
        duration: timedelta = DEFAULT_LEASE_DURATION,
        ttl_hours: Callable[[], int] | None = None,
    ) -> None:
        if duration <= timedelta(0):
            raise ValueError("lease duration must be positive")
        self._session_factory = session_factory
        self._progress = progress_service
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._duration = duration
        self._ttl_hours = ttl_hours or (lambda: 24)

    def heartbeat(
        self,
        *,
        admin: CurrentAdmin,
        playback_session_id: uuid.UUID,
        client_instance_id: uuid.UUID,
        progress: ProgressUpdate | None,
        playing: bool,
    ) -> PlaybackHeartbeatResult:
        if client_instance_id != admin.client_instance_id:
            raise PlaybackHeartbeatProblem
        current = _as_utc(self._now())
        with self._session_factory.begin() as session:
            playback = session.get(PlaybackSession, playback_session_id)
            if playback is None:
                raise PlaybackHeartbeatProblem
            job = session.get(CacheJob, playback.cache_job_id, with_for_update=True)
            if job is None or job.status != "ready":
                raise PlaybackHeartbeatProblem
            playback = session.get(
                PlaybackSession,
                playback_session_id,
                populate_existing=True,
                with_for_update=True,
            )
            if (
                playback is None
                or playback.cache_job_id != job.id
                or playback.admin_id != admin.admin_id
                or playback.session_epoch != admin.session_epoch
                or playback.revoked_at is not None
                or _as_utc(playback.expires_at) <= current
            ):
                raise PlaybackHeartbeatProblem
            lease = session.scalar(
                select(PlaybackLease)
                .where(
                    PlaybackLease.playback_session_id == playback.id,
                    PlaybackLease.client_instance_id == client_instance_id,
                )
                .with_for_update()
            )
            if lease is None:
                raise PlaybackHeartbeatProblem

            authoritative = (
                self._progress.update_in_session(
                    session,
                    movie_id=playback.movie_id,
                    update=progress,
                )
                if progress is not None
                else self._progress.get_in_session(session, playback.movie_id)
            )
            if not playing:
                lease.ended_at = current
                session.flush()
                return PlaybackHeartbeatResult(
                    lease_expires_at=None,
                    progress=authoritative,
                )

            refreshed = refresh_timestamps(
                cache_timestamps(
                    now=current,
                    ttl_hours=self._ttl_hours(),
                    ready_at=job.ready_at,
                    last_accessed_at=job.last_accessed_at,
                    expires_at=job.expires_at,
                ),
                now=current,
                ttl_hours=self._ttl_hours(),
            )
            job.last_accessed_at = refreshed.last_accessed_at
            job.expires_at = refreshed.expires_at
            job.updated_at = current
            expires_at = min(current + self._duration, _as_utc(playback.expires_at))
            lease.last_heartbeat_at = current
            lease.expires_at = expires_at
            lease.ended_at = None
            session.flush()
            return PlaybackHeartbeatResult(
                lease_expires_at=expires_at,
                progress=authoritative,
            )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "PlaybackHeartbeatProblem",
    "PlaybackHeartbeatResult",
    "PlaybackHeartbeatService",
]
