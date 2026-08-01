from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.metadata_state import (
    ALL_STAGES,
    OPTIONAL_STAGES,
    MetadataStateError,
    priority_for_reason,
    stage_plan,
    validate_enrichment_stages,
)
from sakuraplayer.catalog.models import (
    MetadataJob,
    MetadataStage,
    MetadataWorkerControl,
)
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.resources.models import Movie
from sakuraplayer.shared.redaction import redact_text, stable_error_code

MAX_RUNNING_JOBS = 3
_SLOT_LOCK_KEY = 0x53414B5552410007
_RETRYABLE_ENRICHMENT_STATUSES = {"warning", "failed", "pending"}


class MetadataQueueProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class MetadataCandidateInput(Protocol):
    movie_id: uuid.UUID
    normalized_number: str
    publish_date: date | None
    reason: str


@dataclass(frozen=True)
class EnqueueOutcome:
    job_id: uuid.UUID
    created: bool


@dataclass(frozen=True)
class MetadataCompletionOutcome:
    job_id: uuid.UUID
    state: str


@dataclass(frozen=True)
class MetadataQueueControlSnapshot:
    paused: bool
    queued: int
    running: int


@dataclass(frozen=True)
class MetadataClaim:
    job_id: uuid.UUID
    movie_id: uuid.UUID
    normalized_number: str
    retry_mode: str
    requested_stages: tuple[str, ...]
    claim_owner: str
    claim_expires_at: datetime
    elapsed_ms: int
    pending_stages: tuple[str, ...]
    has_warnings: bool


