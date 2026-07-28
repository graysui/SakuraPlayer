from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog import models as _catalog_models  # noqa: F401
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.service import AuthService
from sakuraplayer.playback.heartbeat import PlaybackHeartbeatService
from sakuraplayer.playback.progress import MoviePlaybackStateService
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 28, 11, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"task111-bootstrap-token-at-least-32-bytes"


def test_progress_put_accepts_unknown_duration_and_returns_conflict_authority() -> None:
    app, movie_id, client_instance_id = _context()

    with TestClient(app) as client:
        headers = _bootstrap(client, client_instance_id)
        created = client.put(
            f"/api/v1/movies/{movie_id}/progress",
            headers=headers,
            json={
                "position_seconds": 42.125,
                "duration_seconds": None,
                "version": 0,
            },
        )
        conflict = client.put(
            f"/api/v1/movies/{movie_id}/progress",
            headers=headers,
            json={
                "position_seconds": 50,
                "duration_seconds": 1000,
                "version": 0,
            },
        )

    assert created.status_code == 200
    assert created.headers["cache-control"] == "no-store"
    assert created.json() == {
        "position_seconds": 42.125,
        "duration_seconds": None,
        "completed": False,
        "version": 1,
    }
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "progress_version_conflict"
    assert conflict.json()["details"]["progress"] == created.json()


def test_progress_put_rejects_missing_duration_zero_nan_and_unknown_movie() -> None:
    app, movie_id, client_instance_id = _context()

    with TestClient(app) as client:
        headers = _bootstrap(client, client_instance_id)
        missing = client.put(
            f"/api/v1/movies/{movie_id}/progress",
            headers=headers,
            json={"position_seconds": 1, "version": 0},
        )
        zero = client.put(
            f"/api/v1/movies/{movie_id}/progress",
            headers=headers,
            json={"position_seconds": 1, "duration_seconds": 0, "version": 0},
        )
        nan = client.put(
            f"/api/v1/movies/{movie_id}/progress",
            headers=headers,
            json={
                "position_seconds": "NaN",
                "duration_seconds": None,
                "version": 0,
            },
        )
        boolean_number = client.put(
            f"/api/v1/movies/{movie_id}/progress",
            headers=headers,
            json={
                "position_seconds": True,
                "duration_seconds": None,
                "version": False,
            },
        )
        numeric_string = client.put(
            f"/api/v1/movies/{movie_id}/progress",
            headers=headers,
            json={
                "position_seconds": "1",
                "duration_seconds": None,
                "version": "0",
            },
        )
        unknown = client.put(
            f"/api/v1/movies/{uuid.uuid4()}/progress",
            headers=headers,
            json={
                "position_seconds": 1,
                "duration_seconds": None,
                "version": 0,
            },
        )

    for response in (missing, zero, nan, boolean_number, numeric_string):
        assert response.status_code == 422
        assert response.json()["code"] == "validation_failed"
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "resource_not_found"


def test_actual_openapi_exposes_nullable_duration_optional_heartbeat_progress() -> None:
    app, _, _ = _context()

    schema = app.openapi()
    progress_update = schema["components"]["schemas"]["ProgressUpdateInput"]
    heartbeat = schema["components"]["schemas"]["PlaybackHeartbeatInput"]
    progress_output = schema["components"]["schemas"]["PlaybackProgressOutput"]
    heartbeat_path = schema["paths"][
        "/api/v1/playback/sessions/{playback_session_id}/heartbeat"
    ]["put"]

    assert set(progress_update["required"]) == {
        "position_seconds",
        "duration_seconds",
        "version",
    }
    assert {"type": "null"} in progress_update["properties"]["duration_seconds"][
        "anyOf"
    ]
    assert heartbeat["required"] == ["client_instance_id"]
    assert "progress" not in heartbeat["required"]
    assert "duration_seconds" in progress_output["required"]
    assert set(heartbeat_path["responses"]) >= {"200", "409", "422"}


def test_heartbeat_playing_requires_a_json_boolean() -> None:
    app, _, client_instance_id = _context()

    with TestClient(app) as client:
        headers = _bootstrap(client, client_instance_id)
        response = client.put(
            f"/api/v1/playback/sessions/{uuid.uuid4()}/heartbeat",
            headers=headers,
            json={
                "client_instance_id": str(client_instance_id),
                "playing": 1,
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


def _context():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    movie_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(
            Movie(
                id=movie_id,
                normalized_number="TASK-111-API",
                raw_numbers=["TASK-111-API"],
                catalog_state="core_ready",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    progress = MoviePlaybackStateService(factory, now=lambda: NOW)
    heartbeat = PlaybackHeartbeatService(
        factory,
        progress_service=progress,
        now=lambda: NOW,
    )
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        playback_progress_service=progress,
        playback_heartbeat_service=heartbeat,
    )
    return app, movie_id, uuid.uuid4()


def _bootstrap(client: TestClient, client_instance_id: uuid.UUID) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN.decode("ascii")},
        json={
            "username": "admin",
            "password": "correct horse battery staple",
            "client_instance_id": str(client_instance_id),
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
