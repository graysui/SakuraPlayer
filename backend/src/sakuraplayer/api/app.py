from collections.abc import Callable
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sakuraplayer.identity.api import ApiProblem, create_identity_api
from sakuraplayer.identity.service import AuthService


def create_app(
    *,
    readiness_probe: Callable[[], bool],
    identity_service: AuthService | None = None,
) -> FastAPI:
    app = FastAPI(title="SakuraPlayer API", version="1.1.0")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/auth/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiProblem)
    async def api_problem(request: Request, error: ApiProblem) -> JSONResponse:
        return JSONResponse(
            {
                "code": error.code,
                "message": error.message,
                "request_id": request.state.request_id,
            },
            status_code=error.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        fields = [
            ".".join(str(part) for part in item["loc"])
            for item in error.errors()
        ]
        return JSONResponse(
            {
                "code": "validation_failed",
                "message": "Request validation failed",
                "details": {"fields": fields},
                "request_id": request.state.request_id,
            },
            status_code=422,
        )

    @app.get("/health/live", include_in_schema=False)
    def liveness() -> JSONResponse:
        return JSONResponse(
            {"status": "alive"},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/health/ready", include_in_schema=False)
    def readiness() -> JSONResponse:
        ready = readiness_probe()
        return JSONResponse(
            {"status": "ready" if ready else "not_ready"},
            status_code=200 if ready else 503,
            headers={"Cache-Control": "no-store"},
        )

    if identity_service is not None:
        identity_api = create_identity_api(identity_service)
        app.include_router(identity_api.router)
        app.state.current_admin_dependency = identity_api.current_admin_dependency
        app.state.websocket_admin_dependency = (
            identity_api.websocket_admin_dependency
        )
        app.state.access_authenticator = identity_api.access_authenticator

    return app
