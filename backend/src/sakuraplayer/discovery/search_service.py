from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import uuid

from sakuraplayer.catalog.query_service import (
    ActorSummaryView,
    CatalogQueryService,
    MovieSummaryView,
)


class MetadataCompletion(Protocol):
    job_id: uuid.UUID
    state: str


class MetadataCompletionPort(Protocol):
    def ensure_search_priority(
        self,
        *,
        movie_id: uuid.UUID,
        normalized_number: str,
        sort_date,
    ) -> MetadataCompletion: ...


@dataclass(frozen=True)
class PendingMetadataView:
    number: str
    state: str
    metadata_job_id: uuid.UUID


@dataclass(frozen=True)
class SearchResultView:
    movies: list[MovieSummaryView]
    actors: list[ActorSummaryView]
    pending_metadata: list[PendingMetadataView]


class SearchService:
    def __init__(
        self,
        catalog: CatalogQueryService,
        completion: MetadataCompletionPort,
    ) -> None:
        self._catalog = catalog
        self._completion = completion

    def search(self, q: str, *, limit: int) -> SearchResultView:
        result = self._catalog.search_catalog(q, limit=limit)
        pending: list[PendingMetadataView] = []
        if result.raw_candidate is not None:
            outcome = self._completion.ensure_search_priority(
                movie_id=result.raw_candidate.movie_id,
                normalized_number=result.raw_candidate.number,
                sort_date=result.raw_candidate.sort_date,
            )
            if outcome.state == "completed":
                result = self._catalog.search_catalog(q, limit=limit)
            else:
                pending.append(
                    PendingMetadataView(
                        number=result.raw_candidate.number,
                        state=outcome.state,
                        metadata_job_id=outcome.job_id,
                    )
                )
        return SearchResultView(
            movies=result.movies,
            actors=result.actors,
            pending_metadata=pending,
        )


__all__ = [
    "MetadataCompletionPort",
    "PendingMetadataView",
    "SearchResultView",
    "SearchService",
]
