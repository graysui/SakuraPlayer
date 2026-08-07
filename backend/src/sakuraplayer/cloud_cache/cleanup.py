from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable as CallableABC
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import case, delete, exists, func, or_, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from sakuraplayer.cloud_cache.capacity import (
    READY_CAPACITY,
    acquire_capacity_lock,
    capacity_snapshot,
)
from sakuraplayer.cloud_cache.domain.cache_job import (
    CacheJobState,
    CacheJobStatus,
    CapacityClass,
    InvalidCacheJobTransition,
)
from sakuraplayer.cloud_cache.events import CacheEventPublisher
from sakuraplayer.cloud_cache.models import (
    CacheCleanupAttempt,
    CacheJob,
    CacheJobMediaSelection,
    RemoteMedia,
    RemoteSubtitle,
)
from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Port, Cloud115Problem
from sakuraplayer.playback.models import PlaybackLease, PlaybackSession

DEFAULT_CLEANUP_CLAIM_LEASE = timedelta(minutes=2)
# 115 删除/还原/移动互斥串行（p115client 参考）：目录删除响应时后台可能仍在执行，
# 后续删除返回 cloud115_operation_busy，短暂退避重试即可收敛。
_BUSY_RETRIES = 3
_BUSY_RETRY_DELAY = timedelta(seconds=5)
# busy 轮转重试上限：超过后转 cleanup_failed 供用户可见并手动重试，防止 115 删除队列
# 长期不收敛时任务永久占 cleaning/就绪容量。
_BUSY_MAX_ATTEMPTS = 60
_MATERIALIZED = (
    CacheJobStatus.AWAITING_SELECTION.value,
    CacheJobStatus.READY.value,
)


class CleanupProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class CleanupClaimLost(RuntimeError):
    code = "cache_job_claim_lost"


@dataclass(frozen=True, slots=True)
class CleanupClaim:
    job_id: uuid.UUID
    attempt_id: uuid.UUID
    attempt_no: int
    binding_id: uuid.UUID
    account_key: str
    cache_root_cid: str
    task_dir_cid: str
    task_dir_name: str
    claim_owner: str
    claim_token: uuid.UUID
    claim_expires_at: datetime


@dataclass(frozen=True, slots=True)
class CleanupRequestView:
    job_id: uuid.UUID
    status: str


