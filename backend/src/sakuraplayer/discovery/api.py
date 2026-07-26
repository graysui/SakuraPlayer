from __future__ import annotations

from collections.abc import Callable
import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from sakuraplayer.catalog.api import ActorSummaryOutput, MovieSummaryOutput
from sakuraplayer.catalog.query_service import CatalogProblem
from sakuraplayer.discovery.favorites import FavoriteProblem, FavoriteService
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.identity.api import ApiProblem


class PendingMetadataOutput(BaseModel):
    number: str
    state: str
    metadata_job_id: uuid.UUID


class SearchResultOutput(BaseModel):
    movies: list[MovieSummaryOutput]
    actors: list[ActorSummaryOutput]
    pending_metadata: list[PendingMetadataOutput]


def create_discovery_api(
    search: SearchService,
    favorites: FavoriteService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.get("/search", tags=["Discovery"], response_model=SearchResultOutput)
    def global_search(
        response: Response,
        q: str = Query(min_length=1, max_length=200),
        limit: int = Query(default=24, ge=1, le=100),
    ) -> SearchResultOutput:
        try:
            result = search.search(q, limit=limit)
        except CatalogProblem as error:
            raise _api_problem(error.status_code, error.code) from None
        response.headers["Cache-Control"] = "no-store"
        return SearchResultOutput(
            movies=[MovieSummaryOutput.model_validate(item) for item in result.movies],
            actors=[ActorSummaryOutput.model_validate(item) for item in result.actors],
            pending_metadata=[
                PendingMetadataOutput.model_validate(item, from_attributes=True)
                for item in result.pending_metadata
            ],
        )

    @router.put("/movies/{movie_id}/favorite", tags=["Catalog"], status_code=204)
    def favorite_movie(movie_id: uuid.UUID) -> Response:
        _set_favorite(favorites, "movie", movie_id, enabled=True)
        return Response(status_code=204)

    @router.delete("/movies/{movie_id}/favorite", tags=["Catalog"], status_code=204)
    def unfavorite_movie(movie_id: uuid.UUID) -> Response:
        _set_favorite(favorites, "movie", movie_id, enabled=False)
        return Response(status_code=204)

    @router.put("/actors/{actor_id}/favorite", tags=["Catalog"], status_code=204)
    def favorite_actor(actor_id: uuid.UUID) -> Response:
        _set_favorite(favorites, "actor", actor_id, enabled=True)
        return Response(status_code=204)

    @router.delete("/actors/{actor_id}/favorite", tags=["Catalog"], status_code=204)
    def unfavorite_actor(actor_id: uuid.UUID) -> Response:
        _set_favorite(favorites, "actor", actor_id, enabled=False)
        return Response(status_code=204)

    return router


def _set_favorite(
    service: FavoriteService,
    target_type: str,
    target_id: uuid.UUID,
    *,
    enabled: bool,
) -> None:
    try:
        service.set_favorite(target_type, target_id, enabled=enabled)
    except FavoriteProblem as error:
        raise _api_problem(error.status_code, error.code) from None


def _api_problem(status_code: int, code: str) -> ApiProblem:
    return ApiProblem(
        status_code=status_code,
        code=code,
        message=(
            "Requested resource was not found"
            if code == "resource_not_found"
            else "Discovery request failed"
        ),
    )


__all__ = ["create_discovery_api"]
