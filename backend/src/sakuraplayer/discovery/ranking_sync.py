from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
import uuid

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.discovery.models import (
    RankingEntry,
    RankingSnapshot,
    RankingSyncRequest,
)
from sakuraplayer.resources.models import Movie
from sakuraplayer.shared.redaction import stable_error_code


RANKING_BOARDS = ("daily", "weekly", "monthly", "top250")
TOP250_START_YEAR = 2008


@dataclass(frozen=True)
class RankingEnqueueOutcome:
    request_id: uuid.UUID
    board: str
    year: int | None
    created: bool


@dataclass(frozen=True)
class RankingClaim:
    request_id: uuid.UUID
    board: str
    year: int | None
    claim_owner: str
    claim_token: uuid.UUID
    claim_expires_at: datetime


class RankingCandidate(Protocol):
    rank: int
    normalized_number: str


class RankingProviderPort(Protocol):
    def fetch_rankings(
        self,
        board: str,
        *,
        year: int | None,
        credentials: object | None,
    ) -> tuple[RankingCandidate, ...]: ...


class RankingSyncQueue:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def enqueue(
        self,
        board: str,
        *,
        year: int | None,
        scheduled_for: datetime,
        current_year: int | None = None,
    ) -> RankingEnqueueOutcome:
        current = self._utc_now()
        effective_year = current_year or current.year
        validate_ranking_scope(board, year, current_year=effective_year)
        slot = _utc_minute(scheduled_for)
        request_id = uuid.uuid4()
        try:
            with self._session_factory.begin() as session:
                session.add(
                    RankingSyncRequest(
                        id=request_id,
                        board=board,
                        year=year,
                        scheduled_for=slot,
                        status="queued",
                        claim_owner=None,
                        claim_token=None,
                        claim_expires_at=None,
                        attempt_count=0,
                        snapshot_id=None,
                        completed_at=None,
                        failure_code=None,
                        created_at=current,
                    )
                )
        except IntegrityError:
            with self._session_factory() as session:
                existing = session.scalar(
                    select(RankingSyncRequest)
                    .where(
                        RankingSyncRequest.board == board,
                        func.coalesce(RankingSyncRequest.year, 0) == (year or 0),
                        or_(
                            RankingSyncRequest.scheduled_for == slot,
                            RankingSyncRequest.status.in_(("queued", "claimed")),
                        ),
                    )
                    .order_by(
                        RankingSyncRequest.status.in_(("queued", "claimed")).desc(),
                        RankingSyncRequest.created_at.desc(),
                    )
                    .limit(1)
                )
                if existing is None:
                    raise
                return RankingEnqueueOutcome(
                    request_id=existing.id,
                    board=existing.board,
                    year=existing.year,
                    created=False,
                )
        return RankingEnqueueOutcome(request_id, board, year, True)

    def enqueue_due_targets(
        self,
        *,
        scheduled_for: datetime,
        current_year: int,
        credentials_configured: bool,
    ) -> tuple[RankingEnqueueOutcome, ...]:
        if current_year < TOP250_START_YEAR or current_year > 2200:
            raise ValueError("invalid ranking current year")
        targets: list[tuple[str, int | None]] = [
            ("daily", None),
            ("weekly", None),
            ("monthly", None),
        ]
        if credentials_configured:
            targets.extend((("top250", None), ("top250", current_year)))
            with self._session_factory() as session:
                completed_years = set(
                    session.scalars(
                        select(RankingSnapshot.year).where(
                            RankingSnapshot.board == "top250",
                            RankingSnapshot.status == "current",
                            RankingSnapshot.year.is_not(None),
                            RankingSnapshot.year < current_year,
                        )
                    )
                )
            targets.extend(
                ("top250", year)
                for year in range(current_year - 1, TOP250_START_YEAR - 1, -1)
                if year not in completed_years
            )
        return tuple(
            self.enqueue(
                board,
                year=year,
                scheduled_for=scheduled_for,
                current_year=current_year,
            )
            for board, year in targets
        )

    def claim_next(
        self,
        worker_id: str,
        *,
        lease_duration: timedelta,
    ) -> RankingClaim | None:
        if not worker_id or len(worker_id) > 128 or lease_duration <= timedelta(0):
            raise ValueError("invalid ranking request claim")
        current = self._utc_now()
        claim_token = uuid.uuid4()
        expires_at = current + lease_duration
        with self._session_factory.begin() as session:
            request = session.scalar(
                select(RankingSyncRequest)
                .where(
                    or_(
                        RankingSyncRequest.status == "queued",
                        (
                            (RankingSyncRequest.status == "claimed")
                            & (RankingSyncRequest.claim_expires_at <= current)
                        ),
                    )
                )
                .order_by(RankingSyncRequest.scheduled_for, RankingSyncRequest.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if request is None:
                return None
            request.status = "claimed"
            request.claim_owner = worker_id
            request.claim_token = claim_token
            request.claim_expires_at = expires_at
            request.attempt_count += 1
            request.snapshot_id = None
            request.completed_at = None
            request.failure_code = None
            return RankingClaim(
                request_id=request.id,
                board=request.board,
                year=request.year,
                claim_owner=worker_id,
                claim_token=claim_token,
                claim_expires_at=expires_at,
            )

    def activate_snapshot(
        self,
        claim: RankingClaim,
        *,
        candidates: Iterable[RankingCandidate],
        source_synced_at: datetime,
    ) -> uuid.UUID:
        ranked = tuple(candidates)
        _validate_snapshot_candidates(ranked)
        current = self._utc_now()
        synced_at = _aware_utc(source_synced_at, name="ranking source sync time")
        snapshot_id = uuid.uuid4()
        numbers = tuple(item.normalized_number for item in ranked)
        with self._session_factory.begin() as session:
            request = session.scalar(
                select(RankingSyncRequest)
                .where(*self._claim_conditions(claim, current=current))
                .with_for_update()
            )
            if request is None:
                raise RuntimeError("ranking request claim was lost")

            snapshot = RankingSnapshot(
                id=snapshot_id,
                board=claim.board,
                year=claim.year,
                status="building",
                source_synced_at=synced_at,
                created_at=current,
            )
            session.add(snapshot)
            session.flush()
            movie_ids = {
                movie.normalized_number: movie.id
                for movie in session.scalars(
                    select(Movie).where(Movie.normalized_number.in_(numbers))
                )
            }
            session.add_all(
                RankingEntry(
                    snapshot_id=snapshot_id,
                    rank=item.rank,
                    normalized_number=item.normalized_number,
                    movie_id=movie_ids.get(item.normalized_number),
                )
                for item in ranked
            )
            session.flush()
            session.execute(
                update(RankingSnapshot)
                .where(
                    RankingSnapshot.board == claim.board,
                    RankingSnapshot.year == claim.year,
                    RankingSnapshot.status == "current",
                )
                .values(status="superseded")
            )
            snapshot.status = "current"
            request.status = "completed"
            request.claim_owner = None
            request.claim_token = None
            request.claim_expires_at = None
            request.snapshot_id = snapshot_id
            request.completed_at = current
            request.failure_code = None
            session.flush()
        return snapshot_id

    def renew(self, claim: RankingClaim, *, lease_duration: timedelta) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("invalid ranking request lease")
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(RankingSyncRequest)
                .where(*self._claim_conditions(claim, current=current))
                .values(claim_expires_at=current + lease_duration)
            )
            if result.rowcount != 1:
                raise RuntimeError("ranking request claim was lost")

    def complete(self, claim: RankingClaim, *, snapshot_id: uuid.UUID) -> None:
        self._finish(
            claim,
            status="completed",
            snapshot_id=snapshot_id,
            failure_code=None,
        )

    def fail(self, claim: RankingClaim, *, code: str) -> None:
        self._finish(
            claim,
            status="failed",
            snapshot_id=None,
            failure_code=stable_error_code(code),
        )

    def _finish(
        self,
        claim: RankingClaim,
        *,
        status: str,
        snapshot_id: uuid.UUID | None,
        failure_code: str | None,
    ) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            result = session.execute(
                update(RankingSyncRequest)
                .where(*self._claim_conditions(claim, current=current))
                .values(
                    status=status,
                    claim_owner=None,
                    claim_token=None,
                    claim_expires_at=None,
                    snapshot_id=snapshot_id,
                    completed_at=current,
                    failure_code=failure_code,
                )
            )
            if result.rowcount != 1:
                raise RuntimeError("ranking request claim was lost")

    @staticmethod
    def _claim_conditions(
        claim: RankingClaim,
        *,
        current: datetime,
    ) -> tuple[object, ...]:
        return (
            RankingSyncRequest.id == claim.request_id,
            RankingSyncRequest.status == "claimed",
            RankingSyncRequest.claim_owner == claim.claim_owner,
            RankingSyncRequest.claim_token == claim.claim_token,
            RankingSyncRequest.claim_expires_at > current,
        )

    def _utc_now(self) -> datetime:
        return _aware_utc(self._now(), name="ranking queue clock")


class RankingSnapshotSynchronizer:
    def __init__(
        self,
        queue: RankingSyncQueue,
        provider: RankingProviderPort,
        *,
        credentials: Callable[[], object | None],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._queue = queue
        self._provider = provider
        self._credentials = credentials
        self._now = now or (lambda: datetime.now(timezone.utc))

    def synchronize(
        self,
        claim: RankingClaim,
        *,
        before_activate: Callable[[], None] | None = None,
    ) -> uuid.UUID:
        credentials = self._credentials() if claim.board == "top250" else None
        candidates = self._provider.fetch_rankings(
            claim.board,
            year=claim.year,
            credentials=credentials,
        )
        if before_activate is not None:
            before_activate()
        return self._queue.activate_snapshot(
            claim,
            candidates=candidates,
            source_synced_at=self._now(),
        )


def validate_ranking_scope(
    board: str,
    year: int | None,
    *,
    current_year: int,
) -> None:
    if board not in RANKING_BOARDS:
        raise ValueError("invalid ranking scope")
    if board != "top250" and year is not None:
        raise ValueError("invalid ranking scope")
    if board == "top250" and year is not None and not (
        TOP250_START_YEAR <= year <= current_year
    ):
        raise ValueError("invalid ranking scope")


def _utc_minute(value: datetime) -> datetime:
    return _aware_utc(value, name="ranking schedule").replace(second=0, microsecond=0)


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _validate_snapshot_candidates(candidates: tuple[RankingCandidate, ...]) -> None:
    if not candidates:
        raise ValueError("invalid ranking snapshot candidates")
    ranks: set[int] = set()
    numbers: set[str] = set()
    for item in candidates:
        if (
            type(item.rank) is not int
            or item.rank < 1
            or not isinstance(item.normalized_number, str)
            or not item.normalized_number
            or len(item.normalized_number) > 128
            or item.rank in ranks
            or item.normalized_number in numbers
        ):
            raise ValueError("invalid ranking snapshot candidates")
        ranks.add(item.rank)
        numbers.add(item.normalized_number)


__all__ = [
    "RANKING_BOARDS",
    "TOP250_START_YEAR",
    "RankingClaim",
    "RankingEnqueueOutcome",
    "RankingProviderPort",
    "RankingSnapshotSynchronizer",
    "RankingSyncQueue",
    "validate_ranking_scope",
]
