from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TypeVar

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Request,
    Response,
    WebSocket,
    WebSocketException,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from sakuraplayer.identity.domain import (
    AuthenticationError,
    BootstrapAlreadyCompleted,
    BootstrapTokenInvalid,
    CurrentAdmin,
    IdentityValidationError,
    InvalidCredentials,
    RefreshTokenInvalid,
    RefreshTokenReused,
    SessionRevoked,
    TokenPair,
)
from sakuraplayer.identity.service import AuthService


class ApiProblem(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(code)


class CredentialsInput(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    client_instance_id: uuid.UUID


class RefreshInput(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPairOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    refresh_token: str
    token_type: str
    access_expires_at: datetime
    refresh_expires_at: datetime


class BootstrapStatusOutput(BaseModel):
    initialized: bool
    api_version: int = 1


IdentityException = (
    AuthenticationError,
    BootstrapAlreadyCompleted,
    BootstrapTokenInvalid,
    IdentityValidationError,
    InvalidCredentials,
    RefreshTokenInvalid,
    RefreshTokenReused,
    SessionRevoked,
)
_ERRORS: dict[type[RuntimeError], tuple[int, str]] = {
    AuthenticationError: (401, "Authentication is required"),
    BootstrapAlreadyCompleted: (409, "Bootstrap is already completed"),
    BootstrapTokenInvalid: (401, "Bootstrap token is invalid"),
    IdentityValidationError: (422, "Request validation failed"),
    InvalidCredentials: (401, "Credentials are invalid"),
    RefreshTokenInvalid: (401, "Refresh token is invalid"),
    RefreshTokenReused: (401, "Refresh token was already used"),
    SessionRevoked: (401, "Session is revoked"),
}
T = TypeVar("T")


def _invoke(call: Callable[[], T]) -> T:
    try:
        return call()
    except IdentityException as error:
        status_code, message = _ERRORS[type(error)]
        raise ApiProblem(
            status_code=status_code,
            code=error.code,
            message=message,
        ) from None


@dataclass(frozen=True)
class IdentityApi:
    router: APIRouter
    current_admin_dependency: Callable[..., CurrentAdmin]
    websocket_admin_dependency: Callable[..., CurrentAdmin]
    access_authenticator: Callable[[str], CurrentAdmin]


def create_identity_api(service: AuthService) -> IdentityApi:
    router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])
    bearer = HTTPBearer(auto_error=False)

    def bearer_token(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> str:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise ApiProblem(
                status_code=401,
                code="authentication_required",
                message="Authentication is required",
            )
        return credentials.credentials

    def current_admin(token: str = Depends(bearer_token)) -> CurrentAdmin:
        return _invoke(lambda: service.authenticate_access(token))

    def websocket_admin(websocket: WebSocket) -> CurrentAdmin:
        scheme, separator, token = websocket.headers.get("authorization", "").partition(
            " "
        )
        if separator != " " or scheme.lower() != "bearer" or not token:
            raise WebSocketException(code=4401)
        try:
            return service.authenticate_access(token)
        except SessionRevoked:
            raise WebSocketException(code=4403) from None
        except AuthenticationError:
            raise WebSocketException(code=4401) from None

    @router.get("/bootstrap-status", response_model=BootstrapStatusOutput)
    def bootstrap_status() -> BootstrapStatusOutput:
        return BootstrapStatusOutput(initialized=service.is_initialized())

    @router.post(
        "/bootstrap",
        response_model=TokenPairOutput,
        status_code=201,
        openapi_extra={
            "requestBody": {
                "required": False,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/CredentialsInput"}
                    }
                },
            }
        },
    )
    async def bootstrap(
        request: Request,
        bootstrap_token: str | None = Header(
            default=None,
            alias="X-Bootstrap-Token",
        ),
    ) -> TokenPair:
        await run_in_threadpool(
            _invoke,
            lambda: service.authorize_bootstrap_token(bootstrap_token),
        )
        try:
            body = CredentialsInput.model_validate_json(await request.body())
        except ValidationError:
            raise ApiProblem(
                status_code=422,
                code="validation_failed",
                message="Request validation failed",
            ) from None
        return await run_in_threadpool(
            _invoke,
            lambda: service.bootstrap(
                username=body.username,
                password=body.password,
                client_instance_id=body.client_instance_id,
                provided_bootstrap_token=bootstrap_token,
            ),
        )

    @router.post("/login", response_model=TokenPairOutput)
    def login(body: CredentialsInput) -> TokenPair:
        return _invoke(
            lambda: service.login(
                username=body.username,
                password=body.password,
                client_instance_id=body.client_instance_id,
            )
        )

    @router.post("/refresh", response_model=TokenPairOutput)
    def refresh(body: RefreshInput) -> TokenPair:
        return _invoke(lambda: service.refresh(body.refresh_token))

    @router.post("/logout", status_code=204)
    def logout(token: str = Depends(bearer_token)) -> Response:
        _invoke(lambda: service.logout(token))
        return Response(status_code=204)

    return IdentityApi(
        router=router,
        current_admin_dependency=current_admin,
        websocket_admin_dependency=websocket_admin,
        access_authenticator=service.authenticate_access,
    )
