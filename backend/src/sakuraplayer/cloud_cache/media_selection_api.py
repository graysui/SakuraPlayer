from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.domain.cache_job import (
    CacheJobState,
    CacheJobStatus,
    CapacityClass,
)
from sakuraplayer.cloud_cache.events import CacheEventPublisher
from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    RemoteMedia,
)
from sakuraplayer.cloud_cache.ttl_lru import cache_timestamps


class MediaSelectionProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MediaSelectionResult:
    status: str
    selected_media_ids: tuple[uuid.UUID, ...]


class MediaSelectionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
        ttl_hours: Callable[[], int] | None = None,
        event_publisher: CacheEventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._ttl_hours = ttl_hours or (lambda: 24)
        self._event_publisher = event_publisher

    def select(
        self,
        *,
        job_id: uuid.UUID,
        media_ids: tuple[uuid.UUID, ...],
    ) -> MediaSelectionResult:
        if not 1 <= len(media_ids) <= 100 or len(set(media_ids)) != len(media_ids):
            raise MediaSelectionProblem(status_code=422, code="validation_failed")
        with self._session_factory.begin() as session:
            job = session.get(CacheJob, job_id, with_for_update=True)
            if job is None:
                raise MediaSelectionProblem(status_code=404, code="cache_job_not_found")
            if job.status != CacheJobStatus.AWAITING_SELECTION.value:
                raise MediaSelectionProblem(status_code=409, code="state_conflict")
            requested = list(
                session.scalars(
                    select(RemoteMedia).where(
                        RemoteMedia.cache_job_id == job_id,
                        RemoteMedia.id.in_(media_ids),
                        RemoteMedia.is_valid.is_(True),
                    )
                )
            )
            candidate_ids = {item.candidate_id for item in requested}
            if len(requested) != len(media_ids) or len(candidate_ids) != 1:
                raise MediaSelectionProblem(status_code=409, code="state_conflict")
            candidate_id = next(iter(candidate_ids))
            candidate = list(
                session.scalars(
                    select(RemoteMedia)
                    .where(
                        RemoteMedia.cache_job_id == job_id,
                        RemoteMedia.candidate_id == candidate_id,
                        RemoteMedia.is_valid.is_(True),
                    )
                    .order_by(RemoteMedia.sequence_no, RemoteMedia.id)
                )
            )
            if {item.id for item in candidate} != set(media_ids):
                raise MediaSelectionProblem(status_code=409, code="state_conflict")
            session.execute(
                delete(CacheJobMediaSelection).where(
                    CacheJobMediaSelection.cache_job_id == job_id
                )
            )
            for sequence_no, item in enumerate(candidate):
                session.add(
                    CacheJobMediaSelection(
                        cache_job_id=job_id,
                        sequence_no=sequence_no,
                        media_id=item.id,
                    )
                )
            state = CacheJobState(
                CacheJobStatus(job.status), CapacityClass(job.capacity_class)
            ).transition(CacheJobStatus.READY)
            now = self._now()
            job.status = state.status.value
            job.capacity_class = state.capacity_class.value
            timestamps = cache_timestamps(
                now=now,
                ttl_hours=self._ttl_hours(),
                ready_at=job.ready_at,
                last_accessed_at=job.last_accessed_at,
                expires_at=job.expires_at,
            )
            job.ready_at = timestamps.ready_at
            job.last_accessed_at = timestamps.last_accessed_at
            job.expires_at = timestamps.expires_at
            job.updated_at = now
            job.failure_code = None
            job.failure_detail = None
            job.failure_stage = None
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.ready.v1",
                    notification_type="cache_ready",
                )
            return MediaSelectionResult(
                status=job.status,
                selected_media_ids=tuple(item.id for item in candidate),
            )


__all__ = [
    "MediaSelectionProblem",
    "MediaSelectionResult",
    "MediaSelectionService",
]
