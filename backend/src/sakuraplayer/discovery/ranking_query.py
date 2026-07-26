from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Protocol
import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.query_service import CatalogQueryService, MovieSummaryView
from sakuraplayer.discovery.models import (
    RankingEntry,
    RankingSnapshot,
    RankingSyncRequest,
)
from sakuraplayer.discovery.ranking_sync import validate_ranking_scope
from sakuraplayer.resources.models import Movie, ResourceSource


_ACTIVE_SOURCE_STATES = ("identified", "manual")
_CREDENTIAL_STATUSES = {"configured", "not_configured", "invalid"}


class MetadataCompletion(Protocol):
    state: str


class MetadataCompletionPort(Protocol):
    def ensure_ranking_priority(
        self,
        *,
        movie_id: uuid.UUID,
        normalized_number: str,
        sort_date,
    ) -> MetadataCompletion: ...


class RankingQueryProblem(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        super().__init__(code)


@dataclass(frozen=True)
class RankingItemView:
    rank: int
    movie: MovieSummaryView


@dataclass(frozen=True)
class RankingPageView:
    board: str
    year: int | None
    available_years: list[int]
    synced_at: datetime
    items: list[RankingItemView]
    next_cursor: str | None


class RankingQueryService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        catalog: CatalogQueryService,
        completion: MetadataCompletionPort,
        credential_status: Callable[[], str],
        current_year: Callable[[], int],
    ) -> None:
        self._session_factory = session_factory
        self._catalog = catalog
        self._completion = completion
        self._credential_status = credential_status
        self._current_year = current_year

    def get_ranking(
        self,
        *,
        board: str,
        year: int | None,
        cursor: str | None,
        limit: int,
    ) -> RankingPageView:
        current_year = self._current_year()
        try:
            validate_ranking_scope(board, year, current_year=current_year)
        except ValueError:
            raise self._validation_problem() from None
        if limit < 1 or limit > 100:
            raise self._validation_problem()
        cursor_payload = _decode_cursor(cursor, board=board, year=year)
        with self._session_factory() as session:
            snapshot = self._snapshot(
                session,
                board=board,
                year=year,
                cursor=cursor_payload,
            )
            if snapshot is None:
                raise self._unavailable(session, board=board, year=year)
            after_rank = int(cursor_payload["rank"]) if cursor_payload else 0
            rows = list(
                session.execute(
                    select(RankingEntry, Movie)
                    .join(
                        Movie,
                        Movie.normalized_number == RankingEntry.normalized_number,
                    )
                    .where(
                        RankingEntry.snapshot_id == snapshot.id,
                        RankingEntry.rank > after_rank,
                        _has_active_source(Movie.id),
                    )
                    .order_by(RankingEntry.rank)
                )
            )
            available_years = self._available_years(
                board=board,
                current_year=current_year,
            )

        visible: list[RankingItemView] = []
        for offset in range(0, len(rows), 100):
            candidates: list[tuple[RankingEntry, uuid.UUID]] = []
            for entry, movie in rows[offset : offset + 100]:
                if movie.catalog_state == "core_ready":
                    candidates.append((entry, movie.id))
                    continue
                outcome = self._completion.ensure_ranking_priority(
                    movie_id=movie.id,
                    normalized_number=movie.normalized_number,
                    sort_date=None,
                )
                if outcome.state == "completed":
                    candidates.append((entry, movie.id))
            summaries = self._catalog.movie_summaries_by_ids(
                tuple(movie_id for _, movie_id in candidates)
            )
            summaries_by_id = {item.id: item for item in summaries}
            visible.extend(
                RankingItemView(rank=entry.rank, movie=summaries_by_id[movie_id])
                for entry, movie_id in candidates
                if movie_id in summaries_by_id
            )
            if len(visible) > limit:
                break

        items = visible[:limit]
        next_cursor = None
        if len(visible) > limit and items:
            next_cursor = _encode_cursor(
                board=board,
                year=year,
                snapshot_id=snapshot.id,
                rank=items[-1].rank,
            )
        return RankingPageView(
            board=board,
            year=year,
            available_years=available_years,
            synced_at=_aware_utc(snapshot.source_synced_at),
            items=items,
            next_cursor=next_cursor,
        )

    def _snapshot(
        self,
        session: Session,
        *,
        board: str,
        year: int | None,
        cursor: dict[str, Any] | None,
    ) -> RankingSnapshot | None:
        if cursor is None:
            return session.scalar(
                select(RankingSnapshot).where(
                    RankingSnapshot.board == board,
                    RankingSnapshot.year == year,
                    RankingSnapshot.status == "current",
                )
            )
        snapshot = session.scalar(
            select(RankingSnapshot).where(
                RankingSnapshot.id == uuid.UUID(cursor["snapshot"]),
                RankingSnapshot.board == board,
                RankingSnapshot.year == year,
                RankingSnapshot.status.in_(("current", "superseded")),
            )
        )
        if snapshot is None:
            raise self._validation_problem()
        return snapshot

    def _unavailable(
        self,
        session: Session,
        *,
        board: str,
        year: int | None,
    ) -> RankingQueryProblem:
        status = "configured"
        if board == "top250":
            status = self._credential_status()
            if status not in _CREDENTIAL_STATUSES:
                status = "invalid"
        latest_failure = session.scalar(
            select(RankingSyncRequest)
            .where(
                RankingSyncRequest.board == board,
                RankingSyncRequest.year == year,
                RankingSyncRequest.status == "failed",
            )
            .order_by(
                RankingSyncRequest.completed_at.desc(),
                RankingSyncRequest.id.desc(),
            )
            .limit(1)
        )
        last_error = latest_failure.failure_code if latest_failure is not None else None
        if board == "top250" and status == "not_configured":
            reason = "credentials_not_configured"
        elif board == "top250" and (
            status == "invalid" or last_error == "javdb_credentials_invalid"
        ):
            reason = "credentials_invalid"
        elif latest_failure is not None:
            reason = "sync_failed"
        else:
            reason = "never_synced"
        details: dict[str, object] = {"reason": reason}
        if last_error is not None:
            details["last_error_code"] = last_error
        return RankingQueryProblem(
            status_code=503,
            code="ranking_snapshot_unavailable",
            details=details,
        )

    @staticmethod
    def _available_years(*, board: str, current_year: int) -> list[int]:
        if board != "top250":
            return []
        return list(range(current_year, 2007, -1))[:100]

    @staticmethod
    def _validation_problem() -> RankingQueryProblem:
        return RankingQueryProblem(status_code=422, code="validation_failed")


