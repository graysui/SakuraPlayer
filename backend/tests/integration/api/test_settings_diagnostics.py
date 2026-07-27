from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.api.app import create_app
from sakuraplayer.api.diagnostics import DiagnosticsService
from sakuraplayer.api.settings import ProbeResult, SettingsService
from sakuraplayer.catalog.models import MetadataJob, MetadataStage
from sakuraplayer.catalog.providers.javdb import EncryptedJavdbCredentialStore
from sakuraplayer.catalog.translation.config import EncryptedAiConfigurationStore
from sakuraplayer.identity.crypto import (
    SecretCipher,
    SettingsSecretKeyProvider,
)
from sakuraplayer.identity.models import Base, EncryptedSetting
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


def test_settings_cas_connection_tests_and_diagnostics_are_secret_safe() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = EncryptedSettingRepository(
        factory,
        SecretCipher(SettingsSecretKeyProvider(key_id="v1", key=b"s" * 32)),
        now=lambda: NOW,
    )
    settings = SettingsService(
        factory,
        repository,
        EncryptedJavdbCredentialStore(repository),
        EncryptedAiConfigurationStore(repository),
        probes={
            "javdb": lambda: ProbeResult("available"),
            "ai": lambda: ProbeResult("available"),
            "dmm": lambda: ProbeResult("available"),
            "gfriends": _timeout_probe,
        },
        now=lambda: NOW,
        monotonic_clock=lambda: 1.0,
    )
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        settings_service=settings,
        diagnostics_service=DiagnosticsService(
            factory,
            settings,
            now=lambda: NOW,
        ),
    )
    javdb_password = "private-javdb-password"
    ai_key = "private-ai-key"
    try:
        with TestClient(app) as client:
            headers = _auth_headers(client)
            assert client.get("/api/v1/settings").status_code == 401
            defaults = client.get("/api/v1/settings", headers=headers).json()
            assert defaults["cache_ttl_hours"] == 24
            assert defaults["javdb"]["version"] == 0
            assert defaults["ai"]["version"] == 0
            assert defaults["providers"]["cloud115"]["configured"] is False

            response = client.patch(
                "/api/v1/settings",
                headers=headers,
                json={
                    "cache_ttl_hours": 48,
                    "javdb": {
                        "action": "replace",
                        "expected_version": 0,
                        "username": "fixture-user",
                        "password": javdb_password,
                    },
                    "ai": {
                        "action": "replace",
                        "expected_version": 0,
                        "base_url": "https://ai.example.test/root",
                        "api_key": ai_key,
                        "model": "fixture-model",
                        "timeout_seconds": 45,
                    },
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["cache_ttl_hours"] == 48
            assert body["javdb"] == {
                "configured": True,
                "status": "unknown",
                "last_checked_at": None,
                "last_error_code": None,
                "username": "fixture-user",
                "password_configured": True,
                "version": 1,
            }
            assert body["ai"]["api_key_configured"] is True
            assert javdb_password not in response.text
            assert ai_key not in response.text

            stale = client.patch(
                "/api/v1/settings",
                headers=headers,
                json={
                    "javdb": {
                        "action": "replace",
                        "expected_version": 0,
                        "username": "stale-user",
                        "password": "stale-password",
                    }
                },
            )
            assert stale.status_code == 409
            assert stale.json()["code"] == "state_conflict"

            tested = client.post(
                "/api/v1/settings/connection-tests",
                headers=headers,
                json={"target": "javdb"},
            )
            assert tested.status_code == 200
            assert tested.json()["status"] == "available"
            cloud115 = client.post(
                "/api/v1/settings/connection-tests",
                headers=headers,
                json={"target": "cloud115"},
            )
            assert cloud115.json()["status"] == "not_configured"
            timed_out = client.post(
                "/api/v1/settings/connection-tests",
                headers=headers,
                json={"target": "gfriends"},
            )
            assert timed_out.json()["status"] == "unavailable"
            assert timed_out.json()["error_code"] == "service_unavailable"

            failed_movie = Movie(
                id=uuid.uuid4(),
                normalized_number="DIAG-013",
                raw_numbers=["DIAG-013"],
                catalog_state="raw_only",
                created_at=NOW,
                updated_at=NOW,
            )
            failed_job = MetadataJob(
                id=uuid.uuid4(),
                movie_id=failed_movie.id,
                normalized_number=failed_movie.normalized_number,
                priority=10,
                reason="manual_or_search",
                sort_date=None,
                retry_mode="full",
                requested_stages=[],
                status="failed",
                attempt_no=2,
                parent_job_id=None,
                claim_owner=None,
                claim_expires_at=None,
                started_at=NOW,
                finished_at=NOW,
                elapsed_ms=600_000,
                failure_code="metadata_timeout",
                failure_detail="safe timeout",
                created_at=NOW,
            )
            with factory.begin() as session:
                session.add_all(
                    [
                        failed_movie,
                        failed_job,
                        MetadataStage(
                            job_id=failed_job.id,
                            stage="javdb_core",
                            status="failed",
                            started_at=NOW,
                            finished_at=NOW,
                            failure_code="metadata_timeout",
                        ),
                    ]
                )

            diagnostics = client.get("/api/v1/admin/diagnostics", headers=headers)
            assert diagnostics.status_code == 200
            assert diagnostics.headers["Cache-Control"] == "no-store"
            components = {
                item["component"]: item for item in diagnostics.json()["components"]
            }
            assert components["api"]["status"] == "healthy"
            assert components["postgres"]["status"] == "healthy"
            assert components["worker"]["status"] == "unknown"
            assert components["scheduler"]["status"] == "unknown"
            assert components["avdb"]["status"] == "unknown"
            assert "actor_mapping" not in components
            assert len(diagnostics.json()["connection_tests"]) == 3
            assert diagnostics.json()["recent_failures"] == [
                {
                    "task_type": "metadata",
                    "task_id": str(failed_job.id),
                    "stage": "javdb_core",
                    "error_code": "metadata_timeout",
                    "elapsed_ms": 600_000,
                    "attempt_no": 2,
                    "occurred_at": NOW.isoformat().replace("+00:00", "Z"),
                }
            ]

            cleared = client.patch(
                "/api/v1/settings",
                headers=headers,
                json={"javdb": {"action": "clear", "expected_version": 1}},
            )
            assert cleared.status_code == 200
            assert cleared.json()["javdb"]["configured"] is False
            assert cleared.json()["javdb"]["status"] == "unknown"
            assert cleared.json()["javdb"]["version"] == 2

            replaced_again = client.patch(
                "/api/v1/settings",
                headers=headers,
                json={
                    "javdb": {
                        "action": "replace",
                        "expected_version": 2,
                        "username": "replacement-user",
                        "password": "replacement-password",
                    }
                },
            )
            assert replaced_again.status_code == 200
            assert replaced_again.json()["javdb"]["version"] == 3

            stale_clear = client.patch(
                "/api/v1/settings",
                headers=headers,
                json={"javdb": {"action": "clear", "expected_version": 1}},
            )
            assert stale_clear.status_code == 409
            assert stale_clear.json()["code"] == "state_conflict"

            forbidden = client.patch(
                "/api/v1/settings",
                headers=headers,
                json={"settings_key": "forbidden"},
            )
            assert forbidden.status_code == 422

            settings_response = client.get("/api/v1/settings", headers=headers)
            assert settings_response.headers["Cache-Control"] == "no-store"

        with factory() as session:
            encrypted = list(session.scalars(select(EncryptedSetting)))
        ciphertext = b"".join(row.ciphertext or b"" for row in encrypted)
        assert javdb_password.encode() not in ciphertext
        assert ai_key.encode() not in ciphertext
    finally:
        engine.dispose()


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


def _timeout_probe() -> ProbeResult:
    raise TimeoutError
