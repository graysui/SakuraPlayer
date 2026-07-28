from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.ports import PlaybackProgress
from sakuraplayer.playback.models import MoviePlaybackState
from sakuraplayer.resources.models import Movie

COMPLETION_RATIO = Decimal("0.95")
COMPLETION_REMAINING_SECONDS = Decimal("120")
PROGRESS_QUANTUM = Decimal("0.001")
MAX_PROGRESS_SECONDS = Decimal("999999999.999")


@dataclass(frozen=True, slots=True)
class CompletionState:
    position_seconds: Decimal
    duration_seconds: Decimal | None
    completed: bool


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    expected_version: int
    position_seconds: Decimal
    duration_seconds: Decimal | None


@dataclass(frozen=True, slots=True)
class MoviePlaybackStateView:
    movie_id: uuid.UUID
    position_seconds: Decimal
    duration_seconds: Decimal | None
    completed: bool
    version: int
    last_watched_at: datetime | None
    updated_at: datetime


class ProgressProblem(RuntimeError):
    def __init__(self, *, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class ProgressVersionConflict(ProgressProblem):
    def __init__(self, authoritative: MoviePlaybackStateView | None) -> None:
        self.authoritative = authoritative
        super().__init__(status_code=409, code="progress_version_conflict")


def completion_state(
    *,
    position_seconds: Decimal,
    duration_seconds: Decimal | None,
) -> CompletionState:
    if (
        not position_seconds.is_finite()
        or position_seconds < 0
        or position_seconds > MAX_PROGRESS_SECONDS
    ):
        raise ValueError("progress value must be a finite non-negative position")
    if duration_seconds is not None and (
        not duration_seconds.is_finite()
        or duration_seconds <= 0
        or duration_seconds > MAX_PROGRESS_SECONDS
    ):
        raise ValueError("progress value must have a finite positive duration")
    position_seconds = position_seconds.quantize(
        PROGRESS_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    if duration_seconds is not None:
        duration_seconds = duration_seconds.quantize(
            PROGRESS_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        if duration_seconds <= 0:
            raise ValueError("progress value must have a finite positive duration")

    completed = bool(
        position_seconds > 0
        and duration_seconds is not None
        and (
            position_seconds / duration_seconds >= COMPLETION_RATIO
            or duration_seconds - position_seconds < COMPLETION_REMAINING_SECONDS
        )
    )
    return CompletionState(
        position_seconds=Decimal(0) if completed else position_seconds,
        duration_seconds=duration_seconds,
        completed=completed,
    )


class MoviePlaybackStateService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def get(self, movie_id: uuid.UUID) -> MoviePlaybackStateView | None:
        with self._session_factory() as session:
            return self.get_in_session(session, movie_id)

    def get_in_session(
        self,
        session: Session,
        movie_id: uuid.UUID,
    ) -> MoviePlaybackStateView | None:
        row = session.get(MoviePlaybackState, movie_id)
        return _state_view(row) if row is not None else None

    def get_many(
        self,
        movie_ids: tuple[uuid.UUID, ...],
    ) -> dict[uuid.UUID, PlaybackProgress]:
        if not movie_ids:
            return {}
        with self._session_factory() as session:
            rows = session.scalars(
                select(MoviePlaybackState).where(
                    MoviePlaybackState.movie_id.in_(movie_ids)
                )
            )
            return {
                row.movie_id: PlaybackProgress(
                    position_seconds=float(row.position_seconds),
                    duration_seconds=(
                        float(row.duration_seconds)
                        if row.duration_seconds is not None
                        else None
                    ),
                    completed=row.completed,
                    version=row.version,
                )
                for row in rows
            }

    def update(
        self,
        *,
        movie_id: uuid.UUID,
        expected_version: int,
        position_seconds: Decimal,
        duration_seconds: Decimal | None,
    ) -> MoviePlaybackStateView:
        with self._session_factory.begin() as session:
            return self.update_in_session(
                session,
                movie_id=movie_id,
                update=ProgressUpdate(
                    expected_version=expected_version,
                    position_seconds=position_seconds,
                    duration_seconds=duration_seconds,
                ),
            )

    def update_in_session(
        self,
        session: Session,
        *,
        movie_id: uuid.UUID,
        update: ProgressUpdate,
    ) -> MoviePlaybackStateView:
        if update.expected_version < 0:
            raise ProgressProblem(status_code=422, code="validation_failed")
        result = completion_state(
            position_seconds=update.position_seconds,
            duration_seconds=update.duration_seconds,
        )
        movie = session.get(Movie, movie_id, with_for_update=True)
        if movie is None:
            raise ProgressProblem(status_code=404, code="resource_not_found")
        row = session.get(
            MoviePlaybackState,
            movie_id,
            populate_existing=True,
            with_for_update=True,
        )
        if row is None:
            if update.expected_version != 0:
                raise ProgressVersionConflict(None)
            current = _as_utc(self._now())
            row = MoviePlaybackState(
                movie_id=movie_id,
                position_seconds=result.position_seconds,
                duration_seconds=result.duration_seconds,
                completed=result.completed,
                version=1,
                last_watched_at=current,
                updated_at=current,
            )
            session.add(row)
        else:
            if row.version != update.expected_version:
                raise ProgressVersionConflict(_state_view(row))
            current = _as_utc(self._now())
            row.position_seconds = result.position_seconds
            row.duration_seconds = result.duration_seconds
            row.completed = result.completed
            row.version += 1
            row.last_watched_at = current
            row.updated_at = current
        session.flush()
        return _state_view(row)


def _state_view(row: MoviePlaybackState) -> MoviePlaybackStateView:
    return MoviePlaybackStateView(
        movie_id=row.movie_id,
        position_seconds=Decimal(row.position_seconds),
        duration_seconds=(
            Decimal(row.duration_seconds) if row.duration_seconds is not None else None
        ),
        completed=row.completed,
        version=row.version,
        last_watched_at=(
            _as_utc(row.last_watched_at) if row.last_watched_at is not None else None
        ),
        updated_at=_as_utc(row.updated_at),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "CompletionState",
    "MAX_PROGRESS_SECONDS",
    "MoviePlaybackStateService",
    "MoviePlaybackStateView",
    "ProgressProblem",
    "ProgressUpdate",
    "ProgressVersionConflict",
    "completion_state",
]
