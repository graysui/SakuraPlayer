from __future__ import annotations

from fastapi.testclient import TestClient

from sakuraplayer.api.app import create_app


def test_liveness_is_minimal_and_not_cached() -> None:
    with TestClient(create_app(readiness_probe=lambda: True)) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["cache-control"] == "no-store"


def test_readiness_reports_database_and_schema_failure_without_details() -> None:
    with TestClient(create_app(readiness_probe=lambda: False)) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert response.headers["cache-control"] == "no-store"


def test_internal_health_routes_are_excluded_from_openapi() -> None:
    with TestClient(create_app(readiness_probe=lambda: True)) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert "/health/live" not in paths
    assert "/health/ready" not in paths
