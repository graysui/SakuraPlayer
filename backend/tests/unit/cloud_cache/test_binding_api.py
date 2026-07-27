from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.api.app import create_app
from sakuraplayer.cloud_cache.binding_service import BindingView
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    QrLoginResult,
    QrSession,
    QrStatus,
    QrToken,
)
from sakuraplayer.cloud_cache.qr_service import QrSessionService
from sakuraplayer.identity.api import ApiProblem
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.service import AuthService
from tests.fakes.cloud115 import FakeCloud115

NOW = datetime(2026, 7, 27, 9, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


class _BindingStub:
    def __init__(self) -> None:
        self.view = BindingView(False, "unbound")

    def get(self) -> BindingView:
        return self.view

    async def bind(self, result: QrLoginResult) -> BindingView:
        assert result.account_key == "account-private"
        assert result.cookie_snapshot == "UID=private-cookie"
        self.view = BindingView(True, "active", cache_root_ready=True)
        return self.view

    def remove(self) -> None:
        self.view = BindingView(False, "unbound")


def test_cloud115_api_is_authenticated_and_secret_safe() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    token = QrToken(uid="upstream-private", time=1, sign="sign-private")
    fake = FakeCloud115(
        qr_sessions=[QrSession(token, b"PNG-public-bytes")],
        qr_statuses=[QrStatus.SCANNED, QrStatus.CONFIRMED],
        qr_results=[QrLoginResult("account-private", "UID=private-cookie")],
    )

    @asynccontextmanager
    async def cloud_factory(_cookies: str | None):
        yield fake

    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    binding = _BindingStub()
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        cloud115_binding_service=binding,  # type: ignore[arg-type]
        cloud115_qr_service=QrSessionService(cloud_factory, now=lambda: NOW),
    )
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/cloud115/binding").status_code == 401
            headers = _auth_headers(client)
            created = client.post("/api/v1/cloud115/qr-sessions", headers=headers)
            assert created.status_code == 201
            assert created.headers["Cache-Control"] == "no-store"
            session_id = created.json()["id"]
            assert created.json()["qrcode_png_base64"] is not None

            polled = client.get(
                f"/api/v1/cloud115/qr-sessions/{session_id}", headers=headers
            )
            assert polled.json()["status"] == "scanned"
            assert polled.json()["qrcode_png_base64"] is None

            confirmed = client.post(
                f"/api/v1/cloud115/qr-sessions/{session_id}/confirm",
                headers=headers,
            )
            assert confirmed.status_code == 200
            assert confirmed.json() == {
                "bound": True,
                "status": "active",
                "display_name": None,
                "cache_root_ready": True,
                "last_verified_at": None,
            }
            repeated = client.post(
                f"/api/v1/cloud115/qr-sessions/{session_id}/confirm",
                headers=headers,
            )
            assert repeated.status_code == 409
            assert repeated.json()["code"] == "cloud115_qr_session_consumed"

            removed = client.delete("/api/v1/cloud115/binding", headers=headers)
            assert removed.status_code == 204

        combined = " \n".join(
            [created.text, polled.text, confirmed.text, repeated.text]
        )
        for secret in (
            "upstream-private",
            "sign-private",
            "account-private",
            "private-cookie",
            "root-private-cid",
        ):
            assert secret not in combined
    finally:
        engine.dispose()


def test_cloud115_rate_limit_preserves_retry_after() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    fake = FakeCloud115(
        qr_sessions=[Cloud115Problem("cloud115_rate_limited", retry_after_seconds=7)]
    )

    @asynccontextmanager
    async def cloud_factory(_cookies: str | None):
        yield fake

    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        cloud115_binding_service=_BindingStub(),  # type: ignore[arg-type]
        cloud115_qr_service=QrSessionService(cloud_factory),
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/cloud115/qr-sessions", headers=_auth_headers(client)
            )
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "7"
        assert response.json()["code"] == "cloud115_rate_limited"
    finally:
        engine.dispose()


@pytest.mark.parametrize("invalid", [-1, 86_401, True, 1.5])
def test_api_problem_rejects_invalid_retry_after(invalid: object) -> None:
    with pytest.raises(ValueError):
        ApiProblem(
            status_code=429,
            code="cloud115_rate_limited",
            message="Cloud115 operation failed",
            retry_after_seconds=invalid,  # type: ignore[arg-type]
        )


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN.decode("ascii")},
        json={
            "username": "admin",
            "password": "correct horse battery staple",
            "client_instance_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
