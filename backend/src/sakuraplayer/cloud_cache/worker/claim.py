from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.capacity import (
    RUNNING_CAPACITY,
    acquire_capacity_lock,
    capacity_snapshot,
)
from sakuraplayer.cloud_cache.domain.cache_job import (
    CacheJobState,
    CacheJobStatus,
    CapacityClass,
)
from sakuraplayer.cloud_cache.models import CacheJob
from sakuraplayer.cloud_cache.ports.cloud115 import OfflineStatus, OfflineTaskSnapshot

DEFAULT_CLAIM_LEASE = timedelta(seconds=90)
DEFAULT_RETRY_DELAY = timedelta(seconds=5)
_CLAIMABLE = ("submitting", "offlining", "cancelling")


class CacheJobClaimLost(RuntimeError):
    code = "cache_job_claim_lost"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class CacheJobClaim:
    job_id: uuid.UUID
    movie_id: uuid.UUID
    source_id: uuid.UUID
    binding_id: uuid.UUID
    account_key: str
    cache_root_cid: str
    task_dir_name: str
    task_dir_cid: str | None
    remote_info_hash: str | None
    submit_started_at: datetime | None
    status: CacheJobStatus
    capacity_class: CapacityClass
    claim_owner: str
    claim_token: uuid.UUID
    claim_expires_at: datetime


