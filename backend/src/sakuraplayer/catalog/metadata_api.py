from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.metadata_queue import (
    MetadataQueue,
    MetadataQueueControlSnapshot,
    MetadataQueueProblem,
    retryable_enrichment_stages,
)
from sakuraplayer.catalog.metadata_state import ALL_STAGES
from sakuraplayer.catalog.models import MetadataJob, MetadataStage
from sakuraplayer.identity.api import ApiProblem
from sakuraplayer.resources.models import Movie

MetadataStatus = Literal[
    "queued",
    "running",
    "completed",
    "completed_with_warnings",
    "failed",
]
EnrichmentStage = Literal[
    "images",
    "dmm",
    "actor_map",
    "gfriends",
    "translation",
]


@dataclass(frozen=True)
class MetadataJobView:
    id: uuid.UUID
    movie_id: uuid.UUID
    number: str
    priority: int
    reason: str
    retry_mode: str
    requested_stages: list[str]
    parent_job_id: uuid.UUID | None
    status: str
    stage: str | None
    attempt_no: int
    elapsed_ms: int | None
    error_code: str | None
    stages: list[MetadataStageView]
    retryable_stages: list[str]
    created_at: datetime


@dataclass(frozen=True)
class MetadataStageView:
    stage: str
    status: str
    error_code: str | None


@dataclass(frozen=True)
class MetadataJobPage:
    items: list[MetadataJobView]
    next_cursor: str | None


