from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.resources.models import Movie, ResourceSource


@dataclass(frozen=True)
class MetadataCandidate:
    movie_id: uuid.UUID
    normalized_number: str
    publish_date: date | None
    reason: str


class InitialScopeSelector:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        initial_limit: int = 5_000,
    ) -> None:
        if initial_limit <= 0:
            raise ValueError("initial limit must be positive")
        self._session_factory = session_factory
        self._initial_limit = initial_limit

    def select_initial(self, *, as_of: date) -> list[MetadataCandidate]:
        if not isinstance(as_of, date):
            raise TypeError("as_of must be a date")
        cutoff = as_of - timedelta(days=89)
        candidates = self._candidate_rows().subquery()
        statement = (
            select(
                candidates.c.movie_id,
                candidates.c.normalized_number,
                candidates.c.publish_date,
            )
            .where(
                candidates.c.publish_date >= cutoff,
                candidates.c.publish_date <= as_of,
            )
            .order_by(
                candidates.c.publish_date.desc(),
                candidates.c.normalized_number.asc(),
            )
            .limit(self._initial_limit)
        )
        with self._session_factory() as session:
            return [
                MetadataCandidate(
                    movie_id=row.movie_id,
                    normalized_number=row.normalized_number,
                    publish_date=row.publish_date,
                    reason="initial",
                )
                for row in session.execute(statement)
            ]

    def iter_history(self, *, as_of: date) -> Iterator[MetadataCandidate]:
        if not isinstance(as_of, date):
            raise TypeError("as_of must be a date")
        cutoff = as_of - timedelta(days=89)
        candidates = self._candidate_rows().subquery()
        initial_ids = (
            select(candidates.c.movie_id)
            .where(
                candidates.c.publish_date >= cutoff,
                candidates.c.publish_date <= as_of,
            )
            .order_by(
                candidates.c.publish_date.desc(),
                candidates.c.normalized_number.asc(),
            )
            .limit(self._initial_limit)
        )
        statement = (
            select(
                candidates.c.movie_id,
                candidates.c.normalized_number,
                candidates.c.publish_date,
            )
            .where(candidates.c.movie_id.not_in(initial_ids))
            .order_by(
                candidates.c.publish_date.desc().nulls_last(),
                candidates.c.normalized_number.asc(),
            )
        )
        with self._session_factory() as session:
            rows = session.execute(statement.execution_options(yield_per=1_000))
            for row in rows:
                yield MetadataCandidate(
                    movie_id=row.movie_id,
                    normalized_number=row.normalized_number,
                    publish_date=row.publish_date,
                    reason="history",
                )

    @staticmethod
    def _candidate_rows() -> Select:
        return (
            select(
                Movie.id.label("movie_id"),
                Movie.normalized_number.label("normalized_number"),
                func.max(ResourceSource.publish_date).label("publish_date"),
            )
            .join(ResourceSource, ResourceSource.movie_id == Movie.id)
            .where(
                Movie.catalog_state == "raw_only",
                ResourceSource.identification_status.in_(("identified", "manual")),
            )
            .group_by(Movie.id, Movie.normalized_number)
        )
