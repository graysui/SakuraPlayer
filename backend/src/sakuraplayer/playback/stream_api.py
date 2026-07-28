from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict

from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem
from sakuraplayer.identity.api import ApiProblem
from sakuraplayer.identity.domain import CurrentAdmin
from sakuraplayer.playback.progress_api import PlaybackProgressOutput
from sakuraplayer.playback.resolver import PlaybackStreamResolver
from sakuraplayer.playback.session import (
    PlaybackManifest,
    PlaybackProblem,
    PlaybackSessionService,
)


class PlaybackSessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_id: uuid.UUID
    mode: Literal["original", "compatibility"]
    platform: Literal["windows", "harmonyos"]
    client_instance_id: uuid.UUID


class PlaybackMediaOutput(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    name: str
    size_bytes: int
    duration_seconds: int | None
    sequence_no: int
    is_valid: bool


class PlaybackSubtitleOutput(BaseModel):
    id: uuid.UUID
    media_id: uuid.UUID | None
    name: str
    format: str
    language: str | None
    selected_by_default: bool


class PlaybackQueueOutput(BaseModel):
    session_id: uuid.UUID
    media: PlaybackMediaOutput
    stream_url: str


class PlaybackManifestOutput(BaseModel):
    session_id: uuid.UUID
    cache_job_id: uuid.UUID
    mode: Literal["original", "compatibility"]
    platform: Literal["windows", "harmonyos"]
    stream_url: str
    expires_at: datetime
    subtitle_cache_expires_at: datetime
    required_user_agent: str
    embedded_tracks_source: Literal["client_player"]
    media_queue: list[PlaybackQueueOutput]
    subtitles: list[PlaybackSubtitleOutput]
    progress: PlaybackProgressOutput | None


def create_playback_api(
    service: PlaybackSessionService,
    resolver: PlaybackStreamResolver,
    *,
    current_admin_dependency: Callable[..., CurrentAdmin],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Playback"])

    @router.post(
        "/cache-jobs/{cache_job_id}/playback-sessions",
        response_model=PlaybackManifestOutput,
        status_code=201,
    )
    async def create_session(
        cache_job_id: uuid.UUID,
        payload: PlaybackSessionInput,
        admin: CurrentAdmin = Depends(current_admin_dependency),
    ) -> PlaybackManifestOutput:
        try:
            manifest = await run_in_threadpool(
                service.create,
                admin=admin,
                cache_job_id=cache_job_id,
                media_id=payload.media_id,
                mode=payload.mode,
                platform=payload.platform,
                client_instance_id=payload.client_instance_id,
            )
        except PlaybackProblem as error:
            raise _playback_problem(error) from None
        return _manifest_output(manifest)

    @router.get("/playback/streams/{playback_session_id}", status_code=302)
    async def redirect_stream(
        playback_session_id: uuid.UUID,
        expires: int,
        signature: str,
        user_agent: str = Header(alias="User-Agent"),
    ) -> RedirectResponse:
        try:
            context = await run_in_threadpool(
                service.validate_stream,
                playback_session_id=playback_session_id,
                expires=expires,
                signature=signature,
                user_agent=user_agent,
            )
            location = await resolver.resolve(context)
        except PlaybackProblem as error:
            raise _playback_problem(error) from None
        except Cloud115Problem as error:
            raise _cloud_problem(error) from None
        return RedirectResponse(
            location,
            status_code=302,
            headers={"Cache-Control": "no-store"},
        )

    return router


def _manifest_output(manifest: PlaybackManifest) -> PlaybackManifestOutput:
    return PlaybackManifestOutput(
        session_id=manifest.session_id,
        cache_job_id=manifest.cache_job_id,
        mode=manifest.mode,
        platform=manifest.platform,
        stream_url=manifest.stream_url,
        expires_at=manifest.expires_at,
        subtitle_cache_expires_at=manifest.subtitle_cache_expires_at,
        required_user_agent=manifest.required_user_agent,
        embedded_tracks_source=manifest.embedded_tracks_source,
        media_queue=[
            PlaybackQueueOutput(
                session_id=item.session_id,
                media=PlaybackMediaOutput(
                    id=item.media.id,
                    candidate_id=item.media.candidate_id,
                    name=item.media.name,
                    size_bytes=item.media.size_bytes,
                    duration_seconds=item.media.duration_seconds,
                    sequence_no=item.media.sequence_no,
                    is_valid=item.media.is_valid,
                ),
                stream_url=item.stream_url,
            )
            for item in manifest.media_queue
        ],
        subtitles=[
            PlaybackSubtitleOutput(
                id=item.id,
                media_id=item.media_id,
                name=item.name,
                format=item.format,
                language=item.language,
                selected_by_default=item.selected_by_default,
            )
            for item in manifest.subtitles
        ],
        progress=(
            PlaybackProgressOutput(
                position_seconds=float(manifest.progress.position_seconds),
                duration_seconds=(
                    float(manifest.progress.duration_seconds)
                    if manifest.progress.duration_seconds is not None
                    else None
                ),
                completed=manifest.progress.completed,
                version=manifest.progress.version,
            )
            if manifest.progress is not None
            else None
        ),
    )


def _playback_problem(error: PlaybackProblem) -> ApiProblem:
    return ApiProblem(
        status_code=error.status_code,
        code=error.code,
        message="Playback session is not available",
    )


def _cloud_problem(error: Cloud115Problem) -> ApiProblem:
    statuses = {
        "cloud115_credentials_expired": 422,
        "cloud115_file_not_found": 404,
        "cloud115_original_unavailable": 422,
        "cloud115_hls_membership_required": 422,
        "cloud115_hls_not_ready": 503,
        "cloud115_hls_unavailable": 502,
        "cloud115_rate_limited": 429,
        "cloud115_unavailable": 503,
        "cloud115_protocol_error": 502,
    }
    return ApiProblem(
        status_code=statuses.get(error.code, 502),
        code=error.code,
        message="Cloud115 playback stream is not available",
        retry_after_seconds=error.retry_after_seconds,
    )


__all__ = ["PlaybackManifestOutput", "PlaybackSessionInput", "create_playback_api"]
