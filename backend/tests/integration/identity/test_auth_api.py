from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import Depends, WebSocket
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from sakuraplayer.api.app import create_app
from sakuraplayer.identity.domain import CurrentAdmin
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.service import AuthService


BOOTSTRAP_TOKEN = "bootstrap-token-with-at-least-32-bytes"
PASSWORD = "correct horse battery staple"


@pytest.fixture
def client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False, class_=Session)
    now = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)
    service = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN.encode("ascii"),
        now=lambda: now,
    )
    app = create_app(readiness_probe=lambda: True, identity_service=service)

    @app.get("/api/v1/protected-probe")
    def protected_probe(
        admin: CurrentAdmin = Depends(app.state.current_admin_dependency),
    ) -> dict[str, str]:
        return {"username": admin.username}

    @app.get("/api/v1/playback-signing-probe")
    def playback_signing_probe(
        admin: CurrentAdmin = Depends(app.state.current_admin_dependency),
    ) -> dict[str, str]:
        return {"admin_id": str(admin.admin_id)}

    @app.websocket("/api/v1/websocket-protected-probe")
    async def websocket_protected_probe(
        websocket: WebSocket,
        admin: CurrentAdmin = Depends(app.state.websocket_admin_dependency),
    ) -> None:
        await websocket.accept()
        await websocket.send_json({"username": admin.username})
        await websocket.close()

    return TestClient(app)


def credentials(client_instance_id: uuid.UUID | None = None) -> dict[str, str]:
    return {
        "username": "admin",
        "password": PASSWORD,
        "client_instance_id": str(client_instance_id or uuid.uuid4()),
    }


def bootstrap(client: TestClient, client_instance_id: uuid.UUID | None = None) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
        json=credentials(client_instance_id),
    )
    assert response.status_code == 201
    return response.json()


def test_bootstrap_status_and_auth_responses_are_not_cached(client: TestClient) -> None:
    status = client.get("/api/v1/auth/bootstrap-status")

    assert status.status_code == 200
    assert status.json() == {"initialized": False, "api_version": 1}
    assert status.headers["cache-control"] == "no-store"

    created = client.post(
        "/api/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
        json=credentials(),
    )

    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    assert created.json()["token_type"] == "Bearer"
    assert created.json()["refresh_expires_at"]
    assert client.get("/api/v1/auth/bootstrap-status").json()["initialized"] is True


def test_bootstrap_missing_token_is_safe_and_initialized_empty_request_is_conflict(
    client: TestClient,
) -> None:
    missing = client.post("/api/v1/auth/bootstrap", json=credentials())

    assert missing.status_code == 401
    assert missing.json()["code"] == "bootstrap_token_invalid"
    assert missing.headers["cache-control"] == "no-store"
    assert BOOTSTRAP_TOKEN not in missing.text

    bootstrap(client)
    repeated = client.post("/api/v1/auth/bootstrap")

    assert repeated.status_code == 409
    assert repeated.json()["code"] == "bootstrap_already_completed"
    assert repeated.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "malformed_body",
    [
        {"username": "admin", "password": "short", "client_instance_id": "bad"},
        {"username": "admin"},
        ["not", "an", "object"],
        "not-an-object",
    ],
)
def test_initialized_bootstrap_rejects_malformed_body_as_completed_before_parsing(
    client: TestClient,
    malformed_body: object,
) -> None:
    bootstrap(client)

    repeated = client.post(
        "/api/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": "wrong-token-that-must-not-be-read"},
        json=malformed_body,
    )

    assert repeated.status_code == 409
    assert repeated.json()["code"] == "bootstrap_already_completed"
    assert "wrong-token-that-must-not-be-read" not in repeated.text


def test_uninitialized_bootstrap_checks_token_before_parsing_body(
    client: TestClient,
) -> None:
    malformed = {"username": "admin", "password": "short"}

    missing_token = client.post("/api/v1/auth/bootstrap", json=malformed)
    valid_token = client.post(
        "/api/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
        json=malformed,
    )

    assert missing_token.status_code == 401
    assert missing_token.json()["code"] == "bootstrap_token_invalid"
    assert valid_token.status_code == 422
    assert valid_token.json()["code"] == "validation_failed"
    assert missing_token.headers["cache-control"] == "no-store"
    assert valid_token.headers["cache-control"] == "no-store"
    assert "short" not in valid_token.text


def test_login_validation_and_credentials_errors_never_echo_secrets(
    client: TestClient,
) -> None:
    bootstrap(client)
    wrong_password = "wrong-password-value"

    successful = client.post("/api/v1/auth/login", json=credentials())
    wrong = client.post(
        "/api/v1/auth/login",
        json={**credentials(), "password": wrong_password},
    )
    invalid = client.post(
        "/api/v1/auth/login",
        json={**credentials(), "password": "short"},
    )

    assert successful.status_code == 200
    assert successful.headers["cache-control"] == "no-store"
    assert wrong.status_code == 401
    assert wrong.json()["code"] == "invalid_credentials"
    assert wrong.headers["cache-control"] == "no-store"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "validation_failed"
    assert invalid.headers["cache-control"] == "no-store"
    assert wrong_password not in wrong.text
    assert "short" not in invalid.text


def test_bearer_dependency_refresh_and_logout_enforce_session_state(
    client: TestClient,
) -> None:
    pair = bootstrap(client)

    anonymous = client.get("/api/v1/protected-probe")
    authorized = client.get(
        "/api/v1/protected-probe",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
    )
    rotated = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": pair["refresh_token"]},
    )
    malformed_refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": ""},
    )
    anonymous_logout = client.post("/api/v1/auth/logout")

    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == "authentication_required"
    assert authorized.status_code == 200
    assert authorized.json() == {"username": "admin"}
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != pair["refresh_token"]
    assert rotated.headers["cache-control"] == "no-store"
    assert malformed_refresh.status_code == 422
    assert malformed_refresh.headers["cache-control"] == "no-store"
    assert anonymous_logout.status_code == 401
    assert anonymous_logout.headers["cache-control"] == "no-store"

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {rotated.json()['access_token']}"},
    )
    old_access = client.get(
        "/api/v1/protected-probe",
        headers={"Authorization": f"Bearer {rotated.json()['access_token']}"},
    )
    old_refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated.json()["refresh_token"]},
    )

    assert logout.status_code == 204
    assert logout.headers["cache-control"] == "no-store"
    assert old_access.status_code == 401
    assert old_access.json()["code"] == "session_revoked"
    assert old_refresh.status_code == 401
    assert old_refresh.json()["code"] == "refresh_token_invalid"
    assert old_refresh.headers["cache-control"] == "no-store"


def test_websocket_and_playback_signing_probes_share_current_admin_boundary(
    client: TestClient,
) -> None:
    pair = bootstrap(client)

    anonymous_playback = client.get("/api/v1/playback-signing-probe")
    authorized_playback = client.get(
        "/api/v1/playback-signing-probe",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
    )

    assert anonymous_playback.status_code == 401
    assert authorized_playback.status_code == 200
    with pytest.raises(WebSocketDisconnect) as missing:
        with client.websocket_connect("/api/v1/websocket-protected-probe"):
            pass
    assert missing.value.code == 4401

    with client.websocket_connect(
        "/api/v1/websocket-protected-probe",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
    ) as websocket:
        assert websocket.receive_json() == {"username": "admin"}

    client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
    )
    with pytest.raises(WebSocketDisconnect) as revoked:
        with client.websocket_connect(
            "/api/v1/websocket-protected-probe",
            headers={"Authorization": f"Bearer {pair['access_token']}"},
        ):
            pass
    assert revoked.value.code == 4403
