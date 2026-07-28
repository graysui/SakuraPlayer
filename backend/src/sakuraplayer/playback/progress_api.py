from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from sakuraplayer.identity.api import ApiProblem
from sakuraplayer.identity.domain import CurrentAdmin
from sakuraplayer.playback.heartbeat import (
    PlaybackHeartbeatProblem,
    PlaybackHeartbeatService,
)
from sakuraplayer.playback.progress import (
    MAX_PROGRESS_SECONDS,
    MoviePlaybackStateService,
    MoviePlaybackStateView,
    ProgressProblem,
    ProgressUpdate,
    ProgressVersionConflict,
)


class ProgressUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_seconds: float = Field(
        ge=0,
        le=float(MAX_PROGRESS_SECONDS),
        allow_inf_nan=False,
    )
    duration_seconds: float | None = Field(
        ge=0.001,
        le=float(MAX_PROGRESS_SECONDS),
        allow_inf_nan=False,
    )
    version: int = Field(ge=0)

    @field_validator("position_seconds", "duration_seconds", mode="before")
    @classmethod
    def require_json_number(cls, value: object) -> object:
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise ValueError("progress value must be a JSON number")
        return value

    @field_validator("version", mode="before")
    @classmethod
    def require_json_integer(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("version must be a JSON integer")
        return value

    def to_domain(self) -> ProgressUpdate:
        return ProgressUpdate(
            expected_version=self.version,
            position_seconds=Decimal(str(self.position_seconds)),
            duration_seconds=(
                Decimal(str(self.duration_seconds))
                if self.duration_seconds is not None
                else None
            ),
        )


class PlaybackProgressOutput(BaseModel):
    position_seconds: float
    duration_seconds: float | None
    completed: bool
    version: int


class PlaybackHeartbeatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_instance_id: uuid.UUID
    progress: ProgressUpdateInput | None = None
    playing: StrictBool = True


class PlaybackHeartbeatOutput(BaseModel):
    lease_expires_at: datetime | None
    progress: PlaybackProgressOutput | None


def create_progress_api(
    progress_service: MoviePlaybackStateService,
    heartbeat_service: PlaybackHeartbeatService,
    *,
    current_admin_dependency: Callable[..., CurrentAdmin],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Playback"])

    @router.put(
        "/movies/{movie_id}/progress",
        response_model=PlaybackProgressOutput,
        responses={
            404: {"description": "Movie not found"},
            409: {"description": "Progress version conflict"},
        },
    )
    async def update_movie_progress(
        movie_id: uuid.UUID,
        payload: ProgressUpdateInput,
        _admin: CurrentAdmin = Depends(current_admin_dependency),
    ) -> PlaybackProgressOutput:
        try:
            state = await run_in_threadpool(
                progress_service.update,
                movie_id=movie_id,
                expected_version=payload.version,
                position_seconds=Decimal(str(payload.position_seconds)),
                duration_seconds=(
                    Decimal(str(payload.duration_seconds))
                    if payload.duration_seconds is not None
                    else None
                ),
            )
        except (ProgressProblem, ValueError) as error:
            raise _progress_problem(error) from None
        return _progress_output(state)

    @router.put(
        "/playback/sessions/{playback_session_id}/heartbeat",
        response_model=PlaybackHeartbeatOutput,
        responses={
            409: {"description": "Playback or progress state conflict"},
        },
    )
    async def heartbeat_playback_session(
        playback_session_id: uuid.UUID,
        payload: PlaybackHeartbeatInput,
        admin: CurrentAdmin = Depends(current_admin_dependency),
    ) -> PlaybackHeartbeatOutput:
        try:
            result = await run_in_threadpool(
                heartbeat_service.heartbeat,
                admin=admin,
                playback_session_id=playback_session_id,
                client_instance_id=payload.client_instance_id,
                progress=(
                    payload.progress.to_domain()
                    if payload.progress is not None
                    else None
                ),
                playing=payload.playing,
            )
        except (ProgressProblem, ValueError) as error:
            raise _progress_problem(error) from None
        except PlaybackHeartbeatProblem:
            raise ApiProblem(
                status_code=409,
                code="state_conflict",
                message="Playback heartbeat conflicts with current state",
            ) from None
        return PlaybackHeartbeatOutput(
            lease_expires_at=result.lease_expires_at,
            progress=(
                _progress_output(result.progress)
                if result.progress is not None
                else None
            ),
        )

    return router


def _progress_output(state: MoviePlaybackStateView) -> PlaybackProgressOutput:
    return PlaybackProgressOutput(
        position_seconds=float(state.position_seconds),
        duration_seconds=(
            float(state.duration_seconds)
            if state.duration_seconds is not None
            else None
        ),
        completed=state.completed,
        version=state.version,
    )


def _progress_problem(error: ProgressProblem | ValueError) -> ApiProblem:
    if isinstance(error, ValueError):
        return ApiProblem(
            status_code=422,
            code="validation_failed",
            message="Playback progress request failed validation",
        )
    details: dict[str, object] | None = None
    if isinstance(error, ProgressVersionConflict):
        details = {
            "progress": (
                _progress_output(error.authoritative).model_dump()
                if error.authoritative is not None
                else None
            )
        }
    return ApiProblem(
        status_code=error.status_code,
        code=error.code,
        message=(
            "Playback progress version conflicts with current state"
            if isinstance(error, ProgressVersionConflict)
            else "Playback progress request failed"
        ),
        details=details,
    )


__all__ = [
    "PlaybackHeartbeatInput",
    "PlaybackProgressOutput",
    "ProgressUpdateInput",
    "create_progress_api",
]
