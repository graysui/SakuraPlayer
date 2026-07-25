from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.identification_api import IdentificationService
from sakuraplayer.resources.models import Movie, ResourceSource
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.shared.migration import upgrade_database


pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task005_api_{uuid.uuid4().hex}"
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
def api_context(database_url: str) -> tuple[TestClient, sessionmaker]:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"k" * 32},
        )
    )
    importer = SourceImporter(factory, cipher=cipher, now=lambda: NOW)
    importer.import_batch(
        "identification.zip",
        (
            row(1, number=None, title="Alpha pending"),
            row(2, number="unknown value", title="Literal %_ marker"),
            row(3, number=None, title="Gamma pending"),
            row(4, number="ABP-001", title="Identified target"),
        ),
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
        identification_service=IdentificationService(factory),
    )
    app.add_event_handler("shutdown", engine.dispose)
    with TestClient(app) as client:
        yield client, factory


def row(tid: int, *, number: str | None, title: str) -> dict[str, object]:
    return {
        "tid": tid,
        "number": number,
        "title": title,
        "publish_date": None,
        "magnet": f"urn:fixture-secret-{tid}",
        "preview_images": "https://www.sehuatang.net/private-preview.jpg",
        "detail_url": "https://www.sehuatang.net/private-detail.htm",
        "size": 1024,
        "section": "亚洲有码",
        "category": None,
        "website": "sehuatang",
        "create_time": None,
        "update_time": None,
    }


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


def test_pending_list_requires_auth_and_uses_safe_query_bound_cursor(
    api_context: tuple[TestClient, sessionmaker],
) -> None:
    client, _ = api_context
    anonymous = client.get("/api/v1/admin/resources")
    headers = auth_headers(client)

    first = client.get("/api/v1/admin/resources?limit=2", headers=headers)
    assert anonymous.status_code == 401
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    cursor = first.json()["next_cursor"]
    assert cursor
    second = client.get(
        "/api/v1/admin/resources",
        params={"limit": 2, "cursor": cursor},
        headers=headers,
    )
    assert second.status_code == 200
    combined = first.json()["items"] + second.json()["items"]
    assert len(combined) == 3
    assert len({item["id"] for item in combined}) == 3
    safe_fields = {
        "id",
        "website",
        "external_post_id",
        "title",
        "raw_number",
        "publish_date",
        "section",
        "category",
        "resource_size_mb",
        "identification_status",
    }
    assert all(set(item) == safe_fields for item in combined)
    assert "fixture-secret" not in first.text + second.text
    assert "private-preview" not in first.text + second.text
    assert "private-detail" not in first.text + second.text

    literal = client.get(
        "/api/v1/admin/resources",
        params={"q": "%_"},
        headers=headers,
    )
    by_tid = client.get(
        "/api/v1/admin/resources",
        params={"q": "2"},
        headers=headers,
    )
    wrong_query = client.get(
        "/api/v1/admin/resources",
        params={"q": "Alpha", "cursor": cursor},
        headers=headers,
    )
    malformed_payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "id": 7,
                "imported_at": NOW.isoformat(),
                "q": "",
                "status": "pending",
                "v": 1,
            }
        ).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    malformed_cursor = client.get(
        "/api/v1/admin/resources",
        params={"cursor": malformed_payload},
        headers=headers,
    )
    lower_query = client.get(
        "/api/v1/admin/resources",
        params={"q": "pending", "limit": 1},
        headers=headers,
    )
    assert lower_query.json()["next_cursor"]
    same_query_different_case = client.get(
        "/api/v1/admin/resources",
        params={
            "q": "PENDING",
            "limit": 1,
            "cursor": lower_query.json()["next_cursor"],
        },
        headers=headers,
    )
    assert [item["external_post_id"] for item in literal.json()["items"]] == [2]
    assert [item["external_post_id"] for item in by_tid.json()["items"]] == [2]
    assert wrong_query.status_code == 422
    assert wrong_query.json()["code"] == "validation_failed"
    assert malformed_cursor.status_code == 422
    assert malformed_cursor.json()["code"] == "validation_failed"
    assert same_query_different_case.status_code == 200


def test_manual_identification_is_atomic_and_returns_stable_errors(
    api_context: tuple[TestClient, sessionmaker],
) -> None:
    client, factory = api_context
    headers = auth_headers(client)
    with factory() as session:
        pending = session.scalar(
            select(ResourceSource).where(ResourceSource.external_post_id == 1)
        )
        other_pending = session.scalar(
            select(ResourceSource).where(ResourceSource.external_post_id == 3)
        )
        movie = session.scalar(
            select(Movie).where(Movie.normalized_number == "ABP-001")
        )
    assert pending is not None and other_pending is not None and movie is not None

    identified = client.put(
        f"/api/v1/admin/resources/{pending.id}/identification",
        json={"movie_id": str(movie.id)},
        headers=headers,
    )
    repeated = client.put(
        f"/api/v1/admin/resources/{pending.id}/identification",
        json={"movie_id": str(movie.id)},
        headers=headers,
    )
    missing_source = client.put(
        f"/api/v1/admin/resources/{uuid.uuid4()}/identification",
        json={"movie_id": str(movie.id)},
        headers=headers,
    )
    missing_movie = client.put(
        f"/api/v1/admin/resources/{other_pending.id}/identification",
        json={"movie_id": str(uuid.uuid4())},
        headers=headers,
    )

    assert identified.status_code == 200
    assert identified.json() == {
        "id": str(pending.id),
        "website": "sehuatang",
        "external_post_id": 1,
        "title": "Alpha pending",
        "publish_date": None,
        "category": "亚洲有码",
        "labels": [],
        "resource_size_mb": 1024,
        "video_file_size_bytes": None,
        "availability": "available",
    }
    assert "fixture-secret" not in identified.text
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "source_already_identified"
    assert missing_source.status_code == 404
    assert missing_source.json()["code"] == "source_not_found"
    assert missing_movie.status_code == 404
    assert missing_movie.json()["code"] == "resource_not_found"
