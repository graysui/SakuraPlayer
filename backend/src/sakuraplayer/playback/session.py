from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal, cast
from urllib.parse import urlencode

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    RemoteMedia,
    RemoteSubtitle,
)
from sakuraplayer.cloud_cache.ttl_lru import cache_timestamps, refresh_timestamps
from sakuraplayer.identity.domain import CurrentAdmin
from sakuraplayer.identity.models import AdminUser
from sakuraplayer.playback.lease import DEFAULT_LEASE_DURATION
from sakuraplayer.playback.models import PlaybackLease, PlaybackSession
from sakuraplayer.playback.subtitle_lifecycle import create_subtitle_lifecycle
from sakuraplayer.playback.user_agents import PlaybackPlatform, user_agent_for

PLAYBACK_SESSION_DURATION = timedelta(hours=12)
PlaybackMode = Literal["original", "compatibility"]


class PlaybackProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PlaybackMediaView:
    id: uuid.UUID
    candidate_id: uuid.UUID
    name: str
    size_bytes: int
    duration_seconds: int | None
    sequence_no: int
    is_valid: bool


@dataclass(frozen=True, slots=True)
class PlaybackSubtitleView:
    id: uuid.UUID
    media_id: uuid.UUID | None
    name: str
    format: str
    language: str | None
    selected_by_default: bool


@dataclass(frozen=True, slots=True)
class PlaybackQueueItem:
    session_id: uuid.UUID
    media: PlaybackMediaView
    stream_url: str


@dataclass(frozen=True, slots=True)
class PlaybackManifest:
    session_id: uuid.UUID
    cache_job_id: uuid.UUID
    mode: PlaybackMode
    platform: PlaybackPlatform
    stream_url: str
    expires_at: datetime
    subtitle_cache_expires_at: datetime
    required_user_agent: str
    embedded_tracks_source: Literal["client_player"]
    media_queue: tuple[PlaybackQueueItem, ...]
    subtitles: tuple[PlaybackSubtitleView, ...]


@dataclass(frozen=True, slots=True)
class StreamContext:
    binding_id: uuid.UUID
    account_key: str
    cache_root_cid: str
    pickcode: str
    user_agent: str
    mode: PlaybackMode


class PlaybackSessionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        signing_key: bytes,
        now: Callable[[], datetime] | None = None,
        ttl_hours: Callable[[], int] | None = None,
        lease_duration: timedelta = DEFAULT_LEASE_DURATION,
    ) -> None:
        if len(signing_key) < 32:
            raise ValueError("playback signing key must be at least 32 bytes")
        if lease_duration <= timedelta(0):
            raise ValueError("lease duration must be positive")
        self._session_factory = session_factory
        self._signing_key = signing_key
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._ttl_hours = ttl_hours or (lambda: 24)
        self._lease_duration = lease_duration

    def create(
        self,
        *,
        admin: CurrentAdmin,
        cache_job_id: uuid.UUID,
        media_id: uuid.UUID,
        mode: str,
        platform: PlaybackPlatform,
        client_instance_id: uuid.UUID,
    ) -> PlaybackManifest:
        if client_instance_id != admin.client_instance_id:
            raise PlaybackProblem(status_code=422, code="validation_failed")
        if mode not in {"original", "compatibility"}:
            raise PlaybackProblem(status_code=422, code="playback_mode_not_available")
        playback_mode = cast(PlaybackMode, mode)
        try:
            user_agent = user_agent_for(platform)
        except ValueError:
            raise PlaybackProblem(status_code=422, code="validation_failed") from None

        current = _as_utc(self._now())
        expires_at = current + PLAYBACK_SESSION_DURATION
        user_agent_hash = hashlib.sha256(user_agent.encode("utf-8")).hexdigest()
        with self._session_factory.begin() as session:
            job = session.get(CacheJob, cache_job_id, with_for_update=True)
            if job is None:
                raise PlaybackProblem(status_code=404, code="resource_not_found")
            if job.status != "ready":
                raise PlaybackProblem(status_code=409, code="state_conflict")
            media = list(
                session.scalars(
                    select(RemoteMedia)
                    .join(
                        CacheJobMediaSelection,
                        (
                            CacheJobMediaSelection.cache_job_id
                            == RemoteMedia.cache_job_id
                        )
                        & (CacheJobMediaSelection.media_id == RemoteMedia.id),
                    )
                    .where(
                        CacheJobMediaSelection.cache_job_id == job.id,
                        RemoteMedia.is_valid.is_(True),
                    )
                    .order_by(CacheJobMediaSelection.sequence_no)
                )
            )
            if not media or media_id not in {item.id for item in media}:
                raise PlaybackProblem(status_code=409, code="state_conflict")

            timestamps = cache_timestamps(
                now=current,
                ttl_hours=self._ttl_hours(),
                ready_at=job.ready_at,
                last_accessed_at=job.last_accessed_at,
                expires_at=job.expires_at,
            )
            refreshed = refresh_timestamps(
                timestamps,
                now=current,
                ttl_hours=self._ttl_hours(),
            )
            job.last_accessed_at = refreshed.last_accessed_at
            job.expires_at = refreshed.expires_at
            job.updated_at = current

            created: list[PlaybackSession] = []
            lease_expires_at = min(current + self._lease_duration, expires_at)
            for item in media:
                playback = PlaybackSession(
                    id=uuid.uuid4(),
                    admin_id=admin.admin_id,
                    session_epoch=admin.session_epoch,
                    movie_id=job.movie_id,
                    cache_job_id=job.id,
                    media_id=item.id,
                    mode=playback_mode,
                    platform=platform,
                    user_agent_hash=user_agent_hash,
                    issued_at=current,
                    expires_at=expires_at,
                    revoked_at=None,
                )
                session.add(playback)
                created.append(playback)
            session.flush()
            for playback in created:
                session.add(
                    PlaybackLease(
                        id=uuid.uuid4(),
                        playback_session_id=playback.id,
                        client_instance_id=client_instance_id,
                        last_heartbeat_at=current,
                        expires_at=lease_expires_at,
                        ended_at=None,
                    )
                )
            session.flush()
            subtitles = _subtitles(session, job.id, tuple(item.id for item in media))
            queue = tuple(
                PlaybackQueueItem(
                    session_id=playback.id,
                    media=_media_view(item),
                    stream_url=self._stream_url(playback, expires_at),
                )
                for playback, item in zip(created, media, strict=True)
            )
            entry = next(item for item in queue if item.media.id == media_id)
            subtitle_lifecycle = create_subtitle_lifecycle(
                cache_job_id=job.id, session_expires_at=expires_at
            )
            return PlaybackManifest(
                session_id=entry.session_id,
                cache_job_id=subtitle_lifecycle.cache_job_id,
                mode=playback_mode,
                platform=platform,
                stream_url=entry.stream_url,
                expires_at=expires_at,
                subtitle_cache_expires_at=subtitle_lifecycle.expires_at,
                required_user_agent=user_agent,
                embedded_tracks_source=subtitle_lifecycle.embedded_tracks_source,
                media_queue=queue,
                subtitles=subtitles,
            )

    def validate_stream(
        self,
        *,
        playback_session_id: uuid.UUID,
        expires: int,
        signature: str,
        user_agent: str,
    ) -> StreamContext:
        current = _as_utc(self._now())
        if expires <= int(current.timestamp()):
            raise PlaybackProblem(status_code=401, code="playback_signature_expired")
        with self._session_factory() as session:
            playback = session.get(PlaybackSession, playback_session_id)
            if playback is None:
                raise PlaybackProblem(
                    status_code=401, code="playback_signature_invalid"
                )
            expected_expires = int(_as_utc(playback.expires_at).timestamp())
            if expires != expected_expires or not hmac.compare_digest(
                self._signature(playback, expires), signature
            ):
                raise PlaybackProblem(
                    status_code=401, code="playback_signature_invalid"
                )
            if (
                playback.revoked_at is not None
                or _as_utc(playback.expires_at) <= current
            ):
                raise PlaybackProblem(
                    status_code=401, code="playback_signature_expired"
                )
            if playback.mode not in {"original", "compatibility"}:
                raise PlaybackProblem(
                    status_code=401, code="playback_signature_invalid"
                )
            admin = session.get(AdminUser, playback.admin_id)
            if admin is None or admin.session_epoch != playback.session_epoch:
                raise PlaybackProblem(status_code=401, code="playback_session_revoked")
            try:
                expected_user_agent = user_agent_for(playback.platform)  # type: ignore[arg-type]
            except ValueError:
                raise PlaybackProblem(
                    status_code=401, code="playback_signature_invalid"
                ) from None
            if not hmac.compare_digest(
                expected_user_agent, user_agent
            ) or not hmac.compare_digest(
                playback.user_agent_hash,
                hashlib.sha256(user_agent.encode("utf-8")).hexdigest(),
            ):
                raise PlaybackProblem(
                    status_code=403, code="playback_user_agent_mismatch"
                )
            active_lease = session.scalar(
                select(PlaybackLease.id)
                .where(
                    PlaybackLease.playback_session_id == playback.id,
                    PlaybackLease.ended_at.is_(None),
                    PlaybackLease.expires_at > current,
                )
                .limit(1)
            )
            if active_lease is None:
                raise PlaybackProblem(status_code=409, code="playback_media_detached")
            job = session.get(CacheJob, playback.cache_job_id)
            if job is None or job.status != "ready" or job.binding_id is None:
                raise PlaybackProblem(status_code=409, code="playback_media_detached")
            media = session.scalar(
                select(RemoteMedia)
                .join(
                    CacheJobMediaSelection,
                    (CacheJobMediaSelection.cache_job_id == RemoteMedia.cache_job_id)
                    & (CacheJobMediaSelection.media_id == RemoteMedia.id),
                )
                .where(
                    RemoteMedia.cache_job_id == job.id,
                    RemoteMedia.id == playback.media_id,
                    RemoteMedia.is_valid.is_(True),
                )
            )
            if media is None:
                raise PlaybackProblem(status_code=409, code="playback_media_detached")
            return StreamContext(
                binding_id=job.binding_id,
                account_key=job.account_key,
                cache_root_cid=job.cache_root_cid,
                pickcode=media.pickcode,
                user_agent=expected_user_agent,
                mode=cast(PlaybackMode, playback.mode),
            )

    def _stream_url(self, playback: PlaybackSession, expires_at: datetime) -> str:
        expires = int(_as_utc(expires_at).timestamp())
        query = urlencode(
            {"expires": expires, "signature": self._signature(playback, expires)}
        )
        return f"/api/v1/playback/streams/{playback.id}?{query}"

    def _signature(self, playback: PlaybackSession, expires: int) -> str:
        payload = "\n".join(
            (
                "v1",
                str(playback.id),
                str(playback.admin_id),
                str(playback.session_epoch),
                playback.mode,
                playback.user_agent_hash,
                str(expires),
            )
        ).encode("utf-8")
        return hmac.new(self._signing_key, payload, hashlib.sha256).hexdigest()