class CacheJobClaimQueue:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
        lease: timedelta = DEFAULT_CLAIM_LEASE,
    ) -> None:
        if lease <= timedelta(0):
            raise ValueError("claim lease must be positive")
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._lease = lease

    def claim_next(self, *, worker_id: str) -> CacheJobClaim | None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("worker_id must be 1..128 characters")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            acquire_capacity_lock(session)
            job = session.scalar(
                select(CacheJob)
                .where(
                    CacheJob.status.in_(_CLAIMABLE),
                    or_(
                        CacheJob.claim_owner.is_(None),
                        CacheJob.claim_expires_at <= current,
                    ),
                )
                .order_by(
                    case(
                        (CacheJob.status == "cancelling", 0),
                        (CacheJob.status == "submitting", 1),
                        else_=2,
                    ),
                    CacheJob.created_at,
                    CacheJob.id,
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None and capacity_snapshot(session).running < RUNNING_CAPACITY:
                job = session.scalar(
                    select(CacheJob)
                    .where(CacheJob.status == "queued")
                    .order_by(CacheJob.created_at, CacheJob.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if job is not None:
                    self._apply_state(job, CacheJobStatus.SUBMITTING)
            if job is None:
                return None
            job.claim_owner = worker_id
            job.claim_token = uuid.uuid4()
            job.claim_expires_at = current + self._lease
            job.updated_at = current
            session.flush()
            return self._claim(job)

    def renew(self, claim: CacheJobClaim) -> CacheJobClaim:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            job.claim_expires_at = current + self._lease
            job.updated_at = current
            session.flush()
            return self._claim(job)

    def save_task_directory(
        self, claim: CacheJobClaim, task_dir_cid: str
    ) -> CacheJobClaim:
        if not task_dir_cid or len(task_dir_cid) > 64:
            raise ValueError("task directory cid must be 1..64 characters")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            if job.task_dir_cid is not None and job.task_dir_cid != task_dir_cid:
                raise CacheJobClaimLost
            job.task_dir_cid = task_dir_cid
            job.claim_expires_at = current + self._lease
            job.updated_at = current
            session.flush()
            return self._claim(job)

    def mark_submit_started(self, claim: CacheJobClaim) -> CacheJobClaim:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            if job.task_dir_cid is None or job.submit_started_at is not None:
                raise CacheJobClaimLost
            job.submit_started_at = current
            job.claim_expires_at = current + self._lease
            job.updated_at = current
            session.flush()
            return self._claim(job)

    def save_submission(self, claim: CacheJobClaim, info_hash: str) -> None:
        if not info_hash or len(info_hash) > 128:
            raise ValueError("remote info hash must be 1..128 characters")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            if job.task_dir_cid is None or job.submit_started_at is None:
                raise CacheJobClaimLost
            job.remote_info_hash = info_hash
            self._apply_state(job, CacheJobStatus.OFFLINING)
            self._clear_claim(job)
            job.failure_code = None
            job.failure_detail = None
            job.updated_at = current

    def mark_submit_uncertain(self, claim: CacheJobClaim) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            if job.task_dir_cid is None or job.submit_started_at is None:
                raise CacheJobClaimLost
            self._apply_state(job, CacheJobStatus.SUBMIT_UNCERTAIN)
            self._clear_claim(job)
            job.remote_info_hash = None
            job.failure_code = "cloud115_submit_uncertain"
            job.failure_detail = None
            job.updated_at = current

    def record_offline_snapshot(
        self,
        claim: CacheJobClaim,
        snapshot: OfflineTaskSnapshot,
    ) -> None:
        if not 0 <= snapshot.percent_done <= 100:
            raise ValueError("offline percent must be 0..100")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            if job.remote_info_hash != snapshot.info_hash:
                raise CacheJobClaimLost
            job.remote_percent = snapshot.percent_done
            if snapshot.status is OfflineStatus.COMPLETED:
                self._apply_state(job, CacheJobStatus.RESOLVING)
                job.remote_percent = 100
                job.failure_code = None
            elif snapshot.status is OfflineStatus.FAILED:
                self._apply_state(job, CacheJobStatus.FAILED)
                job.failure_code = "cloud115_offline_failed"
            if snapshot.status in {OfflineStatus.COMPLETED, OfflineStatus.FAILED}:
                self._clear_claim(job)
            else:
                job.claim_expires_at = current + DEFAULT_RETRY_DELAY
                job.failure_code = None
                job.failure_detail = None
            job.updated_at = current

    def complete_cancel(self, claim: CacheJobClaim) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            target = (
                CacheJobStatus.CLEANING
                if job.task_dir_cid is not None
                else CacheJobStatus.CLEANED
            )
            if target is CacheJobStatus.CLEANED:
                self._apply_state(job, CacheJobStatus.CLEANING)
            self._apply_state(job, target)
            self._clear_claim(job)
            job.failure_code = None
            job.failure_detail = None
            job.updated_at = current

    def save_cancel_target(
        self,
        claim: CacheJobClaim,
        info_hash: str,
    ) -> CacheJobClaim:
        if not info_hash or len(info_hash) > 128:
            raise ValueError("remote info hash must be 1..128 characters")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            if job.status != CacheJobStatus.CANCELLING.value:
                raise CacheJobClaimLost
            job.remote_info_hash = info_hash
            job.claim_expires_at = current + self._lease
            job.updated_at = current
            session.flush()
            return self._claim(job)

    def restore_submit_uncertain(self, claim: CacheJobClaim) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            self._apply_state(job, CacheJobStatus.SUBMIT_UNCERTAIN)
            self._clear_claim(job)
            job.failure_code = "cloud115_submit_uncertain"
            job.failure_detail = None
            job.updated_at = current

    def fail(self, claim: CacheJobClaim, code: str) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            self._apply_state(job, CacheJobStatus.FAILED)
            self._clear_claim(job)
            job.failure_code = code
            job.failure_detail = None
            job.updated_at = current

    def defer(
        self,
        claim: CacheJobClaim,
        code: str,
        *,
        delay: timedelta = DEFAULT_RETRY_DELAY,
    ) -> None:
        if delay <= timedelta(0):
            raise ValueError("retry delay must be positive")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            job.claim_expires_at = current + min(delay, timedelta(days=1))
            job.failure_code = code
            job.failure_detail = None
            job.updated_at = current

    def _claimed_job(
        self,
        session: Session,
        claim: CacheJobClaim,
        *,
        current: datetime,
    ) -> CacheJob:
        job = session.get(CacheJob, claim.job_id, with_for_update=True)
        if (
            job is None
            or job.claim_owner != claim.claim_owner
            or job.claim_token != claim.claim_token
            or job.claim_expires_at is None
            or self._as_utc(job.claim_expires_at) <= current
        ):
            raise CacheJobClaimLost
        return job

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

    @staticmethod
    def _claim(job: CacheJob) -> CacheJobClaim:
        if (
            job.binding_id is None
            or job.claim_owner is None
            or job.claim_token is None
            or job.claim_expires_at is None
        ):
            raise CacheJobClaimLost
        return CacheJobClaim(
            job_id=job.id,
            movie_id=job.movie_id,
            source_id=job.source_id,
            binding_id=job.binding_id,
            account_key=job.account_key,
            cache_root_cid=job.cache_root_cid,
            task_dir_name=job.task_dir_name,
            task_dir_cid=job.task_dir_cid,
            remote_info_hash=job.remote_info_hash,
            submit_started_at=job.submit_started_at,
            status=CacheJobStatus(job.status),
            capacity_class=CapacityClass(job.capacity_class),
            claim_owner=job.claim_owner,
            claim_token=job.claim_token,
            claim_expires_at=job.claim_expires_at,
        )

    def _utc_now(self) -> datetime:
        return self._as_utc(self._now())

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


__all__ = [
    "CacheJobClaim",
    "CacheJobClaimLost",
    "CacheJobClaimQueue",
    "DEFAULT_CLAIM_LEASE",
]
