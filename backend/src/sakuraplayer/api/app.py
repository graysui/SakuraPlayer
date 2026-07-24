from collections.abc import Callable

from fastapi import FastAPI
from fastapi.responses import JSONResponse


def create_app(*, readiness_probe: Callable[[], bool]) -> FastAPI:
    app = FastAPI(title="SakuraPlayer API", version="1.1.0")

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

    return app
