from __future__ import annotations

import base64
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict

from sakuraplayer.cloud_cache.binding_service import (
    BindingProblem,
    BindingService,
    BindingView,
)
from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem
from sakuraplayer.cloud_cache.qr_service import (
    QrSessionProblem,
    QrSessionService,
    QrSessionView,
)
from sakuraplayer.identity.api import ApiProblem


class Cloud115BindingOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bound: bool
    status: Literal["unbound", "active", "expired", "unavailable", "detached"]
    display_name: str | None = None
    cache_root_ready: bool
    last_verified_at: datetime | None = None


class QrSessionOutput(BaseModel):
    id: uuid.UUID
    status: Literal["waiting", "scanned", "confirmed", "expired", "canceled"]
    expires_at: datetime
    qrcode_png_base64: str | None = None


def create_cloud115_binding_api(
    binding_service: BindingService,
    qr_service: QrSessionService,
    *,
    current_admin_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/cloud115",
        tags=["Cloud115"],
        dependencies=[Depends(current_admin_dependency)],
    )

    @router.get("/binding", response_model=Cloud115BindingOutput)
    def get_binding() -> BindingView:
        return binding_service.get()

    @router.delete(
        "/binding",
        status_code=204,
        responses={409: {"description": "Active cache jobs block unbinding."}},
    )
    def delete_binding() -> Response:
        try:
            binding_service.remove()
        except BindingProblem as error:
            raise _api_problem(error) from None
        return Response(status_code=204)

    @router.post(
        "/qr-sessions",
        response_model=QrSessionOutput,
        status_code=201,
        responses={
            429: {"description": "QR session capacity or upstream rate limit."},
            502: {"description": "Cloud115 protocol error."},
            503: {"description": "Cloud115 is unavailable."},
        },
    )
    async def create_qr_session() -> QrSessionOutput:
        try:
            result = await qr_service.create()
        except (QrSessionProblem, Cloud115Problem) as error:
            raise _api_problem(error) from None
        return _qr_output(result)

    @router.get(
        "/qr-sessions/{qr_session_id}",
        response_model=QrSessionOutput,
        responses={
            404: {"description": "QR session not found."},
            429: {"description": "Cloud115 rate limit."},
            502: {"description": "Cloud115 protocol error."},
            503: {"description": "Cloud115 is unavailable."},
        },
    )
    async def get_qr_session(qr_session_id: uuid.UUID) -> QrSessionOutput:
        try:
            result = await qr_service.poll(qr_session_id)
        except (QrSessionProblem, Cloud115Problem) as error:
            raise _api_problem(error) from None
        return _qr_output(result)

    @router.post(
        "/qr-sessions/{qr_session_id}/confirm",
        response_model=Cloud115BindingOutput,
        responses={
            404: {"description": "QR session not found."},
            409: {"description": "QR or binding conflict."},
            429: {"description": "Cloud115 rate limit."},
            502: {"description": "Cloud115 protocol error."},
            503: {"description": "Cloud115 is unavailable."},
        },
    )
    async def confirm_qr_session(qr_session_id: uuid.UUID) -> BindingView:
        try:
            return await qr_service.confirm(qr_session_id, binding_service.bind)
        except (QrSessionProblem, BindingProblem, Cloud115Problem) as error:
            raise _api_problem(error) from None

    return router


def _qr_output(view: QrSessionView) -> QrSessionOutput:
    image = (
        base64.b64encode(view.image_png).decode("ascii")
        if view.image_png is not None
        else None
    )
    return QrSessionOutput(
        id=view.id,
        status=view.status,
        expires_at=view.expires_at,
        qrcode_png_base64=image,
    )


def _api_problem(
    error: QrSessionProblem | BindingProblem | Cloud115Problem,
) -> ApiProblem:
    statuses = {
        "cloud115_credentials_expired": 422,
        "cloud115_directory_not_found": 404,
        "cloud115_directory_ambiguous": 409,
        "cloud115_rate_limited": 429,
        "cloud115_unavailable": 503,
        "cloud115_protocol_error": 502,
    }
    status_code = getattr(error, "status_code", statuses.get(error.code, 502))
    retry_after = getattr(error, "retry_after_seconds", None)
    return ApiProblem(
        status_code=status_code,
        code=error.code,
        message="Cloud115 operation failed",
        retry_after_seconds=retry_after,
    )


__all__ = [
    "Cloud115BindingOutput",
    "QrSessionOutput",
    "create_cloud115_binding_api",
]
