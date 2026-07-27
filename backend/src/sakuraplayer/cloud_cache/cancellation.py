from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.capacity import acquire_capacity_lock
from sakuraplayer.cloud_cache.domain.cache_job import (
    CacheJobState,
    CacheJobStatus,
    CapacityClass,
    InvalidCacheJobTransition,
)
from sakuraplayer.cloud_cache.models import CacheJob

_CANCELLABLE = {
    CacheJobStatus.QUEUED,
    CacheJobStatus.SUBMITTING,
    CacheJobStatus.OFFLINING,
    CacheJobStatus.SUBMIT_UNCERTAIN,
    CacheJobStatus.RESOLVING,
}


class CacheCancelProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CancellationView:
    id: uuid.UUID
    status: str


class CancellationService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def request(self, job_id: uuid.UUID, *, confirmed: bool) -> CancellationView:
        if not confirmed:
            raise CacheCancelProblem(
                status_code=409,
                code="cache_cancel_confirmation_required",
            )
        with self._session_factory.begin() as session:
            acquire_capacity_lock(session)
            job = session.get(CacheJob, job_id, with_for_update=True)
            if job is None:
                raise CacheCancelProblem(status_code=404, code="cache_job_not_found")
            current_status = CacheJobStatus(job.status)
            if current_status in {CacheJobStatus.CANCELLING, CacheJobStatus.CLEANING}:
                return CancellationView(job.id, job.status)
            if current_status not in _CANCELLABLE:
                raise CacheCancelProblem(status_code=409, code="state_conflict")
            mkdir_in_flight = (
                current_status is CacheJobStatus.SUBMITTING
                and job.task_dir_cid is None
                and job.submit_started_at is None
                and job.remote_info_hash is None
                and job.claim_owner is not None
            )
            try:
                self._apply_state(job, CacheJobStatus.CANCELLING)
            except InvalidCacheJobTransition:
                raise CacheCancelProblem(
                    status_code=409, code="state_conflict"
                ) from None
            if not mkdir_in_flight:
                self._clear_claim(job)
            if (
                job.task_dir_cid is None
                and job.submit_started_at is None
                and job.remote_info_hash is None
                and not mkdir_in_flight
            ):
                self._apply_state(job, CacheJobStatus.CLEANING)
                self._apply_state(job, CacheJobStatus.CLEANED)
            elif job.task_dir_cid is not None and job.submit_started_at is None:
                self._apply_state(job, CacheJobStatus.CLEANING)
            job.failure_code = None
            job.failure_detail = None
            job.updated_at = self._now()
            session.flush()
            return CancellationView(job.id, job.status)

    @staticmethod
    def _apply_state(job: CacheJob, target: CacheJobStatus) -> None:
        next_state = CacheJobState(
            CacheJobStatus(job.status),
            CapacityClass(job.capacity_class),
        ).transition(target)
        job.status = next_state.status.value
        job.capacity_class = next_state.capacity_class.value

    @staticmethod
    def _clear_claim(job: CacheJob) -> None:
        job.claim_owner = None
        job.claim_token = None
        job.claim_expires_at = None


__all__ = ["CacheCancelProblem", "CancellationService", "CancellationView"]
