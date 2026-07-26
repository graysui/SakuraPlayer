from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from sakuraplayer.catalog.query_service import (
    CatalogProblem,
    CatalogQueryService,
    MovieFilters,
)
from sakuraplayer.identity.api import ApiProblem


class PlaybackProgressOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position_seconds: float
    duration_seconds: float | None
    completed: bool
    version: int


class MovieSummaryOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    title: str
    title_original: str | None
    cover_url: str | None
    publish_date: date | None
    labels: list[str]
    favorite: bool
    source_count: int
    progress: PlaybackProgressOutput | None


class ActorSummaryOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    name_ja: str | None
    name_zh: str | None
    aliases: list[str]
    profile_url: str | None
    favorite: bool


class MovieSourceOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    website: str
    external_post_id: int
    title: str
    publish_date: date | None
    category: str
    labels: list[str]
    resource_size_mb: int | None
    video_file_size_bytes: int | None
    availability: str


class MovieDetailOutput(MovieSummaryOutput):
    release_date: date | None
    maker: str | None
    series: str | None
    director: str | None
    score: float | None
    description: str | None
    description_original: str | None
    actors: list[ActorSummaryOutput]
    tags: list[str]
    plot_image_urls: list[str]
    sources: list[MovieSourceOutput]


class ActorDetailOutput(ActorSummaryOutput):
    bio: str | None
    bio_original: str | None
    gallery_urls: list[str]
    movies: list[MovieSummaryOutput]


class MoviePageOutput(BaseModel):
    items: list[MovieSummaryOutput]
    next_cursor: str | None


class ActorPageOutput(BaseModel):
    items: list[ActorSummaryOutput]
    next_cursor: str | None


def create_catalog_api(
    service: CatalogQueryService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["Catalog"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.get("/movies", response_model=MoviePageOutput)
    def list_movies(
        cursor: str | None = None,
        limit: int = Query(default=24, ge=1, le=100),
        categories: str | None = None,
        labels: str | None = None,
        source_website: Literal["sehuatang", "x1080x"] | None = None,
        playable: bool | None = None,
        min_resource_size_mb: int | None = Query(default=None, ge=0),
        max_resource_size_mb: int | None = Query(default=None, ge=0),
        sort: Literal[
            "publish_date_desc",
            "publish_date_asc",
            "number_asc",
        ] = "publish_date_desc",
        favorite: bool = False,
    ) -> MoviePageOutput:
        try:
            page = service.list_movies(
                filters=MovieFilters(
                    categories=_csv(categories),
                    labels=_csv(labels),
                    source_website=source_website,
                    playable=playable,
                    min_resource_size_mb=min_resource_size_mb,
                    max_resource_size_mb=max_resource_size_mb,
                    sort=sort,
                    favorite=favorite,
                ),
                cursor=cursor,
                limit=limit,
            )
        except CatalogProblem as error:
            raise _api_problem(error) from None
        return MoviePageOutput(
            items=[MovieSummaryOutput.model_validate(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @router.get("/movies/{movie_id}", response_model=MovieDetailOutput)
    def get_movie(movie_id: uuid.UUID) -> MovieDetailOutput:
        try:
            return MovieDetailOutput.model_validate(service.get_movie(movie_id))
        except CatalogProblem as error:
            raise _api_problem(error) from None

    @router.get("/actors", response_model=ActorPageOutput)
    def list_actors(
        q: str | None = Query(default=None, min_length=1, max_length=200),
        cursor: str | None = None,
        limit: int = Query(default=24, ge=1, le=100),
        favorite: bool = False,
    ) -> ActorPageOutput:
        try:
            page = service.list_actors(
                q=q,
                cursor=cursor,
                limit=limit,
                favorite=favorite,
            )
        except CatalogProblem as error:
            raise _api_problem(error) from None
        return ActorPageOutput(
            items=[ActorSummaryOutput.model_validate(item) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @router.get("/actors/{actor_id}", response_model=ActorDetailOutput)
    def get_actor(actor_id: uuid.UUID) -> ActorDetailOutput:
        try:
            return ActorDetailOutput.model_validate(service.get_actor(actor_id))
        except CatalogProblem as error:
            raise _api_problem(error) from None

    @router.get("/catalog/images/{image_id}", response_class=FileResponse)
    def get_catalog_image(image_id: uuid.UUID) -> FileResponse:
        try:
            image = service.resolve_image(image_id)
        except CatalogProblem as error:
            raise _api_problem(error) from None
        return FileResponse(image.path, media_type=image.media_type)

    return router


def _csv(value: str | None) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    items = tuple(item.strip() for item in value.split(","))
    if len(items) > 100 or any(not item for item in items):
        raise ApiProblem(
            status_code=422,
            code="validation_failed",
            message="Request validation failed",
        )
    return items


def _api_problem(error: CatalogProblem) -> ApiProblem:
    return ApiProblem(
        status_code=error.status_code,
        code=error.code,
        message=(
            "Requested resource was not found"
            if error.code == "resource_not_found"
            else "Catalog request failed"
        ),
    )


__all__ = [
    "ActorSummaryOutput",
    "MovieSummaryOutput",
    "create_catalog_api",
]
