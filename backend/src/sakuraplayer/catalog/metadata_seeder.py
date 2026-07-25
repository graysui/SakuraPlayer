from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataCandidateInput, MetadataQueue
from sakuraplayer.catalog.models import MetadataJob, MetadataQueueState
from sakuraplayer.resources.initial_scope import InitialScopeSelector
from sakuraplayer.resources.models import AvdbSyncRun


INITIAL_LIMIT = 5_000
SEED_BATCH_SIZE = 100
_STATE_LOCK_KEY = 0x53414B5552410008


@dataclass(frozen=True)
class SeedOutcome:
    initial: int = 0
    history: int = 0


class MetadataQueueSeeder:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        queue: MetadataQueue,
        selector: InitialScopeSelector,
        now: Callable[[], datetime] | None = None,
        source_ready: Callable[[], bool] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._queue = queue
        self._selector = selector
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._source_ready = source_ready or self._has_completed_source_sync

    def seed_once(self) -> SeedOutcome:
        if not self._source_ready():
            return SeedOutcome()
        with self._session_factory() as lock_session:
            if lock_session.get_bind().dialect.name != "postgresql":
                return self._seed_ready_once()
            with lock_session.begin():
                lock_session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": _STATE_LOCK_KEY},
                )
                return self._seed_ready_once()

    def _seed_ready_once(self) -> SeedOutcome:
        current = self._utc_now()
        as_of, initial_complete, initial_count = self._state_snapshot(current)
        excluded_movie_ids = select(MetadataJob.movie_id)
        if not initial_complete:
            remaining = max(0, INITIAL_LIMIT - initial_count)
            candidates = self._selector.select_initial(
                as_of=as_of,
                exclude_movie_ids=excluded_movie_ids,
            )
            created, exhausted = self._enqueue_until_created(
                candidates,
                limit=min(SEED_BATCH_SIZE, remaining),
            )
            if initial_count + created >= INITIAL_LIMIT or exhausted:
                self._mark_initial_complete(current)
            return SeedOutcome(initial=created)
        created, _ = self._enqueue_until_created(
            self._selector.iter_remaining(
                exclude_movie_ids=excluded_movie_ids,
            ),
            limit=SEED_BATCH_SIZE,
        )
        return SeedOutcome(history=created)

    def _enqueue_until_created(
        self,
        candidates: Iterable[MetadataCandidateInput],
        *,
        limit: int,
    ) -> tuple[int, bool]:
        if limit <= 0:
            return 0, True
        created = 0
        for candidate in candidates:
            outcome = self._queue.enqueue(
                movie_id=candidate.movie_id,
                normalized_number=candidate.normalized_number,
                sort_date=candidate.publish_date,
                reason=candidate.reason,
            )
            created += int(outcome.created)
            if created >= limit:
                return created, False
        return created, True

    def _state_snapshot(self, current: datetime) -> tuple[date, bool, int]:
        with self._session_factory.begin() as session:
            state = session.get(MetadataQueueState, True, with_for_update=True)
            if state is None:
                state = MetadataQueueState(
                    singleton_key=True,
                    initial_as_of=current.astimezone(ZoneInfo("Asia/Shanghai")).date(),
                    initial_completed_at=None,
                    created_at=current,
                    updated_at=current,
                )
                session.add(state)
                session.flush()
            initial_count = session.scalar(
                select(func.count(func.distinct(MetadataJob.movie_id))).where(
                    MetadataJob.reason == "initial"
                )
            )
            return (
                state.initial_as_of,
                state.initial_completed_at is not None,
                int(initial_count or 0),
            )

    def _mark_initial_complete(self, current: datetime) -> None:
        with self._session_factory.begin() as session:
            state = session.get(MetadataQueueState, True, with_for_update=True)
            if state is None:
                raise RuntimeError("metadata queue state disappeared")
            if state.initial_completed_at is None:
                state.initial_completed_at = current
                state.updated_at = current

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("metadata seeder clock must be timezone-aware")
        return current.astimezone(timezone.utc)

    def _has_completed_source_sync(self) -> bool:
        with self._session_factory() as session:
            completed = session.scalar(
                select(AvdbSyncRun.id).where(AvdbSyncRun.status == "completed").limit(1)
            )
        return completed is not None


__all__ = ["MetadataQueueSeeder", "SeedOutcome"]