def _media_view(media: RemoteMedia) -> PlaybackMediaView:
    return PlaybackMediaView(
        id=media.id,
        candidate_id=media.candidate_id,
        name=media.name,
        size_bytes=media.size_bytes,
        duration_seconds=media.duration_seconds,
        sequence_no=media.sequence_no,
        is_valid=media.is_valid,
    )


def _subtitles(
    session: Session,
    cache_job_id: uuid.UUID,
    selected_media_ids: tuple[uuid.UUID, ...],
) -> tuple[PlaybackSubtitleView, ...]:
    rows = list(
        session.scalars(
            select(RemoteSubtitle)
            .where(
                RemoteSubtitle.cache_job_id == cache_job_id,
                or_(
                    RemoteSubtitle.media_id.is_(None),
                    RemoteSubtitle.media_id.in_(selected_media_ids),
                ),
            )
            .order_by(
                RemoteSubtitle.match_score.desc(),
                RemoteSubtitle.name,
                RemoteSubtitle.id,
            )
        )
    )
    return tuple(
        PlaybackSubtitleView(
            id=row.id,
            media_id=row.media_id,
            name=row.name,
            format=row.extension,
            language=None,
            selected_by_default=row.media_id in selected_media_ids,
        )
        for row in rows
    )


def _as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


__all__ = [
    "PlaybackManifest",
    "PlaybackMode",
    "PlaybackProblem",
    "PlaybackQueueItem",
    "PlaybackSessionService",
    "StreamContext",
]
