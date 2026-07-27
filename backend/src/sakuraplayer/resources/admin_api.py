from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sakuraplayer.identity.api import ApiProblem
from sakuraplayer.resources.movie_source_service import (
    MovieDetailView,
    MovieSourceProblem,
    MovieSourceService,
)


class MergeMoviesInput(BaseModel):
    target_movie_id: uuid.UUID
    source_movie_ids: list[uuid.UUID] = Field(min_length=1)


class SplitMovieSourceInput(BaseModel):
    new_normalized_number: str = Field(min_length=1, max_length=128)


class MovieSourceOutput(BaseModel):
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


class MovieDetailOutput(BaseModel):
    id: uuid.UUID
    number: str
    title: str
    title_original: str | None
    cover_url: str | None
    publish_date: date | None
    labels: list[str]
    favorite: bool
    source_count: int
    progress: None
    actors: list[object]
    tags: list[str]
    plot_image_urls: list[str]
    sources: list[MovieSourceOutput]


def create_movie_source_admin_api(
    service: MovieSourceService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin",
        tags=["Admin"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.post("/movies/merge", response_model=MovieDetailOutput)
    def merge_movies(body: MergeMoviesInput) -> MovieDetailOutput:
        try:
            result = service.merge(
                target_movie_id=body.target_movie_id,
                source_movie_ids=body.source_movie_ids,
            )
        except MovieSourceProblem as error:
            raise _api_problem(error) from None
        return _movie_detail_output(result)

    @router.post(
        "/movies/{movie_id}/sources/{source_id}/split",
        response_model=MovieDetailOutput,
        status_code=201,
    )
    def split_movie_source(
        movie_id: uuid.UUID,
        source_id: uuid.UUID,
        body: SplitMovieSourceInput,
    ) -> MovieDetailOutput:
        try:
            result = service.split(
                movie_id=movie_id,
                source_id=source_id,
                new_normalized_number=body.new_normalized_number,
            )
        except MovieSourceProblem as error:
            raise _api_problem(error) from None
        return _movie_detail_output(result)

    return router


def _movie_detail_output(view: MovieDetailView) -> MovieDetailOutput:
    return MovieDetailOutput.model_validate(
        {
            **view.__dict__,
            "sources": [
                MovieSourceOutput(**source.__dict__) for source in view.sources
            ],
        }
    )


def _api_problem(error: MovieSourceProblem) -> ApiProblem:
    messages = {
        "movie_merge_conflict": "Movie merge conflicts with current relations",
        "resource_not_found": "Movie or source was not found",
        "validation_failed": "Request validation failed",
    }
    return ApiProblem(
        status_code=error.status_code,
        code=error.code,
        message=messages[error.code],
    )
