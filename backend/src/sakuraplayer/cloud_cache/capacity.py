from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.domain.cache_job import (
    CacheJobState,
    CacheJobStatus,
    CapacityClass,
)
from sakuraplayer.cloud_cache.models import CacheJob

RUNNING_CAPACITY = 2
QUEUED_CAPACITY = 10
READY_CAPACITY = 20
_CAPACITY_LOCK_KEY = 115_103


@dataclass(frozen=True, slots=True)
class CacheCapacitySnapshot:
    running: int
    queued: int
    ready: int


class CacheCapacityUnavailable(RuntimeError):
    code = "cache_running_full"

    def __init__(self) -> None:
        super().__init__(self.code)


def acquire_capacity_lock(session: Session) -> None:
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _CAPACITY_LOCK_KEY},
        )


def active_cache_jobs(session: Session) -> bool:
    acquire_capacity_lock(session)
    count = session.scalar(
        select(func.count(CacheJob.id)).where(
            CacheJob.capacity_class != CapacityClass.RELEASED.value
        )
    )
    return bool(count)


class CacheCapacityService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def snapshot(self) -> CacheCapacitySnapshot:
        with self._session_factory.begin() as session:
            acquire_capacity_lock(session)
            return capacity_snapshot(session)

    def transition(
        self,
        job_id: uuid.UUID,
        target: CacheJobStatus,
    ) -> None:
        with self._session_factory.begin() as session:
            acquire_capacity_lock(session)
            job = session.get(CacheJob, job_id, with_for_update=True)
            if job is None:
                raise LookupError("cache_job_not_found")
            current_state = CacheJobState(
                CacheJobStatus(job.status),
                CapacityClass(job.capacity_class),
            )
            next_state = current_state.transition(target)
            if (
                next_state.capacity_class is CapacityClass.RUNNING
                and current_state.capacity_class is not CapacityClass.RUNNING
                and capacity_snapshot(session).running >= RUNNING_CAPACITY
            ):
                raise CacheCapacityUnavailable
            job.status = next_state.status.value
            job.capacity_class = next_state.capacity_class.value
            job.updated_at = self._now()


def capacity_snapshot(session: Session) -> CacheCapacitySnapshot:
    counts: dict[str, int] = {
        capacity_class: count
        for capacity_class, count in session.execute(
            select(CacheJob.capacity_class, func.count(CacheJob.id))
            .where(CacheJob.capacity_class != CapacityClass.RELEASED.value)
            .group_by(CacheJob.capacity_class)
        ).all()
    }
    return CacheCapacitySnapshot(
        running=counts.get(CapacityClass.RUNNING.value, 0),
        queued=counts.get(CapacityClass.QUEUED.value, 0),
        ready=counts.get(CapacityClass.READY.value, 0),
    )


__all__ = [
    "CacheCapacityService",
    "CacheCapacitySnapshot",
    "CacheCapacityUnavailable",
    "QUEUED_CAPACITY",
    "READY_CAPACITY",
    "RUNNING_CAPACITY",
    "acquire_capacity_lock",
    "active_cache_jobs",
    "capacity_snapshot",
]
