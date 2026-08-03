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
from sakuraplayer.catalog.translation.adapter import TranslationAdapterError
from sakuraplayer.catalog.translation.config import EncryptedAiConfigurationStore
from sakuraplayer.cloud_cache.models import CacheJob, Cloud115Binding
from sakuraplayer.identity.crypto import (
    SecretCipher,
    SettingsSecretKeyProvider,
)
from sakuraplayer.identity.models import Base, EncryptedSetting
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.avdb_release import EncryptedAvdbSourceStore
from sakuraplayer.resources.models import AvdbSyncRun, Movie

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
        EncryptedAvdbSourceStore(repository),
        probes={
            "javdb": lambda: ProbeResult("available"),
            "ai": _translation_credentials_probe,
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
            assert defaults["mgdb"] == {
                "configured": False,
                "source_url": None,
                "version": 0,
            }
            assert defaults["providers"]["cloud115"]["configured"] is False
            assert defaults["avdb_sync"]["full_reconcile"]["imported_count"] == 0

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
                    "mgdb": {
                        "action": "replace",
                        "expected_version": 0,
                        "source_url": "https://github.com/example/mgdb",
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
            assert body["mgdb"] == {
                "configured": True,
                "source_url": "https://github.com/example/mgdb",
                "version": 1,
            }
            assert javdb_password not in response.text
            assert ai_key not in response.text

            invalid_source = client.patch(
                "/api/v1/settings",
                headers=headers,
                json={
                    "mgdb": {
                        "action": "replace",
                        "expected_version": 1,
                        "source_url": "https://example.invalid/mgdb",
                    }
                },
            )
            assert invalid_source.status_code == 422

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
            ai_test = client.post(
                "/api/v1/settings/connection-tests",
                headers=headers,
                json={"target": "ai"},
            )
            assert ai_test.json()["status"] == "credentials_invalid"
            assert ai_test.json()["error_code"] == ("translation_credentials_invalid")

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
                        AvdbSyncRun(
                            id=uuid.uuid4(),
                            mode="full_reconcile",
                            repository="fixture/repository",
                            release_id="fixture-release",
                            status="completed",
                            cursor={},
                            started_at=NOW,
                            completed_at=NOW,
                            failure_code=None,
                            failure_detail=None,
                            stats={
                                "inserted": 120,
                                "updated": 7,
                                "skipped": 3,
                                "pending": 4,
                            },
                            claim_token=None,
                            claim_expires_at=None,
                            attempt_count=1,
                        ),
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
                        CacheJob(
                            id=uuid.uuid4(),
                            movie_id=uuid.uuid4(),
                            source_id=uuid.uuid4(),
                            binding_id=None,
                            status="failed",
                            capacity_class="released",
                            account_key="diagnostics-account",
                            cache_root_cid="diagnostics-root",
                            task_dir_cid=None,
                            task_dir_name="diagnostics-task",
                            remote_percent=0,
                            failure_code="cloud115_offline_failed",
                            failure_stage="offlining",
                            created_at=NOW,
                            updated_at=NOW,
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
            assert components["avdb"]["status"] == "healthy"
            assert "actor_mapping" not in components
            assert len(diagnostics.json()["connection_tests"]) == 4
            assert diagnostics.json()["queues"] == {
                "metadata_queued": 0,
                "metadata_running": 0,
                "metadata_paused": False,
                "cache_queued": 0,
                "cache_running": 0,
                "cache_ready": 0,
            }
            assert diagnostics.json()["metadata_progress"] == {
                "total": 1,
                "queued": 0,
                "running": 0,
                "completed": 0,
                "failed": 1,
                "finished": 1,
                "current_numbers": [],
            }
            sync = client.get("/api/v1/settings", headers=headers).json()["avdb_sync"]
            assert sync["full_reconcile"]["imported_count"] == 127
            recent_failures = diagnostics.json()["recent_failures"]
            assert {item["task_type"] for item in recent_failures} == {
                "metadata",
                "cache",
            }
            assert {item["task_type"]: item for item in recent_failures}[
                "metadata"
            ] == {
                "task_type": "metadata",
                "task_id": str(failed_job.id),
                "stage": "javdb_core",
                "error_code": "metadata_timeout",
                "elapsed_ms": 600_000,
                "attempt_no": 2,
                "occurred_at": NOW.isoformat().replace("+00:00", "Z"),
            }
            cache_failure = {item["task_type"]: item for item in recent_failures}[
                "cache"
            ]
            assert cache_failure["stage"] == "offlining"
            assert cache_failure["error_code"] == "cloud115_offline_failed"
            assert cache_failure["elapsed_ms"] == 0
            assert cache_failure["attempt_no"] == 1

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

            credential = repository.create_secret(
                "cloud115.cookie", b"UID=detached-cookie"
            )
            with factory.begin() as session:
                session.add(
                    Cloud115Binding(
                        id=uuid.uuid4(),
                        singleton_key=True,
                        account_key="detached-account",
                        display_name=None,
                        cookie_setting_key="cloud115.cookie",
                        login_app="alipaymini",
                        cache_root_cid="moved-root",
                        status="detached",
                        credential_version=credential.version,
                        last_verified_at=NOW,
                        created_at=NOW,
                        updated_at=NOW,
                    )
                )
            detached = client.get("/api/v1/settings", headers=headers)
            assert detached.json()["providers"]["cloud115"] == {
                "configured": True,
                "status": "unavailable",
                "last_checked_at": NOW.isoformat().replace("+00:00", "Z"),
                "last_error_code": "cache_ownership_mismatch",
            }

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


def _translation_credentials_probe() -> ProbeResult:
    raise TranslationAdapterError("translation_credentials_invalid")
