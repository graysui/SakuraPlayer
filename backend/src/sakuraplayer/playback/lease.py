from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.models import CacheJob
from sakuraplayer.cloud_cache.ttl_lru import cache_timestamps, refresh_timestamps
from sakuraplayer.playback.models import PlaybackLease, PlaybackSession

DEFAULT_LEASE_DURATION = timedelta(seconds=90)


class PlaybackLeaseProblem(RuntimeError):
    code = "state_conflict"


@dataclass(frozen=True, slots=True)
class PlaybackLeaseView:
    id: uuid.UUID
    playback_session_id: uuid.UUID
    client_instance_id: uuid.UUID
    last_heartbeat_at: datetime
    expires_at: datetime
    ended_at: datetime | None


class PlaybackLeaseService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
        duration: timedelta = DEFAULT_LEASE_DURATION,
        ttl_hours: Callable[[], int] | None = None,
    ) -> None:
        if duration <= timedelta(0):
            raise ValueError("lease duration must be positive")
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._duration = duration
        self._ttl_hours = ttl_hours or (lambda: 24)

    def acquire(
        self,
        *,
        playback_session_id: uuid.UUID,
        client_instance_id: uuid.UUID,
    ) -> PlaybackLeaseView:
        current = self._now()
        with self._session_factory.begin() as session:
            playback = session.get(PlaybackSession, playback_session_id)
            if (
                playback is None
                or playback.revoked_at is not None
                or _as_utc(playback.expires_at) <= current
            ):
                raise PlaybackLeaseProblem
            cache_job = session.get(
                CacheJob, playback.cache_job_id, with_for_update=True
            )
            if cache_job is None or cache_job.status != "ready":
                raise PlaybackLeaseProblem
            playback = session.get(
                PlaybackSession,
                playback_session_id,
                populate_existing=True,
                with_for_update=True,
            )
            if (
                playback is None
                or playback.cache_job_id != cache_job.id
                or playback.revoked_at is not None
                or _as_utc(playback.expires_at) <= current
            ):
                raise PlaybackLeaseProblem
            ttl_hours = self._ttl_hours()
            timestamps = cache_timestamps(
                now=current,
                ttl_hours=ttl_hours,
                ready_at=cache_job.ready_at,
                last_accessed_at=cache_job.last_accessed_at,
                expires_at=cache_job.expires_at,
            )
            refreshed = refresh_timestamps(
                timestamps,
                now=current,
                ttl_hours=ttl_hours,
            )
            cache_job.last_accessed_at = refreshed.last_accessed_at
            cache_job.expires_at = refreshed.expires_at
            cache_job.updated_at = current
            expires_at = min(current + self._duration, _as_utc(playback.expires_at))
            lease = session.scalar(
                select(PlaybackLease)
                .where(
                    PlaybackLease.playback_session_id == playback_session_id,
                    PlaybackLease.client_instance_id == client_instance_id,
                )
                .with_for_update()
            )
            if lease is None:
                lease = PlaybackLease(
                    id=uuid.uuid4(),
                    playback_session_id=playback_session_id,
                    client_instance_id=client_instance_id,
                    last_heartbeat_at=current,
                    expires_at=expires_at,
                    ended_at=None,
                )
                session.add(lease)
            else:
                lease.last_heartbeat_at = current
                lease.expires_at = expires_at
                lease.ended_at = None
            session.flush()
            return _view(lease)

    def end(
        self,
        *,
        playback_session_id: uuid.UUID,
        client_instance_id: uuid.UUID,
    ) -> None:
        current = self._now()
        with self._session_factory.begin() as session:
            lease = session.scalar(
                select(PlaybackLease)
                .where(
                    PlaybackLease.playback_session_id == playback_session_id,
                    PlaybackLease.client_instance_id == client_instance_id,
                )
                .with_for_update()
            )
            if lease is not None and lease.ended_at is None:
                lease.ended_at = current

    def active_for_job(self, cache_job_id: uuid.UUID) -> bool:
        current = self._now()
        with self._session_factory() as session:
            return bool(
                session.scalar(
                    select(
                        exists().where(
                            PlaybackSession.cache_job_id == cache_job_id,
                            PlaybackLease.playback_session_id == PlaybackSession.id,
                            PlaybackLease.ended_at.is_(None),
                            PlaybackLease.expires_at > current,
                        )
                    )
                )
            )


def _view(lease: PlaybackLease) -> PlaybackLeaseView:
    return PlaybackLeaseView(
        id=lease.id,
        playback_session_id=lease.playback_session_id,
        client_instance_id=lease.client_instance_id,
        last_heartbeat_at=_as_utc(lease.last_heartbeat_at),
        expires_at=_as_utc(lease.expires_at),
        ended_at=_as_utc(lease.ended_at) if lease.ended_at is not None else None,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "DEFAULT_LEASE_DURATION",
    "PlaybackLeaseProblem",
    "PlaybackLeaseService",
    "PlaybackLeaseView",
]
