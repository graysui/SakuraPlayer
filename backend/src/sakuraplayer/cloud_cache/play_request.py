from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.capacity import (
    QUEUED_CAPACITY,
    RUNNING_CAPACITY,
    CacheCapacitySnapshot,
    acquire_capacity_lock,
    capacity_snapshot,
)
from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CachePlayRequest,
    Cloud115Binding,
)
from sakuraplayer.cloud_cache.play_disposition import play_disposition
from sakuraplayer.resources.source_submission import (
    SourceSubmissionPort,
    SourceSubmissionProblem,
)

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._~-]{16,128}$")
_ACTIVE_STATUSES = (
    "queued",
    "submitting",
    "offlining",
    "submit_uncertain",
    "resolving",
    "awaiting_selection",
    "ready",
    "cancelling",
    "cleaning",
    "cleanup_failed",
)


class CacheProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CacheJobView:
    id: uuid.UUID
    movie_id: uuid.UUID
    source_id: uuid.UUID
    status: str
    remote_percent: float
    ready_at: datetime | None
    last_accessed_at: datetime | None
    expires_at: datetime | None
    failure_code: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PlayRequestResult:
    disposition: Literal["started", "queued", "ready", "reused"]
    job: CacheJobView
    wait_deadline: datetime | None = None


@dataclass(frozen=True, slots=True)
class CacheJobPage:
    items: list[CacheJobView]
    capacity: CacheCapacitySnapshot
    next_cursor: str | None