class MetadataQueue:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
        event_writer: DomainEventWriter | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._event_writer = event_writer

    def enqueue(
        self,
        *,
        movie_id: uuid.UUID,
        normalized_number: str,
        sort_date: date | None,
        reason: str,
    ) -> EnqueueOutcome:
        priority = priority_for_reason(reason)
        current = self._utc_now()
        with self._session_factory.begin() as session:
            movie = session.get(Movie, movie_id, with_for_update=True)
            if movie is None or movie.normalized_number != normalized_number:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="resource_not_found",
                )
            existing = session.scalar(
                select(MetadataJob)
                .where(MetadataJob.normalized_number == normalized_number)
                .order_by(MetadataJob.attempt_no.desc())
                .limit(1)
            )
            if existing is not None:
                return EnqueueOutcome(existing.id, created=False)
            job = self._add_job(
                session,
                movie=movie,
                normalized_number=normalized_number,
                priority=priority,
                reason=reason,
                sort_date=sort_date,
                retry_mode="full",
                requested_stages=(),
                attempt_no=1,
                parent_job_id=None,
                created_at=current,
            )
            return EnqueueOutcome(job.id, created=True)

    def enqueue_candidates(
        self,
        candidates: Iterable[MetadataCandidateInput],
    ) -> list[EnqueueOutcome]:
        outcomes: list[EnqueueOutcome] = []
        for candidate in candidates:
            outcomes.append(
                self.enqueue(
                    movie_id=candidate.movie_id,
                    normalized_number=candidate.normalized_number,
                    sort_date=candidate.publish_date,
                    reason=candidate.reason,
                )
            )
        return outcomes

    def ensure_search_priority(
        self,
        *,
        movie_id: uuid.UUID,
        normalized_number: str,
        sort_date: date | None,
    ) -> MetadataCompletionOutcome:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            movie = session.get(Movie, movie_id, with_for_update=True)
            if movie is None or movie.normalized_number != normalized_number:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="resource_not_found",
                )
            existing = session.scalar(
                select(MetadataJob)
                .where(MetadataJob.normalized_number == normalized_number)
                .order_by(MetadataJob.attempt_no.desc())
                .limit(1)
                .with_for_update()
            )
            if existing is None:
                job = self._add_job(
                    session,
                    movie=movie,
                    normalized_number=normalized_number,
                    priority=priority_for_reason("manual_or_search"),
                    reason="manual_or_search",
                    sort_date=sort_date,
                    retry_mode="full",
                    requested_stages=(),
                    attempt_no=1,
                    parent_job_id=None,
                    created_at=current,
                )
                return MetadataCompletionOutcome(job.id, "queued")
            if movie.catalog_state == "core_ready":
                return MetadataCompletionOutcome(existing.id, "completed")
            if existing.status == "queued":
                changed = existing.priority != priority_for_reason("manual_or_search")
                existing.priority = priority_for_reason("manual_or_search")
                existing.reason = "manual_or_search"
                if sort_date is not None:
                    changed = changed or existing.sort_date != sort_date
                    existing.sort_date = sort_date
                if changed:
                    self._publish_job(
                        session,
                        existing,
                        event_type="metadata.job.queued.v1",
                    )
                return MetadataCompletionOutcome(existing.id, "queued")
            if existing.status == "running":
                return MetadataCompletionOutcome(existing.id, "running")
            return MetadataCompletionOutcome(existing.id, "failed")

    def ensure_ranking_priority(
        self,
        *,
        movie_id: uuid.UUID,
        normalized_number: str,
        sort_date: date | None,
    ) -> MetadataCompletionOutcome:
        current = self._utc_now()
        ranking_priority = priority_for_reason("ranking")
        with self._session_factory.begin() as session:
            movie = session.get(Movie, movie_id, with_for_update=True)
            if movie is None or movie.normalized_number != normalized_number:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="resource_not_found",
                )
            existing = session.scalar(
                select(MetadataJob)
                .where(MetadataJob.normalized_number == normalized_number)
                .order_by(MetadataJob.attempt_no.desc())
                .limit(1)
                .with_for_update()
            )
            if movie.catalog_state == "core_ready":
                return MetadataCompletionOutcome(
                    existing.id if existing is not None else movie.id,
                    "completed",
                )
            if existing is None:
                job = self._add_job(
                    session,
                    movie=movie,
                    normalized_number=normalized_number,
                    priority=ranking_priority,
                    reason="ranking",
                    sort_date=sort_date,
                    retry_mode="full",
                    requested_stages=(),
                    attempt_no=1,
                    parent_job_id=None,
                    created_at=current,
                )
                return MetadataCompletionOutcome(job.id, "queued")
            if existing.status == "queued":
                if existing.priority > ranking_priority:
                    existing.priority = ranking_priority
                    existing.reason = "ranking"
                    if sort_date is not None:
                        existing.sort_date = sort_date
                    self._publish_job(
                        session,
                        existing,
                        event_type="metadata.job.queued.v1",
                    )
                return MetadataCompletionOutcome(existing.id, "queued")
            if existing.status == "running":
                return MetadataCompletionOutcome(existing.id, "running")
            return MetadataCompletionOutcome(existing.id, "failed")

    def manual_retry(self, parent_job_id: uuid.UUID) -> EnqueueOutcome:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            parent = session.get(MetadataJob, parent_job_id)
            if parent is None:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="metadata_job_not_found",
                )
            movie = session.get(Movie, parent.movie_id, with_for_update=True)
            parent = session.get(
                MetadataJob,
                parent_job_id,
                with_for_update=True,
                populate_existing=True,
            )
            if movie is None or parent is None:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="metadata_job_not_found",
                )
            if parent.status != "failed":
                raise MetadataQueueProblem(
                    status_code=409,
                    code="metadata_job_not_failed",
                )
            self._ensure_no_active(session, parent.normalized_number)
            attempt_no = self._next_attempt_no(session, parent.normalized_number)
            job = self._add_job(
                session,
                movie=movie,
                normalized_number=parent.normalized_number,
                priority=priority_for_reason("manual_or_search"),
                reason="manual_or_search",
                sort_date=parent.sort_date,
                retry_mode="full",
                requested_stages=(),
                attempt_no=attempt_no,
                parent_job_id=parent.id,
                created_at=current,
            )
            return EnqueueOutcome(job.id, created=True)

    def retry_enrichment(
        self,
        parent_job_id: uuid.UUID,
        *,
        stages: Iterable[str],
    ) -> EnqueueOutcome:
        try:
            requested = validate_enrichment_stages(stages)
        except MetadataStateError:
            raise MetadataQueueProblem(
                status_code=409,
                code="metadata_job_no_retryable_enrichment",
            ) from None
        current = self._utc_now()
        with self._session_factory.begin() as session:
            parent = session.get(MetadataJob, parent_job_id)
            if parent is None:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="metadata_job_not_found",
                )
            movie = session.get(Movie, parent.movie_id, with_for_update=True)
            parent = session.get(
                MetadataJob,
                parent_job_id,
                with_for_update=True,
                populate_existing=True,
            )
            if movie is None or parent is None:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="metadata_job_not_found",
                )
            if parent.status not in {"completed_with_warnings", "failed"}:
                raise MetadataQueueProblem(
                    status_code=409,
                    code="metadata_job_no_retryable_enrichment",
                )
            retryable = retryable_enrichment_stages(session, parent, movie=movie)
            if any(stage not in retryable for stage in requested):
                raise MetadataQueueProblem(
                    status_code=409,
                    code="metadata_job_no_retryable_enrichment",
                )
            self._ensure_no_active(session, parent.normalized_number)
            attempt_no = self._next_attempt_no(session, parent.normalized_number)
            job = self._add_job(
                session,
                movie=movie,
                normalized_number=parent.normalized_number,
                priority=priority_for_reason("manual_or_search"),
                reason="manual_or_search",
                sort_date=parent.sort_date,
                retry_mode="missing_enrichment",
                requested_stages=requested,
                attempt_no=attempt_no,
                parent_job_id=parent.id,
                created_at=current,
            )
            return EnqueueOutcome(job.id, created=True)

    def retryable_stages(self, job_id: uuid.UUID) -> tuple[str, ...]:
        with self._session_factory() as session:
            job = session.get(MetadataJob, job_id)
            if job is None:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="metadata_job_not_found",
                )
            movie = session.get(Movie, job.movie_id)
            return retryable_enrichment_stages(session, job, movie=movie)

    def control_snapshot(self) -> MetadataQueueControlSnapshot:
        with self._session_factory() as session:
            return self._control_snapshot_in_session(session)

    def set_paused(self, paused: bool) -> MetadataQueueControlSnapshot:
        if not isinstance(paused, bool):
            raise ValueError("metadata paused control must be boolean")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            self._acquire_slot_lock(session)
            control = session.get(
                MetadataWorkerControl,
                True,
                with_for_update=True,
            )
            if control is None:
                control = MetadataWorkerControl(
                    singleton_key=True,
                    paused=paused,
                    updated_at=current,
                )
                session.add(control)
                session.flush()
            else:
                control.paused = paused
                control.updated_at = current
            return self._control_snapshot_in_session(session)

    def claim_next(
        self,
        worker_id: str,
        *,
        lease_duration: timedelta,
    ) -> MetadataClaim | None:
        if not worker_id or len(worker_id) > 80 or lease_duration <= timedelta(0):
            raise ValueError("invalid metadata worker claim")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            self._acquire_slot_lock(session)
            control = session.get(MetadataWorkerControl, True)
            if control is not None and control.paused:
                return None
            active_count = session.scalar(
                select(func.count(MetadataJob.id)).where(
                    MetadataJob.status == "running",
                    MetadataJob.claim_expires_at > current,
                )
            )
            if active_count is None or active_count >= MAX_RUNNING_JOBS:
                return None
            job = session.scalar(
                select(MetadataJob)
                .where(
                    or_(
                        MetadataJob.status == "queued",
                        (
                            (MetadataJob.status == "running")
                            & (MetadataJob.claim_expires_at <= current)
                        ),
                    )
                )
                .order_by(
                    MetadataJob.priority,
                    MetadataJob.sort_date.desc().nulls_last(),
                    MetadataJob.created_at,
                    MetadataJob.id,
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            if job.status == "running":
                session.execute(
                    update(MetadataStage)
                    .where(
                        MetadataStage.job_id == job.id,
                        MetadataStage.status == "running",
                    )
                    .values(
                        status="pending",
                        started_at=None,
                        finished_at=None,
                        failure_code=None,
                    )
                )
            claim_owner = f"{worker_id}:{uuid.uuid4().hex}"
            job.status = "running"
            job.claim_owner = claim_owner
            job.claim_expires_at = current + lease_duration
            if job.started_at is None:
                job.started_at = current
            movie = session.get(Movie, job.movie_id, with_for_update=True)
            if movie is None:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="resource_not_found",
                )
            if movie.catalog_state != "core_ready":
                movie.catalog_state = "metadata_running"
                movie.updated_at = current
            elapsed_ms = _elapsed_ms(job.started_at, current)
            stage_statuses = {
                item.stage: item.status
                for item in session.scalars(
                    select(MetadataStage).where(MetadataStage.job_id == job.id)
                )
            }
            pending_stages = tuple(
                stage for stage in ALL_STAGES if stage_statuses.get(stage) == "pending"
            )
            self._publish_job(
                session,
                job,
                event_type="metadata.job.started.v1",
                stage=pending_stages[0] if pending_stages else None,
            )
            return MetadataClaim(
                job_id=job.id,
                movie_id=job.movie_id,
                normalized_number=job.normalized_number,
                retry_mode=job.retry_mode,
                requested_stages=tuple(job.requested_stages),
                claim_owner=claim_owner,
                claim_expires_at=job.claim_expires_at,
                elapsed_ms=elapsed_ms,
                pending_stages=pending_stages,
                has_warnings=any(
                    status in {"warning", "failed"}
                    for status in stage_statuses.values()
                ),
            )

    def renew(
        self,
        claim: MetadataClaim,
        *,
        lease_duration: timedelta,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("invalid metadata claim lease")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(MetadataJob)
                .where(
                    MetadataJob.id == claim.job_id,
                    MetadataJob.status == "running",
                    MetadataJob.claim_owner == claim.claim_owner,
                    MetadataJob.claim_expires_at > current,
                )
                .values(claim_expires_at=current + lease_duration)
            )
            if result.rowcount != 1:
                raise self._claim_lost()

    def load_claim(
        self,
        *,
        job_id: uuid.UUID,
        claim_owner: str,
    ) -> MetadataClaim:
        current = self._utc_now()
        with self._session_factory() as session:
            job = session.scalar(
                select(MetadataJob).where(
                    MetadataJob.id == job_id,
                    MetadataJob.status == "running",
                    MetadataJob.claim_owner == claim_owner,
                    MetadataJob.claim_expires_at > current,
                )
            )
            if job is None:
                raise self._claim_lost()
            stage_statuses = {
                item.stage: item.status
                for item in session.scalars(
                    select(MetadataStage).where(MetadataStage.job_id == job.id)
                )
            }
            return MetadataClaim(
                job_id=job.id,
                movie_id=job.movie_id,
                normalized_number=job.normalized_number,
                retry_mode=job.retry_mode,
                requested_stages=tuple(job.requested_stages),
                claim_owner=job.claim_owner,
                claim_expires_at=job.claim_expires_at,
                elapsed_ms=_elapsed_ms(job.started_at, current),
                pending_stages=tuple(
                    stage
                    for stage in ALL_STAGES
                    if stage_statuses.get(stage) == "pending"
                ),
                has_warnings=any(
                    status in {"warning", "failed"}
                    for status in stage_statuses.values()
                ),
            )

    def is_claim_active(self, claim: MetadataClaim) -> bool:
        current = self._utc_now()
        with self._session_factory() as session:
            active = session.scalar(
                select(MetadataJob.id).where(
                    MetadataJob.id == claim.job_id,
                    MetadataJob.status == "running",
                    MetadataJob.claim_owner == claim.claim_owner,
                    MetadataJob.claim_expires_at > current,
                )
            )
        return active is not None

    def expire(self, claim: MetadataClaim) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(MetadataJob)
                .where(
                    MetadataJob.id == claim.job_id,
                    MetadataJob.status == "running",
                    MetadataJob.claim_owner == claim.claim_owner,
                )
                .values(claim_expires_at=current)
            )
            if result.rowcount != 1:
                raise self._claim_lost()

    def start_stage(self, claim: MetadataClaim, stage_name: str) -> None:
        if stage_name not in ALL_STAGES:
            raise ValueError("invalid metadata stage")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._require_active_claim(session, claim, current=current)
            stage = session.get(
                MetadataStage,
                (claim.job_id, stage_name),
                with_for_update=True,
            )
            if stage is None or stage.status != "pending":
                raise MetadataQueueProblem(
                    status_code=409,
                    code="metadata_stage_conflict",
                )
            stage.status = "running"
            stage.started_at = current
            self._publish_job(
                session,
                job,
                event_type="metadata.job.stage_changed.v1",
                stage=stage_name,
                stage_status="running",
            )

    def is_core_ready(self, claim: MetadataClaim) -> bool:
        current = self._utc_now()
        with self._session_factory() as session:
            active = session.scalar(
                select(MetadataJob.id).where(
                    MetadataJob.id == claim.job_id,
                    MetadataJob.status == "running",
                    MetadataJob.claim_owner == claim.claim_owner,
                    MetadataJob.claim_expires_at > current,
                )
            )
            if active is None:
                raise self._claim_lost()
            state = session.scalar(
                select(Movie.catalog_state).where(Movie.id == claim.movie_id)
            )
        return state == "core_ready"

    def finish_stage(
        self,
        claim: MetadataClaim,
        stage_name: str,
        *,
        status: str,
        failure_code: str | None = None,
    ) -> None:
        if status not in {"succeeded", "warning", "failed"}:
            raise ValueError("invalid metadata stage result")
        if (status == "succeeded") != (failure_code is None):
            raise ValueError("invalid metadata stage failure code")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._require_active_claim(session, claim, current=current)
            stage = session.get(
                MetadataStage,
                (claim.job_id, stage_name),
                with_for_update=True,
            )
            if stage is None or stage.status != "running":
                raise MetadataQueueProblem(
                    status_code=409,
                    code="metadata_stage_conflict",
                )
            stage.status = status
            stage.finished_at = current
            stage.failure_code = (
                stable_error_code(failure_code) if failure_code is not None else None
            )
            self._publish_job(
                session,
                job,
                event_type="metadata.job.stage_changed.v1",
                stage=stage_name,
                stage_status=status,
            )

    def complete(self, claim: MetadataClaim, *, with_warnings: bool) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            job = self._require_active_claim(session, claim, current=current)
            movie = session.get(Movie, job.movie_id, with_for_update=True)
            if movie is None or movie.catalog_state != "core_ready":
                raise MetadataQueueProblem(
                    status_code=409,
                    code="metadata_core_not_committed",
                )
            stages = list(
                session.scalars(
                    select(MetadataStage)
                    .where(MetadataStage.job_id == job.id)
                    .with_for_update()
                )
            )
            if any(stage.status in {"pending", "running"} for stage in stages):
                raise MetadataQueueProblem(
                    status_code=409,
                    code="metadata_stage_conflict",
                )
            has_warnings = any(
                stage.status in {"warning", "failed"} for stage in stages
            )
            if has_warnings != with_warnings:
                raise MetadataQueueProblem(
                    status_code=409,
                    code="metadata_stage_conflict",
                )
            self._finish_job(
                job,
                status=("completed_with_warnings" if has_warnings else "completed"),
                current=current,
                failure_code=None,
                failure_detail=None,
            )
            self._publish_job(
                session,
                job,
                event_type="metadata.job.completed.v1",
                stages=stages,
            )

    def fail(
        self,
        claim: MetadataClaim,
        *,
        code: str,
        detail: str,
    ) -> None:
        self._fail(
            claim,
            code=code,
            detail=detail,
            require_unexpired=True,
        )

    def fail_after_termination(
        self,
        claim: MetadataClaim,
        *,
        code: str,
        detail: str,
    ) -> None:
        self._fail(
            claim,
            code=code,
            detail=detail,
            require_unexpired=False,
        )

    def _fail(
        self,
        claim: MetadataClaim,
        *,
        code: str,
        detail: str,
        require_unexpired: bool,
    ) -> None:
        current = self._utc_now()
        safe_code = stable_error_code(code)
        safe_detail = redact_text(detail)
        if not safe_detail:
            safe_detail = safe_code
        with self._session_factory.begin() as session:
            conditions = [
                MetadataJob.id == claim.job_id,
                MetadataJob.status == "running",
                MetadataJob.claim_owner == claim.claim_owner,
            ]
            if require_unexpired:
                conditions.append(MetadataJob.claim_expires_at > current)
            job = session.scalar(
                select(MetadataJob).where(*conditions).with_for_update()
            )
            if job is None:
                raise self._claim_lost()
            running_stage = session.scalar(
                select(MetadataStage)
                .where(
                    MetadataStage.job_id == job.id,
                    MetadataStage.status == "running",
                )
                .with_for_update()
                .limit(1)
            )
            if running_stage is not None:
                running_stage.status = "failed"
                running_stage.finished_at = current
                running_stage.failure_code = safe_code
            self._finish_job(
                job,
                status="failed",
                current=current,
                failure_code=safe_code,
                failure_detail=safe_detail,
            )
            self._publish_job(
                session,
                job,
                event_type="metadata.job.failed.v1",
                stage=running_stage.stage if running_stage is not None else None,
            )
            movie = session.get(Movie, job.movie_id, with_for_update=True)
            if movie is not None and movie.catalog_state != "core_ready":
                movie.catalog_state = "raw_only"
                movie.updated_at = current

    def _add_job(
        self,
        session: Session,
        *,
        movie: Movie,
        normalized_number: str,
        priority: int,
        reason: str,
        sort_date: date | None,
        retry_mode: str,
        requested_stages: tuple[str, ...],
        attempt_no: int,
        parent_job_id: uuid.UUID | None,
        created_at: datetime,
    ) -> MetadataJob:
        plan = stage_plan(
            retry_mode=retry_mode,
            requested_stages=requested_stages,
        )
        job = MetadataJob(
            id=uuid.uuid4(),
            movie_id=movie.id,
            normalized_number=normalized_number,
            priority=priority,
            reason=reason,
            sort_date=sort_date,
            retry_mode=retry_mode,
            requested_stages=list(requested_stages),
            status="queued",
            attempt_no=attempt_no,
            parent_job_id=parent_job_id,
            claim_owner=None,
            claim_expires_at=None,
            started_at=None,
            finished_at=None,
            elapsed_ms=None,
            failure_code=None,
            failure_detail=None,
            created_at=created_at,
        )
        session.add(job)
        session.flush()
        session.add_all(
            MetadataStage(
                job_id=job.id,
                stage=stage,
                status=status,
                started_at=None,
                finished_at=None,
                failure_code=None,
            )
            for stage, status in plan.items()
        )
        if movie.catalog_state != "core_ready":
            movie.catalog_state = "metadata_queued"
            movie.updated_at = created_at
        self._publish_job(
            session,
            job,
            event_type="metadata.job.queued.v1",
        )
        return job

    def _publish_job(
        self,
        session: Session,
        job: MetadataJob | None,
        *,
        event_type: str,
        stage: str | None = None,
        stage_status: str | None = None,
        elapsed_ms: int | None = None,
        stages: list[MetadataStage] | None = None,
    ) -> None:
        if self._event_writer is None or job is None:
            return
        if event_type == "metadata.job.queued.v1":
            payload: dict[str, object] = {
                "id": str(job.id),
                "movie_id": str(job.movie_id),
                "number": job.normalized_number,
                "priority": job.priority,
                "status": job.status,
                "attempt_no": job.attempt_no,
                "retry_mode": job.retry_mode,
                "requested_stages": list(job.requested_stages),
                "parent_job_id": (
                    str(job.parent_job_id) if job.parent_job_id is not None else None
                ),
            }
        elif event_type == "metadata.job.started.v1":
            payload = {
                "id": str(job.id),
                "movie_id": str(job.movie_id),
                "number": job.normalized_number,
                "priority": job.priority,
                "status": job.status,
                "attempt_no": job.attempt_no,
                "retry_mode": job.retry_mode,
                "requested_stages": list(job.requested_stages),
                "parent_job_id": (
                    str(job.parent_job_id) if job.parent_job_id is not None else None
                ),
                "stage": stage,
                "started_at": _iso(job.started_at),
            }
        elif event_type == "metadata.job.stage_changed.v1":
            payload = {
                "id": str(job.id),
                "status": job.status,
                "stage": stage,
                "stage_status": stage_status,
                "elapsed_ms": (
                    elapsed_ms
                    if elapsed_ms is not None
                    else _elapsed_ms(job.started_at, self._utc_now())
                ),
            }
        elif event_type == "metadata.job.completed.v1":
            payload = {
                "id": str(job.id),
                "movie_id": str(job.movie_id),
                "status": job.status,
                "warnings": [
                    item.stage
                    for item in stages or []
                    if item.status in {"warning", "failed"}
                ],
                "finished_at": _iso(job.finished_at),
            }
        elif event_type == "metadata.job.failed.v1":
            payload = {
                "id": str(job.id),
                "movie_id": str(job.movie_id),
                "status": job.status,
                "error_code": job.failure_code,
                "stage": stage,
                "elapsed_ms": job.elapsed_ms,
            }
        else:
            raise ValueError("unsupported metadata event type")
        self._event_writer.append(
            session,
            stream="metadata",
            aggregate_id=job.id,
            event_type=event_type,
            payload=payload,
        )

    @staticmethod
    def _ensure_no_active(session: Session, normalized_number: str) -> None:
        active = session.scalar(
            select(MetadataJob.id).where(
                MetadataJob.normalized_number == normalized_number,
                MetadataJob.status.in_(("queued", "running")),
            )
        )
        if active is not None:
            raise MetadataQueueProblem(
                status_code=409,
                code="metadata_job_already_active",
            )

    @staticmethod
    def _next_attempt_no(session: Session, normalized_number: str) -> int:
        latest = session.scalar(
            select(func.max(MetadataJob.attempt_no)).where(
                MetadataJob.normalized_number == normalized_number
            )
        )
        return int(latest or 0) + 1

    @staticmethod
    def _require_active_claim(
        session: Session,
        claim: MetadataClaim,
        *,
        current: datetime,
    ) -> MetadataJob:
        job = session.scalar(
            select(MetadataJob)
            .where(
                MetadataJob.id == claim.job_id,
                MetadataJob.status == "running",
                MetadataJob.claim_owner == claim.claim_owner,
                MetadataJob.claim_expires_at > current,
            )
            .with_for_update()
        )
        if job is None:
            raise MetadataQueue._claim_lost()
        return job

    @staticmethod
    def _finish_job(
        job: MetadataJob,
        *,
        status: str,
        current: datetime,
        failure_code: str | None,
        failure_detail: str | None,
    ) -> None:
        job.status = status
        job.claim_owner = None
        job.claim_expires_at = None
        job.finished_at = current
        job.elapsed_ms = _elapsed_ms(job.started_at, current)
        job.failure_code = failure_code
        job.failure_detail = failure_detail

    @staticmethod
    def _acquire_slot_lock(session: Session) -> None:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _SLOT_LOCK_KEY},
            )

    @staticmethod
    def _control_snapshot_in_session(
        session: Session,
    ) -> MetadataQueueControlSnapshot:
        control = session.get(MetadataWorkerControl, True)
        counts = {
            status: int(count)
            for status, count in session.execute(
                select(MetadataJob.status, func.count(MetadataJob.id))
                .where(MetadataJob.status.in_(("queued", "running")))
                .group_by(MetadataJob.status)
            )
        }
        return MetadataQueueControlSnapshot(
            paused=bool(control.paused) if control is not None else False,
            queued=counts.get("queued", 0),
            running=counts.get("running", 0),
        )

    @staticmethod
    def _claim_lost() -> MetadataQueueProblem:
        return MetadataQueueProblem(status_code=409, code="metadata_claim_lost")

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("metadata queue clock must be timezone-aware")
        return current.astimezone(timezone.utc)


