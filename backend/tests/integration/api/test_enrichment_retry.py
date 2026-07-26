from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog.metadata_api import MetadataAdminService
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import MetadataJob, MetadataStage
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.models import Movie


NOW = datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


def test_enrichment_retry_only_queues_explicit_optional_stages() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    queue = MetadataQueue(factory, now=lambda: NOW)
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number="RETRY-013",
        raw_numbers=["RETRY-013"],
        catalog_state="core_ready",
        created_at=NOW,
        updated_at=NOW,
    )
    parent = MetadataJob(
        id=uuid.uuid4(),
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        priority=10,
        reason="manual_or_search",
        sort_date=None,
        retry_mode="full",
        requested_stages=[],
        status="completed_with_warnings",
        attempt_no=1,
        parent_job_id=None,
        claim_owner=None,
        claim_expires_at=None,
        started_at=NOW,
        finished_at=NOW,
        elapsed_ms=100,
        failure_code=None,
        failure_detail=None,
        created_at=NOW,
    )
    with factory.begin() as session:
        session.add_all(
            [
                movie,
                parent,
                MetadataStage(
                    job_id=parent.id,
                    stage="javdb_core",
                    status="succeeded",
                    started_at=NOW,
                    finished_at=NOW,
                    failure_code=None,
                ),
                MetadataStage(
                    job_id=parent.id,
                    stage="images",
                    status="warning",
                    started_at=NOW,
                    finished_at=NOW,
                    failure_code="metadata_provider_unavailable",
                ),
                MetadataStage(
                    job_id=parent.id,
                    stage="translation",
                    status="warning",
                    started_at=NOW,
                    finished_at=NOW,
                    failure_code="translation_not_configured",
                ),
            ]
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
        metadata_admin_service=MetadataAdminService(factory, queue),
    )
    try:
        with TestClient(app) as client:
            headers = _auth_headers(client)
            response = client.post(
                f"/api/v1/admin/metadata-jobs/{parent.id}/retry-enrichment",
                headers=headers,
                json={"stages": ["images"]},
            )
            assert response.status_code == 201
            body = response.json()
            assert body["retry_mode"] == "missing_enrichment"
            assert body["requested_stages"] == ["images"]
            assert body["parent_job_id"] == str(parent.id)
            assert body["attempt_no"] == 2
            stage_statuses = {
                stage["stage"]: stage["status"] for stage in body["stages"]
            }
            assert stage_statuses["images"] == "pending"
            assert stage_statuses["javdb_core"] == "skipped"
            assert stage_statuses["translation"] == "skipped"

            core = client.post(
                f"/api/v1/admin/metadata-jobs/{parent.id}/retry-enrichment",
                headers=headers,
                json={"stages": ["javdb_core"]},
            )
            assert core.status_code == 422
            assert core.json()["code"] == "validation_failed"
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