def _has_active_source(movie_id):
    return exists(
        select(ResourceSource.id).where(
            ResourceSource.movie_id == movie_id,
            ResourceSource.identification_status.in_(_ACTIVE_SOURCE_STATES),
        )
    )


def _encode_cursor(
    *,
    board: str,
    year: int | None,
    snapshot_id: uuid.UUID,
    rank: int,
) -> str:
    payload = {
        "board": board,
        "rank": rank,
        "snapshot": str(snapshot_id),
        "v": 1,
        "year": year,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_cursor(
    cursor: str | None,
    *,
    board: str,
    year: int | None,
) -> dict[str, Any] | None:
    if cursor is None:
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {
            "board",
            "rank",
            "snapshot",
            "v",
            "year",
        }:
            raise ValueError
        if (
            payload["board"] != board
            or payload["year"] != year
            or type(payload["v"]) is not int
            or payload["v"] != 1
            or type(payload["rank"]) is not int
            or payload["rank"] < 1
            or not isinstance(payload["snapshot"], str)
        ):
            raise ValueError
        uuid.UUID(payload["snapshot"])
        return payload
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        raise RankingQueryProblem(status_code=422, code="validation_failed") from None


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "RankingItemView",
    "RankingPageView",
    "RankingQueryProblem",
    "RankingQueryService",
]