class CleanupQueue:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
        claim_lease: timedelta = DEFAULT_CLEANUP_CLAIM_LEASE,
        event_publisher: CacheEventPublisher | None = None,
    ) -> None:
        if claim_lease <= timedelta(0):
            raise ValueError("cleanup claim lease must be positive")
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._claim_lease = claim_lease
        self._event_publisher = event_publisher

    def request(self, job_id: uuid.UUID) -> CleanupRequestView:
        current = self._now()
        with self._session_factory.begin() as session:
            acquire_capacity_lock(session)
            job = session.get(CacheJob, job_id, with_for_update=True)
            if job is None:
                raise CleanupProblem(status_code=404, code="cache_job_not_found")
            if _has_active_lease(session, job.id, current):
                raise CleanupProblem(status_code=409, code="cache_active_lease")
            status = CacheJobStatus(job.status)
            if status is CacheJobStatus.CLEANING:
                return CleanupRequestView(job.id, job.status)
            if status not in {
                CacheJobStatus.AWAITING_SELECTION,
                CacheJobStatus.READY,
                CacheJobStatus.CLEANUP_FAILED,
            }:
                raise CleanupProblem(status_code=409, code="state_conflict")
            if job.cleanup_reason is None:
                job.cleanup_reason = "manual"
            _apply_state(job, CacheJobStatus.CLEANING)
            _clear_claim(job)
            job.failure_code = None
            job.failure_detail = None
            job.failure_stage = None
            job.updated_at = current
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.updated.v1",
                    extra={"cleanup_reason": job.cleanup_reason},
                )
            return CleanupRequestView(job.id, job.status)

    def claim_next(self, *, worker_id: str) -> CleanupClaim | None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("invalid cleanup worker id")
        current = self._now()
        with self._session_factory.begin() as session:
            acquire_capacity_lock(session)
            available = or_(
                CacheJob.claim_owner.is_(None),
                CacheJob.claim_expires_at <= current,
            )
            no_active_lease = ~_active_lease_exists(CacheJob.id, current)
            auto_selected = False
            job = session.scalar(
                select(CacheJob)
                .where(
                    CacheJob.status == CacheJobStatus.CLEANING.value,
                    available,
                    no_active_lease,
                )
                .order_by(CacheJob.updated_at, CacheJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                cleaning = session.scalar(
                    select(func.count(CacheJob.id)).where(
                        CacheJob.status == CacheJobStatus.CLEANING.value
                    )
                )
                projected_ready = capacity_snapshot(session).ready - (cleaning or 0)
                over_target = projected_ready > READY_CAPACITY
                lifecycle_due = CacheJob.expires_at <= current
                eligible: ColumnElement[bool] = lifecycle_due
                if over_target:
                    eligible = or_(lifecycle_due, CacheJob.status.in_(_MATERIALIZED))
                job = session.scalar(
                    select(CacheJob)
                    .where(
                        CacheJob.status.in_(_MATERIALIZED),
                        eligible,
                        available,
                        no_active_lease,
                    )
                    .order_by(
                        case((lifecycle_due, 0), else_=1),
                        CacheJob.last_accessed_at.asc().nulls_first(),
                        CacheJob.ready_at.asc().nulls_first(),
                        CacheJob.created_at,
                        CacheJob.id,
                    )
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if job is not None:
                    assert job.expires_at is not None
                    job.cleanup_reason = (
                        "ttl" if _as_utc(job.expires_at) <= current else "capacity"
                    )
                    _apply_state(job, CacheJobStatus.CLEANING)
                    auto_selected = True
            if job is None:
                return None
            if job.binding_id is None or job.task_dir_cid is None:
                if job.cleanup_reason is None:
                    job.cleanup_reason = "manual"
                _apply_state(job, CacheJobStatus.DETACHED)
                _clear_claim(job)
                job.failure_code = "cache_ownership_mismatch"
                job.failure_detail = None
                job.failure_stage = CacheJobStatus.CLEANING.value
                job.updated_at = current
                if self._event_publisher is not None:
                    self._event_publisher.publish_cache(
                        session,
                        job,
                        event_type="cache.job.detached.v1",
                        extra={"cleanup_reason": job.cleanup_reason},
                    )
                return None

            prior = session.scalar(
                select(CacheCleanupAttempt)
                .where(
                    CacheCleanupAttempt.cache_job_id == job.id,
                    CacheCleanupAttempt.status == "running",
                )
                .with_for_update()
            )
            if prior is not None:
                prior.status = "failed"
                prior.failure_code = "cache_cleanup_failed"
                prior.finished_at = current
            attempt_no = (
                session.scalar(
                    select(func.max(CacheCleanupAttempt.attempt_no)).where(
                        CacheCleanupAttempt.cache_job_id == job.id
                    )
                )
                or 0
            ) + 1
            attempt = CacheCleanupAttempt(
                id=uuid.uuid4(),
                cache_job_id=job.id,
                attempt_no=attempt_no,
                ownership_evidence={},
                status="running",
                failure_code=None,
                started_at=current,
                finished_at=None,
            )
            session.add(attempt)
            job.claim_owner = worker_id
            job.claim_token = uuid.uuid4()
            job.claim_expires_at = current + self._claim_lease
            job.updated_at = current
            session.flush()
            if auto_selected and self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.updated.v1",
                    extra={"cleanup_reason": job.cleanup_reason},
                )
            return _claim(job, attempt)

    def succeed(
        self,
        claim: CleanupClaim,
        *,
        ownership_evidence: dict[str, object],
    ) -> None:
        current = self._now()
        with self._session_factory.begin() as session:
            job, attempt = self._claimed(session, claim, current)
            _apply_state(job, CacheJobStatus.CLEANED)
            attempt.status = "succeeded"
            attempt.ownership_evidence = ownership_evidence
            attempt.finished_at = current
            attempt.failure_code = None
            _clear_claim(job)
            job.failure_code = None
            job.failure_detail = None
            job.failure_stage = None
            job.updated_at = current
            session.execute(
                delete(CacheJobMediaSelection).where(
                    CacheJobMediaSelection.cache_job_id == job.id
                )
            )
            session.execute(
                delete(RemoteSubtitle).where(RemoteSubtitle.cache_job_id == job.id)
            )
            session.execute(
                delete(RemoteMedia).where(RemoteMedia.cache_job_id == job.id)
            )
            if self._event_publisher is not None:
                reason = job.cleanup_reason or "manual"
                job.cleanup_reason = reason
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type=(
                        "cache.job.cancelled.v1"
                        if reason == "cancelled"
                        else "cache.job.cleaned.v1"
                    ),
                    extra={"cleanup_reason": reason},
                )

    def fail(
        self,
        claim: CleanupClaim,
        *,
        failure_code: str,
        ownership_evidence: dict[str, object] | None = None,
    ) -> None:
        current = self._now()
        with self._session_factory.begin() as session:
            job, attempt = self._claimed(session, claim, current)
            _apply_state(job, CacheJobStatus.CLEANUP_FAILED)
            attempt.status = "failed"
            attempt.failure_code = failure_code
            attempt.ownership_evidence = ownership_evidence or {}
            attempt.finished_at = current
            _clear_claim(job)
            job.failure_code = "cache_cleanup_failed"
            job.failure_detail = None
            job.failure_stage = CacheJobStatus.CLEANING.value
            job.updated_at = current
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.cleanup_failed.v1",
                    extra={
                        "attempt_no": attempt.attempt_no,
                        "cleanup_reason": job.cleanup_reason,
                    },
                )

    def release(self, claim: CleanupClaim) -> None:
        """保持任务 cleaning、清除 claim、把 updated_at 置为当前时间，并终结本轮 attempt。

        claim_next 对 CLEANING 任务按 updated_at ASC 排序，刚释放的任务排到队尾，
        实现多个 busy 任务公平轮转；attempt 以 `cloud115_operation_busy` 记为 failed，
        与真实失败区分并保留重试证据，下次 claim 直接新建 attempt。
        """
        current = self._now()
        with self._session_factory.begin() as session:
            job, attempt = self._claimed(session, claim, current)
            _clear_claim(job)
            attempt.status = "failed"
            attempt.failure_code = "cloud115_operation_busy"
            attempt.finished_at = current
            job.updated_at = current
            session.flush()

    def detach(
        self,
        claim: CleanupClaim,
        *,
        ownership_evidence: dict[str, object],
    ) -> None:
        current = self._now()
        with self._session_factory.begin() as session:
            job, attempt = self._claimed(session, claim, current)
            _apply_state(job, CacheJobStatus.DETACHED)
            attempt.status = "detached"
            attempt.ownership_evidence = ownership_evidence
            attempt.finished_at = current
            attempt.failure_code = None
            _clear_claim(job)
            job.failure_code = "cache_ownership_mismatch"
            job.failure_detail = None
            job.failure_stage = CacheJobStatus.CLEANING.value
            job.updated_at = current
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.detached.v1",
                    extra={"cleanup_reason": job.cleanup_reason},
                )

    def _claimed(
        self,
        session: Session,
        claim: CleanupClaim,
        current: datetime,
    ) -> tuple[CacheJob, CacheCleanupAttempt]:
        job = session.get(CacheJob, claim.job_id, with_for_update=True)
        attempt = session.get(
            CacheCleanupAttempt, claim.attempt_id, with_for_update=True
        )
        if (
            job is None
            or attempt is None
            or job.status != CacheJobStatus.CLEANING.value
            or job.claim_owner != claim.claim_owner
            or job.claim_token != claim.claim_token
            or job.claim_expires_at is None
            or _as_utc(job.claim_expires_at) <= current
            or attempt.cache_job_id != job.id
            or attempt.status != "running"
        ):
            raise CleanupClaimLost
        return job, attempt