class MetadataAdminService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        queue: MetadataQueue,
    ) -> None:
        self._session_factory = session_factory
        self._queue = queue

    def list_jobs(
        self,
        *,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> MetadataJobPage:
        cursor_values = self._decode_cursor(cursor, status=status)
        statement = select(MetadataJob)
        if status is not None:
            statement = statement.where(MetadataJob.status == status)
        if cursor_values is not None:
            created_at, job_id = cursor_values
            statement = statement.where(
                tuple_(MetadataJob.created_at, MetadataJob.id)
                < tuple_(created_at, job_id)
            )
        statement = statement.order_by(
            MetadataJob.created_at.desc(),
            MetadataJob.id.desc(),
        ).limit(limit + 1)
        with self._session_factory() as session:
            jobs = list(session.scalars(statement))
            visible = jobs[:limit]
            views = self.views_in_session(session, visible)
        next_cursor = None
        if len(jobs) > limit and visible:
            last = visible[-1]
            next_cursor = self._encode_cursor(last.created_at, last.id, status=status)
        return MetadataJobPage(items=views, next_cursor=next_cursor)

    def retry(self, job_id: uuid.UUID) -> MetadataJobView:
        outcome = self._queue.manual_retry(job_id)
        return self.get(outcome.job_id)

    def set_paused(self, paused: bool) -> MetadataQueueControlSnapshot:
        return self._queue.set_paused(paused)

    def retry_enrichment(
        self,
        job_id: uuid.UUID,
        *,
        stages: tuple[str, ...],
    ) -> MetadataJobView:
        outcome = self._queue.retry_enrichment(job_id, stages=stages)
        return self.get(outcome.job_id)

    def get(self, job_id: uuid.UUID) -> MetadataJobView:
        with self._session_factory() as session:
            job = session.get(MetadataJob, job_id)
            if job is None:
                raise MetadataQueueProblem(
                    status_code=404,
                    code="metadata_job_not_found",
                )
            return self.views_in_session(session, [job])[0]

    @staticmethod
    def views_in_session(
        session: Session,
        jobs: list[MetadataJob],
    ) -> list[MetadataJobView]:
        if not jobs:
            return []
        stages_by_job: dict[uuid.UUID, dict[str, MetadataStage]] = {
            job.id: {} for job in jobs
        }
        for stage in session.scalars(
            select(MetadataStage).where(MetadataStage.job_id.in_(stages_by_job))
        ):
            stages_by_job[stage.job_id][stage.stage] = stage
        return [
            MetadataJobView(
                id=job.id,
                movie_id=job.movie_id,
                number=job.normalized_number,
                priority=job.priority,
                reason=job.reason,
                retry_mode=job.retry_mode,
                requested_stages=list(job.requested_stages),
                parent_job_id=job.parent_job_id,
                status=job.status,
                stage=_visible_stage(
                    {name: item.status for name, item in stages_by_job[job.id].items()}
                ),
                attempt_no=job.attempt_no,
                elapsed_ms=job.elapsed_ms,
                error_code=job.failure_code,
                stages=[
                    MetadataStageView(
                        stage=stage,
                        status=stages_by_job[job.id][stage].status,
                        error_code=stages_by_job[job.id][stage].failure_code,
                    )
                    for stage in ALL_STAGES
                    if stage in stages_by_job[job.id]
                ],
                retryable_stages=list(
                    retryable_enrichment_stages(
                        session,
                        job,
                        movie=session.get(Movie, job.movie_id),
                    )
                ),
                created_at=job.created_at,
            )
            for job in jobs
        ]

    @staticmethod
    def _encode_cursor(
        created_at: datetime,
        job_id: uuid.UUID,
        *,
        status: str | None,
    ) -> str:
        payload = json.dumps(
            {
                "created_at": created_at.isoformat(),
                "id": str(job_id),
                "status": status,
                "v": 1,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode_cursor(
        cursor: str | None,
        *,
        status: str | None,
    ) -> tuple[datetime, uuid.UUID] | None:
        if cursor is None:
            return None
        try:
            padding = "=" * (-len(cursor) % 4)
            raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
            payload: Any = json.loads(raw.decode("utf-8"))
            if (
                not isinstance(payload, dict)
                or set(payload) != {"created_at", "id", "status", "v"}
                or payload["v"] != 1
                or not isinstance(payload["created_at"], str)
                or not isinstance(payload["id"], str)
                or payload["status"] != status
            ):
                raise ValueError
            created_at = datetime.fromisoformat(payload["created_at"])
            if created_at.tzinfo is None:
                raise ValueError
            return created_at, uuid.UUID(payload["id"])
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            raise MetadataQueueProblem(
                status_code=422,
                code="validation_failed",
            ) from None


class MetadataStageOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    status: str
    error_code: str | None


class MetadataJobOutput(BaseModel):
    id: uuid.UUID
    movie_id: uuid.UUID
    number: str
    priority: int
    reason: str
    retry_mode: str
    requested_stages: list[str]
    parent_job_id: uuid.UUID | None
    status: str
    stage: str | None
    attempt_no: int
    elapsed_ms: int | None
    error_code: str | None
    stages: list[MetadataStageOutput]
    retryable_stages: list[str]
    created_at: datetime


class MetadataJobPageOutput(BaseModel):
    items: list[MetadataJobOutput]
    next_cursor: str | None


class MetadataQueueControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paused: bool


class MetadataQueueControlOutput(BaseModel):
    paused: bool
    queued: int = Field(ge=0)
    running: int = Field(ge=0, le=3)


class EnrichmentRetryInput(BaseModel):
    stages: list[EnrichmentStage] = Field(min_length=1)

    @field_validator("stages")
    @classmethod
    def stages_are_unique(cls, stages: list[str]) -> list[str]:
        if len(stages) != len(set(stages)):
            raise ValueError("metadata enrichment stages must be unique")
        return stages


def create_metadata_api(
    service: MetadataAdminService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/admin",
        tags=["Admin"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.put("/metadata-queue", response_model=MetadataQueueControlOutput)
    def set_metadata_queue_control(
        body: MetadataQueueControlInput,
    ) -> MetadataQueueControlOutput:
        snapshot = service.set_paused(body.paused)
        return MetadataQueueControlOutput.model_validate(
            snapshot,
            from_attributes=True,
        )

    @router.get("/metadata-jobs", response_model=MetadataJobPageOutput)
    def list_metadata_jobs(
        status: MetadataStatus | None = None,
        cursor: str | None = None,
        limit: int = Query(default=24, ge=1, le=100),
    ) -> MetadataJobPageOutput:
        try:
            page = service.list_jobs(status=status, cursor=cursor, limit=limit)
        except MetadataQueueProblem as error:
            raise _api_problem(error) from None
        return MetadataJobPageOutput(
            items=[MetadataJobOutput(**item.__dict__) for item in page.items],
            next_cursor=page.next_cursor,
        )

    @router.post(
        "/metadata-jobs/{metadata_job_id}/retry",
        response_model=MetadataJobOutput,
        status_code=201,
    )
    def retry_metadata_job(metadata_job_id: uuid.UUID) -> MetadataJobOutput:
        try:
            view = service.retry(metadata_job_id)
        except MetadataQueueProblem as error:
            raise _api_problem(error) from None
        return MetadataJobOutput(**view.__dict__)

    @router.post(
        "/metadata-jobs/{metadata_job_id}/retry-enrichment",
        response_model=MetadataJobOutput,
        status_code=201,
    )
    def retry_metadata_enrichment(
        metadata_job_id: uuid.UUID,
        body: EnrichmentRetryInput,
    ) -> MetadataJobOutput:
        try:
            view = service.retry_enrichment(
                metadata_job_id,
                stages=tuple(body.stages),
            )
        except MetadataQueueProblem as error:
            raise _api_problem(error) from None
        return MetadataJobOutput(**view.__dict__)

    return router


def _visible_stage(stages: dict[str, str]) -> str | None:
    for status in ("running", "pending"):
        for stage in ALL_STAGES:
            if stages.get(stage) == status:
                return stage
    for stage in reversed(ALL_STAGES):
        if stages.get(stage) in {"failed", "warning", "succeeded"}:
            return stage
    return None


def _api_problem(error: MetadataQueueProblem) -> ApiProblem:
    messages = {
        "metadata_job_already_active": "Metadata job is already active",
        "metadata_job_no_retryable_enrichment": "No selected enrichment stage can be retried",
        "metadata_job_not_failed": "Metadata job is not failed",
        "metadata_job_not_found": "Metadata job was not found",
        "validation_failed": "Request validation failed",
    }
    return ApiProblem(
        status_code=error.status_code,
        code=error.code,
        message=messages.get(error.code, "Metadata job request failed"),
    )


__all__ = ["MetadataAdminService", "create_metadata_api"]
