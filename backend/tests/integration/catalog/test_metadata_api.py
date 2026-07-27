from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog.metadata_api import MetadataAdminService
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import MetadataJob
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.models import Movie
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 25, 11, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task007_api_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()
    test_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        upgrade_database(test_url, ALEMBIC_INI)
        yield test_url
    finally:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin_engine.dispose()


@pytest.fixture
def api_context(database_url: str):
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    queue = MetadataQueue(factory, now=lambda: NOW)
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
    app.add_event_handler("shutdown", engine.dispose)
    with TestClient(app) as client:
        yield client, queue, factory


def add_movie(factory: sessionmaker, number: str) -> Movie:
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add(movie)
    return movie


def auth_headers(client: TestClient) -> dict[str, str]:
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


def create_failed_job(queue: MetadataQueue, factory: sessionmaker) -> uuid.UUID:
    movie = add_movie(factory, "ABP-101")
    outcome = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 24),
        reason="initial",
    )
    claim = queue.claim_next("worker-api", lease_duration=timedelta(seconds=30))
    assert claim is not None
    queue.fail(claim, code="javdb_upstream_error", detail="safe_fixture")
    return outcome.job_id


def create_warning_job(queue: MetadataQueue, factory: sessionmaker) -> uuid.UUID:
    movie = add_movie(factory, "ABP-102")
    outcome = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 23),
        reason="daily",
    )
    claim = queue.claim_next("worker-api", lease_duration=timedelta(seconds=30))
    assert claim is not None
    queue.start_stage(claim, "javdb_core")
    with factory.begin() as session:
        persisted = session.get(Movie, movie.id, with_for_update=True)
        assert persisted is not None
        persisted.catalog_state = "core_ready"
    queue.finish_stage(claim, "javdb_core", status="succeeded")
    for stage in ("images", "dmm", "actor_map", "gfriends", "translation"):
        queue.start_stage(claim, stage)
        queue.finish_stage(
            claim,
            stage,
            status="warning" if stage == "images" else "succeeded",
            failure_code="image_download_failed" if stage == "images" else None,
        )
    queue.complete(claim, with_warnings=True)
    return outcome.job_id


def test_metadata_admin_list_is_authenticated_paginated_and_redacted(
    api_context,
) -> None:
    client, queue, factory = api_context
    failed_id = create_failed_job(queue, factory)
    warning_id = create_warning_job(queue, factory)

    anonymous = client.get("/api/v1/admin/metadata-jobs")
    headers = auth_headers(client)
    first = client.get(
        "/api/v1/admin/metadata-jobs",
        params={"limit": 1},
        headers=headers,
    )
    second = client.get(
        "/api/v1/admin/metadata-jobs",
        params={"limit": 1, "cursor": first.json()["next_cursor"]},
        headers=headers,
    )
    failed = client.get(
        "/api/v1/admin/metadata-jobs",
        params={"status": "failed"},
        headers=headers,
    )

    assert anonymous.status_code == 401
    assert first.status_code == second.status_code == failed.status_code == 200
    assert first.json()["next_cursor"]
    assert {first.json()["items"][0]["id"], second.json()["items"][0]["id"]} == {
        str(failed_id),
        str(warning_id),
    }
    item = failed.json()["items"][0]
    assert item["error_code"] == "javdb_upstream_error"
    assert len(item["stages"]) == 6
    assert item["retryable_stages"] == []
    assert "safe_fixture" not in failed.text
    assert "claim_owner" not in failed.text


def test_admin_retry_endpoints_create_new_attempts_and_keep_parent_immutable(
    api_context,
) -> None:
    client, queue, factory = api_context
    failed_id = create_failed_job(queue, factory)
    warning_id = create_warning_job(queue, factory)
    headers = auth_headers(client)

    full = client.post(
        f"/api/v1/admin/metadata-jobs/{failed_id}/retry",
        headers=headers,
    )
    repeated = client.post(
        f"/api/v1/admin/metadata-jobs/{failed_id}/retry",
        headers=headers,
    )
    enrichment = client.post(
        f"/api/v1/admin/metadata-jobs/{warning_id}/retry-enrichment",
        json={"stages": ["images"]},
        headers=headers,
    )
    paid_ai_not_missing = client.post(
        f"/api/v1/admin/metadata-jobs/{warning_id}/retry-enrichment",
        json={"stages": ["translation"]},
        headers=headers,
    )
    core_forbidden = client.post(
        f"/api/v1/admin/metadata-jobs/{warning_id}/retry-enrichment",
        json={"stages": ["javdb_core"]},
        headers=headers,
    )
    duplicate_stages = client.post(
        f"/api/v1/admin/metadata-jobs/{warning_id}/retry-enrichment",
        json={"stages": ["images", "images"]},
        headers=headers,
    )

    assert full.status_code == 201
    assert full.json()["parent_job_id"] == str(failed_id)
    assert full.json()["attempt_no"] == 2
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "metadata_job_already_active"
    assert enrichment.status_code == 201
    assert enrichment.json()["retry_mode"] == "missing_enrichment"
    assert enrichment.json()["requested_stages"] == ["images"]
    warning_snapshot = client.get(
        "/api/v1/admin/metadata-jobs",
        params={"status": "completed_with_warnings"},
        headers=headers,
    ).json()["items"][0]
    assert warning_snapshot["retryable_stages"] == ["images"]
    assert {
        stage["stage"]: (stage["status"], stage["error_code"])
        for stage in warning_snapshot["stages"]
    }["images"] == ("warning", "image_download_failed")
    assert paid_ai_not_missing.status_code == 409
    assert paid_ai_not_missing.json()["code"] == "metadata_job_no_retryable_enrichment"
    assert core_forbidden.status_code == 422
    assert core_forbidden.json()["code"] == "validation_failed"
    assert duplicate_stages.status_code == 422
    assert duplicate_stages.json()["code"] == "validation_failed"
    with factory() as session:
        parents = list(
            session.scalars(
                select(MetadataJob).where(MetadataJob.id.in_((failed_id, warning_id)))
            )
        )
    assert {job.status for job in parents} == {"failed", "completed_with_warnings"}