def _elapsed_ms(started_at: datetime | None, current: datetime) -> int:
    if started_at is None:
        return 0
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return max(0, int((current - started_at).total_seconds() * 1000))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def retryable_enrichment_stages(
    session: Session,
    job: MetadataJob,
    *,
    movie: Movie | None,
) -> tuple[str, ...]:
    if job.status == "completed_with_warnings":
        pass
    elif (
        job.status == "failed"
        and movie is not None
        and movie.catalog_state == "core_ready"
    ):
        core_status = session.scalar(
            select(MetadataStage.status).where(
                MetadataStage.job_id == job.id,
                MetadataStage.stage == "javdb_core",
            )
        )
        if core_status != "succeeded":
            return ()
    else:
        return ()
    return tuple(
        stage
        for stage in OPTIONAL_STAGES
        if _latest_non_skipped_status(session, job, stage)
        in _RETRYABLE_ENRICHMENT_STATUSES
    )


def _latest_non_skipped_status(
    session: Session,
    job: MetadataJob,
    stage_name: str,
) -> str | None:
    current: MetadataJob | None = job
    visited: set[uuid.UUID] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        status = session.scalar(
            select(MetadataStage.status).where(
                MetadataStage.job_id == current.id,
                MetadataStage.stage == stage_name,
            )
        )
        if status is not None and status != "skipped":
            return status
        current = (
            session.get(MetadataJob, current.parent_job_id)
            if current.parent_job_id is not None
            else None
        )
    return None


__all__ = [
    "EnqueueOutcome",
    "MAX_RUNNING_JOBS",
    "MetadataCandidateInput",
    "MetadataClaim",
    "MetadataCompletionOutcome",
    "MetadataQueue",
    "MetadataQueueControlSnapshot",
    "MetadataQueueProblem",
    "retryable_enrichment_stages",
]
