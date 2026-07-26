from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict

from sakuraplayer.catalog.api import MovieSummaryOutput
from sakuraplayer.discovery.ranking_query import (
    RankingQueryProblem,
    RankingQueryService,
)
from sakuraplayer.identity.api import ApiProblem


class RankingItemOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    movie: MovieSummaryOutput


class RankingPageOutput(BaseModel):
    board: str
    year: int | None
    available_years: list[int]
    synced_at: datetime
    items: list[RankingItemOutput]
    next_cursor: str | None


def create_ranking_api(
    service: RankingQueryService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["Discovery"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.get("/rankings", response_model=RankingPageOutput)
    def get_ranking(
        response: Response,
        board: Literal["daily", "weekly", "monthly", "top250"],
        year: int | None = Query(default=None, ge=2008, le=2200),
        cursor: str | None = None,
        limit: int = Query(default=24, ge=1, le=100),
    ) -> RankingPageOutput:
        try:
            page = service.get_ranking(
                board=board,
                year=year,
                cursor=cursor,
                limit=limit,
            )
        except RankingQueryProblem as error:
            raise ApiProblem(
                status_code=error.status_code,
                code=error.code,
                message=(
                    "Ranking snapshot is unavailable"
                    if error.code == "ranking_snapshot_unavailable"
                    else "Ranking request failed"
                ),
                details=error.details or None,
            ) from None
        response.headers["Cache-Control"] = "no-store"
        return RankingPageOutput.model_validate(page, from_attributes=True)

    return router


__all__ = ["create_ranking_api"]
