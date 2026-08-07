from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import and_, case, delete, or_, select
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
from sakuraplayer.cloud_cache.events import CacheEventPublisher
from sakuraplayer.cloud_cache.failure_classifier import DETERMINISTIC_FAILURE_CODES
from sakuraplayer.cloud_cache.file_scanner import file_extension
from sakuraplayer.cloud_cache.media_selection import MediaSelectionPlan
from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    RemoteMedia,
    RemoteSubtitle,
)
from sakuraplayer.cloud_cache.ports.cloud115 import OfflineStatus, OfflineTaskSnapshot
from sakuraplayer.cloud_cache.subtitle_locator import LocatedSubtitle
from sakuraplayer.cloud_cache.ttl_lru import cache_timestamps
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.resources.models import Movie

DEFAULT_CLAIM_LEASE = timedelta(seconds=90)
DEFAULT_RETRY_DELAY = timedelta(seconds=5)
OFFLINE_POLL_DELAY = timedelta(seconds=2)
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
        ttl_hours: Callable[[], int] | None = None,
        lease: timedelta = DEFAULT_CLAIM_LEASE,
        event_writer: DomainEventWriter | None = None,
        event_publisher: CacheEventPublisher | None = None,
    ) -> None:
        if lease <= timedelta(0):
            raise ValueError("claim lease must be positive")
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._ttl_hours = ttl_hours or (lambda: 24)
        self._lease = lease
        self._event_writer = event_writer or DomainEventWriter(now=self._now)
        self._event_publisher = event_publisher

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
                        and_(
                            CacheJob.status == CacheJobStatus.OFFLINING.value,
                            CacheJob.updated_at <= current - OFFLINE_POLL_DELAY,
                        ),
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
            started_from_queue = False
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
                    started_from_queue = True
            if job is None:
                return None
            job.claim_owner = worker_id
            job.claim_token = uuid.uuid4()
            job.claim_expires_at = current + self._lease
            job.updated_at = current
            session.flush()
            if started_from_queue and self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.updated.v1",
                    notification_type="cache_started",
                )
            return self._claim(job)

    def claim_resolving(self, *, worker_id: str) -> CacheJobClaim | None:
        if not worker_id or len(worker_id) > 128:
            raise ValueError("worker_id must be 1..128 characters")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = session.scalar(
                select(CacheJob)
                .where(
                    CacheJob.status == CacheJobStatus.RESOLVING.value,
                    or_(
                        CacheJob.claim_owner.is_(None),
                        CacheJob.claim_expires_at <= current,
                    ),
                )
                .order_by(CacheJob.created_at, CacheJob.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.claim_owner = worker_id
            job.claim_token = uuid.uuid4()
            job.claim_expires_at = current + self._lease
            job.updated_at = current
            session.flush()
            return self._claim(job)

    def resolution_movie_number(self, claim: CacheJobClaim) -> str:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            if job.status != CacheJobStatus.RESOLVING.value:
                raise CacheJobClaimLost
            movie = session.get(Movie, job.movie_id)
            if movie is None:
                raise CacheJobClaimLost
            job.claim_expires_at = current + self._lease
            job.updated_at = current
            return movie.normalized_number

    def complete_resolution(
        self,
        claim: CacheJobClaim,
        plan: MediaSelectionPlan,
        subtitles: tuple[LocatedSubtitle, ...],
    ) -> None:
        if not plan.media:
            raise ValueError("resolution requires media")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            if job.status != CacheJobStatus.RESOLVING.value:
                raise CacheJobClaimLost
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

            candidate_ids = {
                media_item.candidate_key: uuid.uuid5(
                    job.id, f"candidate:{media_item.candidate_key}"
                )
                for media_item in plan.media
            }
            media_ids = {
                media_item.file.file_id: uuid.uuid5(
                    job.id, f"media:{media_item.file.file_id}"
                )
                for media_item in plan.media
            }
            for media_item in plan.media:
                session.add(
                    RemoteMedia(
                        id=media_ids[media_item.file.file_id],
                        cache_job_id=job.id,
                        file_id=media_item.file.file_id,
                        pickcode=media_item.file.pickcode,
                        parent_cid=media_item.file.parent_cid,
                        name=media_item.file.name,
                        size_bytes=media_item.file.size_bytes,
                        duration_seconds=media_item.file.duration_seconds,
                        candidate_id=candidate_ids[media_item.candidate_key],
                        sequence_no=media_item.sequence_no,
                        selection_score=media_item.selection_score,
                        selection_evidence=[
                            {"reason": reason, "value": value}
                            for reason, value in media_item.selection_evidence
                        ],
                        is_valid=True,
                        created_at=current,
                    )
                )
            session.flush()
            for subtitle_item in subtitles:
                session.add(
                    RemoteSubtitle(
                        id=uuid.uuid5(job.id, f"subtitle:{subtitle_item.file.file_id}"),
                        cache_job_id=job.id,
                        media_id=(
                            media_ids[subtitle_item.media_file_id]
                            if subtitle_item.media_file_id is not None
                            else None
                        ),
                        file_id=subtitle_item.file.file_id,
                        pickcode=subtitle_item.file.pickcode,
                        parent_cid=subtitle_item.file.parent_cid,
                        name=subtitle_item.file.name,
                        extension=file_extension(subtitle_item.file.name),
                        size_bytes=subtitle_item.file.size_bytes,
                        match_score=subtitle_item.match_score,
                        match_evidence=list(subtitle_item.match_evidence),
                        created_at=current,
                    )
                )
            if plan.selected_candidate_key is not None:
                selected = sorted(
                    (
                        media_item
                        for media_item in plan.media
                        if media_item.candidate_key == plan.selected_candidate_key
                    ),
                    key=lambda media_item: media_item.sequence_no,
                )
                for sequence_no, selected_item in enumerate(selected):
                    session.add(
                        CacheJobMediaSelection(
                            cache_job_id=job.id,
                            sequence_no=sequence_no,
                            media_id=media_ids[selected_item.file.file_id],
                        )
                    )
                target = CacheJobStatus.READY
            else:
                target = CacheJobStatus.AWAITING_SELECTION
            timestamps = cache_timestamps(
                now=current,
                ttl_hours=self._ttl_hours(),
                ready_at=job.ready_at,
                last_accessed_at=job.last_accessed_at,
                expires_at=job.expires_at,
            )
            job.ready_at = timestamps.ready_at
            job.last_accessed_at = timestamps.last_accessed_at
            job.expires_at = timestamps.expires_at
            self._apply_state(job, target)
            self._clear_claim(job)
            job.failure_code = None
            job.failure_detail = None
            job.failure_stage = None
            job.updated_at = current
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type=(
                        "cache.job.ready.v1"
                        if target is CacheJobStatus.READY
                        else "cache.job.selection_required.v1"
                    ),
                    notification_type=(
                        "cache_ready" if target is CacheJobStatus.READY else None
                    ),
                )

    def detach(self, claim: CacheJobClaim) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            if job.status != CacheJobStatus.RESOLVING.value:
                raise CacheJobClaimLost
            failure_stage = job.status
            self._apply_state(job, CacheJobStatus.DETACHED)
            self._clear_claim(job)
            job.failure_code = "cache_ownership_mismatch"
            job.failure_detail = None
            job.failure_stage = failure_stage
            job.updated_at = current
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.detached.v1",
                )

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
            job.failure_stage = None
            job.updated_at = current
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.updated.v1",
                )

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
            job.failure_stage = CacheJobStatus.SUBMITTING.value
            job.updated_at = current
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.updated.v1",
                )

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
            previous_percent = float(job.remote_percent)
            previous_status = job.status
            job.remote_percent = snapshot.percent_done
            if snapshot.status is OfflineStatus.COMPLETED:
                self._apply_state(job, CacheJobStatus.RESOLVING)
                job.remote_percent = 100
                job.failure_code = None
                job.failure_stage = None
            elif snapshot.status is OfflineStatus.FAILED:
                self._apply_state(job, CacheJobStatus.FAILED)
                job.failure_code = "cloud115_offline_failed"
                job.failure_stage = previous_status
            if snapshot.status in {OfflineStatus.COMPLETED, OfflineStatus.FAILED}:
                self._clear_claim(job)
            else:
                job.claim_expires_at = current + self._lease
                job.failure_code = None
                job.failure_detail = None
            job.updated_at = current
            if self._event_publisher is not None and (
                job.status != previous_status
                or float(job.remote_percent) != previous_percent
            ):
                failed = job.status == CacheJobStatus.FAILED.value
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type=(
                        "cache.job.failed.v1" if failed else "cache.job.updated.v1"
                    ),
                    notification_type="cache_failed" if failed else None,
                )

    def complete_cancel(self, claim: CacheJobClaim) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            job.cleanup_reason = "cancelled"
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
            job.failure_stage = None
            job.updated_at = current
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type=(
                        "cache.job.cancelled.v1"
                        if target is CacheJobStatus.CLEANED
                        else "cache.job.updated.v1"
                    ),
                    extra={"cleanup_reason": "cancelled"},
                )

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

    def fail(self, claim: CacheJobClaim, code: str) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            failure_stage = job.status
            self._apply_state(job, CacheJobStatus.FAILED)
            self._clear_claim(job)
            job.failure_code = code
            job.failure_detail = None
            job.failure_stage = failure_stage
            job.updated_at = current
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.failed.v1",
                    notification_type="cache_failed",
                )

    def fail_rejected(self, claim: CacheJobClaim, code: str) -> None:
        if code not in DETERMINISTIC_FAILURE_CODES:
            raise ValueError("failure code is not a deterministic source rejection")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._claimed_job(session, claim, current=current)
            failure_stage = job.status
            self._apply_state(job, CacheJobStatus.FAILED)
            self._clear_claim(job)
            job.failure_code = code
            job.failure_detail = None
            job.failure_stage = failure_stage
            job.updated_at = current
            self._event_writer.append(
                session,
                stream="cache",
                aggregate_id=job.id,
                event_type="cache.job.failed.v1",
                payload={
                    "id": str(job.id),
                    "status": CacheJobStatus.FAILED.value,
                    "error_code": code,
                    "rejected_source": True,
                },
            )
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.failed.v1",
                    notification_type="cache_failed",
                    publish_event=False,
                )

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
            if self._event_publisher is not None:
                self._event_publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.updated.v1",
                )

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
