import uuid
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sakuraplayer.api.diagnostics import DiagnosticsService, create_diagnostics_api
from sakuraplayer.api.settings import SettingsService, create_settings_api
from sakuraplayer.catalog.api import create_catalog_api
from sakuraplayer.catalog.metadata_api import (
    MetadataAdminService,
    create_metadata_api,
)
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.cloud_cache.binding_api import create_cloud115_binding_api
from sakuraplayer.cloud_cache.binding_service import BindingService
from sakuraplayer.cloud_cache.cache_api import create_cache_api
from sakuraplayer.cloud_cache.play_request import PlayRequestService
from sakuraplayer.cloud_cache.qr_service import QrSessionService
from sakuraplayer.discovery.api import create_discovery_api
from sakuraplayer.discovery.favorites import FavoriteService
from sakuraplayer.discovery.ranking_api import create_ranking_api
from sakuraplayer.discovery.ranking_query import RankingQueryService
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.events.outbox import EventLog
from sakuraplayer.events.snapshot import EventSnapshotService
from sakuraplayer.events.websocket import create_events_api
from sakuraplayer.identity.api import ApiProblem, create_identity_api
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.admin_api import (
    create_movie_source_admin_api,
)
from sakuraplayer.resources.identification_api import (
    IdentificationService,
    create_identification_api,
)
from sakuraplayer.resources.movie_source_service import MovieSourceService
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
    ranking_query_service: RankingQueryService | None = None,
    event_snapshot_service: EventSnapshotService | None = None,
    event_log: EventLog | None = None,
    settings_service: SettingsService | None = None,
    diagnostics_service: DiagnosticsService | None = None,
    cloud115_binding_service: BindingService | None = None,
    cloud115_qr_service: QrSessionService | None = None,
    cache_service: PlayRequestService | None = None,
) -> FastAPI:
    app = FastAPI(title="SakuraPlayer API", version="1.1.0")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        if (
            request.url.path.startswith("/api/v1/auth/")
            or request.url.path.startswith("/api/v1/settings")
            or request.url.path.startswith("/api/v1/admin/")
            or request.url.path.startswith("/api/v1/events/")
            or request.url.path.startswith("/api/v1/cloud115/")
            or request.url.path.startswith("/api/v1/cache-jobs")
            or request.url.path.endswith("/play-requests")
            or request.url.path == "/api/v1/rankings"
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiProblem)
    async def api_problem(request: Request, error: ApiProblem) -> JSONResponse:
        payload: dict[str, object] = {
            "code": stable_error_code(error.code),
            "message": redact_text(error.message),
            "request_id": request.state.request_id,
        }
        if error.details is not None:
            payload["details"] = redact_mapping(error.details)
        return JSONResponse(
            payload,
            status_code=error.status_code,
            headers=(
                {"Retry-After": str(error.retry_after_seconds)}
                if error.retry_after_seconds is not None
                else None
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        fields = [
            ".".join(str(part) for part in item["loc"]) for item in error.errors()
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
        app.state.websocket_admin_dependency = identity_api.websocket_admin_dependency
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
        if ranking_query_service is not None:
            app.include_router(
                create_ranking_api(
                    ranking_query_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
        if event_snapshot_service is not None and event_log is not None:
            app.include_router(
                create_events_api(
                    event_snapshot_service,
                    event_log,
                    current_admin_dependency=identity_api.current_admin_dependency,
                    websocket_admin_dependency=identity_api.websocket_admin_dependency,
                )
            )
        elif event_snapshot_service is not None or event_log is not None:
            raise ValueError("events API requires snapshot service and event log")
        if settings_service is not None:
            app.include_router(
                create_settings_api(
                    settings_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
        if diagnostics_service is not None:
            app.include_router(
                create_diagnostics_api(
                    diagnostics_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
        if cloud115_binding_service is not None and cloud115_qr_service is not None:
            app.include_router(
                create_cloud115_binding_api(
                    cloud115_binding_service,
                    cloud115_qr_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
        elif cloud115_binding_service is not None or cloud115_qr_service is not None:
            raise ValueError("Cloud115 API requires binding and QR services")
        if cache_service is not None:
            app.include_router(
                create_cache_api(
                    cache_service,
                    current_admin_dependency=identity_api.current_admin_dependency,
                )
            )
    elif (
        identification_service is not None
        or movie_source_admin_service is not None
        or metadata_admin_service is not None
        or catalog_query_service is not None
        or search_service is not None
        or favorite_service is not None
        or ranking_query_service is not None
        or event_snapshot_service is not None
        or event_log is not None
        or settings_service is not None
        or diagnostics_service is not None
        or cloud115_binding_service is not None
        or cloud115_qr_service is not None
        or cache_service is not None
    ):
        raise ValueError("admin APIs require identity service")

    return app
