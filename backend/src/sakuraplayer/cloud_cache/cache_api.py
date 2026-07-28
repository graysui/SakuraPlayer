from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from sakuraplayer.cloud_cache.capacity import CacheCapacitySnapshot
from sakuraplayer.cloud_cache.cleanup import CleanupProblem, CleanupQueue
from sakuraplayer.cloud_cache.media_selection_api import MediaSelectionProblem
from sakuraplayer.cloud_cache.play_request import (
    CacheJobView,
    CacheProblem,
    PlayRequestResult,
    PlayRequestService,
)
from sakuraplayer.identity.api import ApiProblem


class PlayRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: uuid.UUID


class RemoteMediaOutput(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    name: str
    size_bytes: int
    duration_seconds: int | None
    sequence_no: int
    is_valid: bool


class SubtitleOutput(BaseModel):
    id: uuid.UUID
    name: str
    format: Literal["srt", "ass", "ssa", "vtt"]
    language: str | None
    selected_by_default: bool


class CacheJobOutput(BaseModel):
    id: uuid.UUID
    movie_id: uuid.UUID
    source_id: uuid.UUID
    status: str
    remote_percent: float
    error_code: str | None
    media_candidates: list[RemoteMediaOutput]
    selected_media_ids: list[uuid.UUID]
    subtitles: list[SubtitleOutput]
    ready_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CacheCapacityOutput(BaseModel):
    running: int
    running_limit: Literal[2] = 2
    queued: int
    queued_limit: Literal[10] = 10
    ready: int
    ready_limit: Literal[20] = 20


class CacheJobPageOutput(BaseModel):
    items: list[CacheJobOutput]
    capacity: CacheCapacityOutput
    next_cursor: str | None


class PlayRequestOutput(BaseModel):
    disposition: Literal["ready", "started", "queued", "reused"]
    wait_deadline: datetime | None = None
    cache_job: CacheJobOutput


class MediaSelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=100,
        json_schema_extra={"uniqueItems": True},
    )

    @field_validator("media_ids")
    @classmethod
    def validate_unique_media_ids(cls, media_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(media_ids)) != len(media_ids):
            raise ValueError("media_ids must be unique")
        return media_ids


def create_cache_api(
    service: PlayRequestService,
    *,
    current_admin_dependency: Callable[..., object],
    cleanup_service: CleanupQueue | None = None,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        tags=["Cache"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.post(
        "/movies/{movie_id}/play-requests",
        response_model=PlayRequestOutput,
        response_model_exclude_none=True,
        responses={200: {"description": "Existing cache job reused."}},
        status_code=202,
    )
    def create_play_request(
        movie_id: uuid.UUID,
        payload: PlayRequestInput,
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> PlayRequestOutput:
        try:
            result = service.create(
                movie_id=movie_id,
                source_id=payload.source_id,
                idempotency_key=idempotency_key,
            )
        except CacheProblem as error:
            raise _api_problem(error) from None
        if result.disposition in {"ready", "reused"}:
            response.status_code = 200
        return _play_request_output(result)

    @router.get("/cache-jobs", response_model=CacheJobPageOutput)
    def list_cache_jobs(
        status: str | None = None,
        cursor: str | None = None,
        limit: int = Query(default=24, ge=1, le=100),
    ) -> CacheJobPageOutput:
        try:
            statuses = _statuses(status)
            page = service.list(statuses=statuses, cursor=cursor, limit=limit)
        except CacheProblem as error:
            raise _api_problem(error) from None
        return CacheJobPageOutput(
            items=[_job_output(item) for item in page.items],
            capacity=_capacity_output(page.capacity),
            next_cursor=page.next_cursor,
        )

    @router.get("/cache-jobs/{cache_job_id}", response_model=CacheJobOutput)
    def get_cache_job(cache_job_id: uuid.UUID) -> CacheJobOutput:
        try:
            return _job_output(service.get(cache_job_id))
        except CacheProblem as error:
            raise _api_problem(error) from None

    @router.put(
        "/cache-jobs/{cache_job_id}/media-selection",
        response_model=CacheJobOutput,
    )
    def select_cache_media(
        cache_job_id: uuid.UUID,
        payload: MediaSelectionInput,
    ) -> CacheJobOutput:
        try:
            service.select_media(
                job_id=cache_job_id,
                media_ids=tuple(payload.media_ids),
            )
            return _job_output(service.get(cache_job_id))
        except MediaSelectionProblem as error:
            raise _selection_api_problem(error) from None
        except CacheProblem as error:
            raise _api_problem(error) from None

    if cleanup_service is not None:

        @router.post(
            "/cache-jobs/{cache_job_id}/cleanup",
            response_model=CacheJobOutput,
            status_code=202,
        )
        def cleanup_cache_job(cache_job_id: uuid.UUID) -> CacheJobOutput:
            try:
                cleanup_service.request(cache_job_id)
                return _job_output(service.get(cache_job_id))
            except CleanupProblem as error:
                raise _cleanup_api_problem(error) from None
            except CacheProblem as error:
                raise _api_problem(error) from None

    return router


def _statuses(value: str | None) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    statuses = tuple(item.strip() for item in value.split(","))
    if len(statuses) > 12 or any(not item for item in statuses):
        raise CacheProblem(status_code=422, code="validation_failed")
    return statuses


def _job_output(job: CacheJobView) -> CacheJobOutput:
    return CacheJobOutput(
        id=job.id,
        movie_id=job.movie_id,
        source_id=job.source_id,
        status=job.status,
        remote_percent=job.remote_percent,
        error_code=job.failure_code,
        media_candidates=[
            RemoteMediaOutput(
                id=item.id,
                candidate_id=item.candidate_id,
                name=item.name,
                size_bytes=item.size_bytes,
                duration_seconds=item.duration_seconds,
                sequence_no=item.sequence_no,
                is_valid=item.is_valid,
            )
            for item in job.media_candidates
        ],
        selected_media_ids=list(job.selected_media_ids),
        subtitles=[
            SubtitleOutput(
                id=item.id,
                name=item.name,
                format=item.format,  # type: ignore[arg-type]
                language=item.language,
                selected_by_default=item.selected_by_default,
            )
            for item in job.subtitles
        ],
        ready_at=job.ready_at,
        expires_at=job.expires_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _capacity_output(snapshot: CacheCapacitySnapshot) -> CacheCapacityOutput:
    return CacheCapacityOutput(
        running=snapshot.running,
        queued=snapshot.queued,
        ready=snapshot.ready,
    )


def _play_request_output(result: PlayRequestResult) -> PlayRequestOutput:
    return PlayRequestOutput(
        disposition=result.disposition,
        wait_deadline=result.wait_deadline,
        cache_job=_job_output(result.job),
    )


def _api_problem(error: CacheProblem) -> ApiProblem:
    message = (
        "Requested resource was not found"
        if error.code == "resource_not_found"
        else "Cache request failed"
    )
    return ApiProblem(
        status_code=error.status_code,
        code=error.code,
        message=message,
    )


def _selection_api_problem(error: MediaSelectionProblem) -> ApiProblem:
    return ApiProblem(
        status_code=error.status_code,
        code=error.code,
        message="Media selection failed",
    )


def _cleanup_api_problem(error: CleanupProblem) -> ApiProblem:
    return ApiProblem(
        status_code=error.status_code,
        code=error.code,
        message="Cache cleanup request failed",
    )


__all__ = [
    "CacheCapacityOutput",
    "CacheJobOutput",
    "PlayRequestOutput",
    "create_cache_api",
]
