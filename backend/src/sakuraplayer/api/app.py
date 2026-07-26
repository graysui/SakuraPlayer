from collections.abc import Callable
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sakuraplayer.catalog.metadata_api import (
    MetadataAdminService,
    create_metadata_api,
)
from sakuraplayer.catalog.api import create_catalog_api
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.discovery.api import create_discovery_api
from sakuraplayer.discovery.favorites import FavoriteService
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.identity.api import ApiProblem, create_identity_api
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.admin_api import (
    create_movie_source_admin_api,
)
from sakuraplayer.resources.movie_source_service import MovieSourceService
from sakuraplayer.resources.identification_api import (
    IdentificationService,
    create_identification_api,
)
from sakuraplayer.shared.redaction import (
    redact_mapping,
    redact_text,
    stable_error_code,
)


def create_app(
    *,
    readiness_probe: Callable[[], bool],
    identity_service: AuthService | None = None,
    identification_service: IdentificationService | None = None,
    movie_source_admin_service: MovieSourceService | None = None,
    metadata_admin_service: MetadataAdminService | None = None,
    catalog_query_service: CatalogQueryService | None = None,
    search_service: SearchService | None = None,
    favorite_service: FavoriteService | None = None,
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
                "code": stable_error_code(error.code),
                "message": redact_text(error.message),
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
                "details": redact_mapping({"fields": fields}),
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

        if identification_service is not None:
            app.include_router(
                create_identification_api(
                    identification_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
        if movie_source_admin_service is not None:
            app.include_router(
                create_movie_source_admin_api(
                    movie_source_admin_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
        if metadata_admin_service is not None:
            app.include_router(
                create_metadata_api(
                    metadata_admin_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
        if catalog_query_service is not None:
            app.include_router(
                create_catalog_api(
                    catalog_query_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
        if search_service is not None and favorite_service is not None:
            app.include_router(
                create_discovery_api(
                    search_service,
                    favorite_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
        elif search_service is not None or favorite_service is not None:
            raise ValueError("discovery API requires search and favorite services")
    elif (
        identification_service is not None
        or movie_source_admin_service is not None
        or metadata_admin_service is not None
        or catalog_query_service is not None
        or search_service is not None
        or favorite_service is not None
    ):
        raise ValueError("admin APIs require identity service")

    return app