class PlayRequestService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        source_port: SourceSubmissionPort,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._source_port = source_port
        self._now = now or (lambda: datetime.now(timezone.utc))

    def create(
        self,
        *,
        movie_id: uuid.UUID,
        source_id: uuid.UUID,
        idempotency_key: str,
    ) -> PlayRequestResult:
        if _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise CacheProblem(status_code=422, code="validation_failed")

        with self._session_factory.begin() as session:
            acquire_capacity_lock(session)
            prior = session.get(CachePlayRequest, idempotency_key)
            if prior is not None:
                if prior.movie_id != movie_id or prior.source_id != source_id:
                    raise CacheProblem(status_code=409, code="idempotency_conflict")
                job = session.get(CacheJob, prior.cache_job_id)
                if job is None:
                    raise CacheProblem(status_code=409, code="state_conflict")
                return self._result(job, now=self._now(), replayed=True)

            binding = session.scalar(select(Cloud115Binding).with_for_update())
            self._require_active_binding(binding)
            assert binding is not None
            try:
                self._source_port.validate_for_play(
                    session,
                    movie_id=movie_id,
                    source_id=source_id,
                )
            except SourceSubmissionProblem as error:
                raise CacheProblem(
                    status_code=error.status_code,
                    code=error.code,
                ) from None

            existing = session.scalar(
                select(CacheJob)
                .where(
                    CacheJob.source_id == source_id,
                    CacheJob.binding_id == binding.id,
                    CacheJob.status.in_(_ACTIVE_STATUSES),
                )
                .with_for_update()
            )
            now = self._now()
            if existing is not None:
                session.add(
                    CachePlayRequest(
                        idempotency_key=idempotency_key,
                        movie_id=movie_id,
                        source_id=source_id,
                        cache_job_id=existing.id,
                        created_at=now,
                    )
                )
                session.flush()
                return self._result(existing, now=now)

            snapshot = capacity_snapshot(session)
            if snapshot.running < RUNNING_CAPACITY:
                status = "submitting"
                capacity_class = "running"
            elif snapshot.queued < QUEUED_CAPACITY:
                status = "queued"
                capacity_class = "queued"
            else:
                raise CacheProblem(status_code=409, code="cache_queue_full")

            job = CacheJob(
                id=uuid.uuid4(),
                movie_id=movie_id,
                source_id=source_id,
                binding_id=binding.id,
                status=status,
                capacity_class=capacity_class,
                account_key=binding.account_key,
                cache_root_cid=binding.cache_root_cid,
                task_dir_name=f"cache-{uuid.uuid4().hex}",
                remote_percent=0,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            session.flush()
            session.add(
                CachePlayRequest(
                    idempotency_key=idempotency_key,
                    movie_id=movie_id,
                    source_id=source_id,
                    cache_job_id=job.id,
                    created_at=now,
                )
            )
            session.flush()
            resolved = play_disposition(job.status, created=True, now=now)
            return PlayRequestResult(
                disposition=resolved.name,
                job=_view(job),
                wait_deadline=resolved.wait_deadline,
            )

    def get(self, job_id: uuid.UUID) -> CacheJobView:
        with self._session_factory() as session:
            job = session.get(CacheJob, job_id)
            if job is None:
                raise CacheProblem(status_code=404, code="resource_not_found")
            return _view(job)

    def list(
        self,
        *,
        statuses: tuple[str, ...] = (),
        cursor: str | None = None,
        limit: int = 24,
    ) -> CacheJobPage:
        if not 1 <= limit <= 100 or any(
            status not in _ACTIVE_STATUSES + ("failed", "cleaned", "detached")
            for status in statuses
        ):
            raise CacheProblem(status_code=422, code="validation_failed")
        normalized_statuses = tuple(sorted(set(statuses)))
        cursor_values = _decode_cursor(cursor, statuses=normalized_statuses)
        with self._session_factory.begin() as session:
            acquire_capacity_lock(session)
            statement = select(CacheJob)
            if normalized_statuses:
                statement = statement.where(CacheJob.status.in_(normalized_statuses))
            if cursor_values is not None:
                created_at, job_id = cursor_values
                statement = statement.where(
                    or_(
                        CacheJob.created_at < created_at,
                        and_(
                            CacheJob.created_at == created_at,
                            CacheJob.id < job_id,
                        ),
                    )
                )
            jobs = list(
                session.scalars(
                    statement.order_by(
                        CacheJob.created_at.desc(),
                        CacheJob.id.desc(),
                    ).limit(limit + 1)
                )
            )
            has_more = len(jobs) > limit
            jobs = jobs[:limit]
            next_cursor = None
            if has_more and jobs:
                last = jobs[-1]
                next_cursor = _encode_cursor(
                    last.created_at,
                    last.id,
                    statuses=normalized_statuses,
                )
            return CacheJobPage(
                items=[_view(job) for job in jobs],
                capacity=capacity_snapshot(session),
                next_cursor=next_cursor,
            )

    @staticmethod
    def _require_active_binding(binding: Cloud115Binding | None) -> None:
        if binding is None:
            raise CacheProblem(status_code=409, code="cloud115_binding_required")
        failures = {
            "expired": (422, "cloud115_credentials_expired"),
            "unavailable": (503, "cloud115_unavailable"),
            "detached": (404, "cloud115_directory_not_found"),
        }
        failure = failures.get(binding.status)
        if failure is not None:
            raise CacheProblem(status_code=failure[0], code=failure[1])
        if binding.status != "active":
            raise CacheProblem(status_code=409, code="state_conflict")

    @staticmethod
    def _result(
        job: CacheJob,
        *,
        now: datetime,
        replayed: bool = False,
    ) -> PlayRequestResult:
        resolved = play_disposition(
            job.status,
            created=False,
            replayed=replayed,
            now=now,
        )
        return PlayRequestResult(
            disposition=resolved.name,
            job=_view(job),
            wait_deadline=resolved.wait_deadline,
        )


def _view(job: CacheJob) -> CacheJobView:
    return CacheJobView(
        id=job.id,
        movie_id=job.movie_id,
        source_id=job.source_id,
        status=job.status,
        remote_percent=float(job.remote_percent),
        ready_at=job.ready_at,
        last_accessed_at=job.last_accessed_at,
        expires_at=job.expires_at,
        failure_code=job.failure_code,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _encode_cursor(
    created_at: datetime,
    job_id: uuid.UUID,
    *,
    statuses: tuple[str, ...],
) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    payload = json.dumps(
        {
            "created_at": created_at.isoformat(),
            "id": str(job_id),
            "statuses": list(statuses),
            "v": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode_cursor(
    cursor: str | None,
    *,
    statuses: tuple[str, ...],
) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        payload: Any = json.loads(raw.decode("utf-8"))
        if (
            not isinstance(payload, dict)
            or set(payload) != {"created_at", "id", "statuses", "v"}
            or payload["v"] != 1
            or payload["statuses"] != list(statuses)
            or not isinstance(payload["created_at"], str)
            or not isinstance(payload["id"], str)
        ):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            raise ValueError
        return created_at, uuid.UUID(payload["id"])
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        raise CacheProblem(status_code=422, code="validation_failed") from None


__all__ = [
    "CacheJobPage",
    "CacheJobView",
    "CacheProblem",
    "PlayRequestResult",
    "PlayRequestService",
]