CleanupCloudScope = CallableABC[
    [CleanupClaim], AbstractAsyncContextManager[Cloud115Port]
]


class CleanupWorker:
    def __init__(
        self,
        queue: CleanupQueue,
        cloud_factory: CleanupCloudScope,
    ) -> None:
        self._queue = queue
        self._cloud_factory = cloud_factory

    def run_once(self, *, worker_id: str) -> str:
        claim = self._queue.claim_next(worker_id=worker_id)
        if claim is None:
            return "idle"
        try:
            asyncio.run(self._process(claim))
        except CleanupClaimLost:
            pass
        return "worked"

    async def _process(self, claim: CleanupClaim) -> None:
        from sakuraplayer.cloud_cache.ownership import (
            ownership_evidence,
            root_is_owned,
            task_is_owned,
        )

        evidence = ownership_evidence(claim)
        try:
            async with self._cloud_factory(claim) as cloud:
                try:
                    root = await cloud.directory_info(claim.cache_root_cid)
                except Cloud115Problem as error:
                    if error.code == "cloud115_directory_not_found":
                        self._queue.detach(
                            claim,
                            ownership_evidence=ownership_evidence(claim),
                        )
                        return
                    raise
                if not root_is_owned(claim, root):
                    self._queue.detach(
                        claim,
                        ownership_evidence=ownership_evidence(claim, root=root),
                    )
                    return
                try:
                    task = await cloud.directory_info(claim.task_dir_cid)
                except Cloud115Problem as error:
                    if error.code == "cloud115_directory_not_found":
                        self._queue.succeed(
                            claim,
                            ownership_evidence=ownership_evidence(
                                claim,
                                root=root,
                                task_missing=True,
                            ),
                        )
                        return
                    raise
                evidence = ownership_evidence(claim, root=root, task=task)
                if not task_is_owned(claim, task):
                    self._queue.detach(claim, ownership_evidence=evidence)
                    return
                if await self._delete_with_busy_retry(claim, cloud, evidence):
                    return
                self._queue.succeed(claim, ownership_evidence=evidence)
        except Cloud115Problem as error:
            if error.code == "cloud115_directory_not_found":
                self._queue.detach(
                    claim,
                    ownership_evidence=ownership_evidence(claim),
                )
            elif error.code == "cloud115_operation_busy":
                # 115 删除/还原/移动互斥繁忙（p115client 参考）：暂时性错误，不立即 fail。
                # 保持 cleaning、释放 claim 按 updated_at 轮转，由后续 claim 继续重试；
                # 超过轮转上限（115 队列长期不收敛）才转 cleanup_failed 供用户干预。
                if claim.attempt_no >= _BUSY_MAX_ATTEMPTS:
                    self._queue.fail(
                        claim,
                        failure_code="cache_cleanup_failed",
                        ownership_evidence=evidence,
                    )
                else:
                    self._queue.release(claim)
            else:
                self._queue.fail(
                    claim,
                    failure_code=error.code,
                    ownership_evidence=evidence,
                )

    async def _delete_with_busy_retry(
        self,
        claim: CleanupClaim,
        cloud: Cloud115Port,
        evidence: dict[str, object],
    ) -> bool:
        """返回 True 表示删除步骤已幂等终结（远端目标已不存在），调用方不再重复 succeed。"""
        for attempt in range(1, _BUSY_RETRIES + 1):
            try:
                await cloud.delete_managed_entries(
                    (claim.task_dir_cid,), claim.cache_root_cid
                )
                return False
            except Cloud115Problem as error:
                if error.code == "cloud115_file_not_found":
                    # 远端目标已不存在：证明式幂等成功。
                    self._queue.succeed(
                        claim,
                        ownership_evidence={**evidence, "delete_missing": True},
                    )
                    return True
                if error.code == "cloud115_operation_busy" and attempt < _BUSY_RETRIES:
                    await asyncio.sleep(_BUSY_RETRY_DELAY.total_seconds())
                    continue
                raise


