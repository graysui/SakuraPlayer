from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from sakuraplayer.identity.api import ApiProblem
from sakuraplayer.identity.domain import CurrentAdmin
from sakuraplayer.playback.subtitles import (
    SUBTITLE_MEDIA_TYPES,
    SubtitleDownloadService,
    SubtitleProblem,
)


class ApiError(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9_]+$")
    message: str
    request_id: str
    details: dict[str, object] | None = None


def create_subtitle_api(
    service: SubtitleDownloadService,
    *,
    current_admin_dependency: Callable[..., CurrentAdmin],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Playback"])

    @router.get(
        "/playback/sessions/{playback_session_id}/subtitles/{subtitle_id}",
        operation_id="downloadSubtitle",
        response_class=Response,
        responses={
            200: {
                "description": "Subtitle bytes for the application-private cache",
                "headers": {
                    "Content-Disposition": {"schema": {"type": "string"}},
                    "Cache-Control": {"schema": {"type": "string"}},
                    "X-Content-Type-Options": {
                        "schema": {"type": "string", "const": "nosniff"}
                    },
                },
                "content": {
                    media_type: {"schema": {"type": "string", "format": "binary"}}
                    for media_type in sorted(set(SUBTITLE_MEDIA_TYPES.values()))
                },
            },
            401: _error_response("Authentication is required"),
            404: _error_response("Subtitle or managed remote file was not found"),
            413: _error_response("Subtitle exceeds the eight MiB limit"),
            422: _error_response("Credentials expired or subtitle format unsupported"),
            429: _error_response("Cloud115 rate limit"),
            502: _error_response("Cloud115 protocol failure"),
            503: _error_response("Cloud115 temporarily unavailable"),
        },
    )
    async def download_subtitle(
        playback_session_id: uuid.UUID,
        subtitle_id: uuid.UUID,
        admin: CurrentAdmin = Depends(current_admin_dependency),
    ) -> Response:
        try:
            result = await service.download(
                admin=admin,
                playback_session_id=playback_session_id,
                subtitle_id=subtitle_id,
            )
        except SubtitleProblem as error:
            raise ApiProblem(
                status_code=error.status_code,
                code=error.code,
                message="Subtitle is not available",
                retry_after_seconds=error.retry_after_seconds,
            ) from None
        return Response(
            content=result.content,
            headers={
                "Content-Type": result.media_type,
                "Content-Disposition": f'attachment; filename="{result.filename}"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router


def _error_response(description: str) -> dict[str, object]:
    return {"description": description, "model": ApiError}


__all__ = ["create_subtitle_api"]