def _active_lease_exists(cache_job_id, current: datetime):
    return exists(
        select(1)
        .select_from(PlaybackLease)
        .join(
            PlaybackSession,
            PlaybackSession.id == PlaybackLease.playback_session_id,
        )
        .where(
            PlaybackSession.cache_job_id == cache_job_id,
            PlaybackLease.ended_at.is_(None),
            PlaybackLease.expires_at > current,
        )
    )


def _has_active_lease(session: Session, job_id: uuid.UUID, current: datetime) -> bool:
    return bool(session.scalar(select(_active_lease_exists(job_id, current))))


def _apply_state(job: CacheJob, target: CacheJobStatus) -> None:
    try:
        state = CacheJobState(
            CacheJobStatus(job.status), CapacityClass(job.capacity_class)
        ).transition(target)
    except InvalidCacheJobTransition:
        raise CleanupProblem(status_code=409, code="state_conflict") from None
    job.status = state.status.value
    job.capacity_class = state.capacity_class.value


def _clear_claim(job: CacheJob) -> None:
    job.claim_owner = None
    job.claim_token = None
    job.claim_expires_at = None


def _claim(job: CacheJob, attempt: CacheCleanupAttempt) -> CleanupClaim:
    assert job.binding_id is not None
    assert job.task_dir_cid is not None
    assert job.claim_owner is not None
    assert job.claim_token is not None
    assert job.claim_expires_at is not None
    return CleanupClaim(
        job_id=job.id,
        attempt_id=attempt.id,
        attempt_no=attempt.attempt_no,
        binding_id=job.binding_id,
        account_key=job.account_key,
        cache_root_cid=job.cache_root_cid,
        task_dir_cid=job.task_dir_cid,
        task_dir_name=job.task_dir_name,
        claim_owner=job.claim_owner,
        claim_token=job.claim_token,
        claim_expires_at=_as_utc(job.claim_expires_at),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "CleanupClaim",
    "CleanupClaimLost",
    "CleanupCloudScope",
    "CleanupProblem",
    "CleanupQueue",
    "CleanupRequestView",
    "CleanupWorker",
]
