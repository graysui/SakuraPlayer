from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.identification_api import IdentificationService
from sakuraplayer.resources.models import (
    Movie,
    ResourceSource,
    ResourceSourceLabel,
    SourceRejection,
)
from sakuraplayer.resources.movie_source_service import MovieSourceService
from sakuraplayer.resources.rejection import SourceRejectionService
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 25, 9, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task006_{uuid.uuid4().hex}"
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
def context(database_url: str):
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    cipher = SecretCipher(
        InMemorySecretKeyProvider(active_key_id="test-v1", keys={"test-v1": b"k" * 32})
    )
    importer = SourceImporter(factory, cipher=cipher, now=lambda: NOW)
    rejection_service = SourceRejectionService(factory, now=lambda: NOW)
    admin_service = MovieSourceService(factory, now=lambda: NOW)
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
        movie_source_admin_service=admin_service,
    )
    app.add_event_handler("shutdown", engine.dispose)
    with TestClient(app) as client:
        yield client, factory, importer, rejection_service


def row(
    tid: int,
    *,
    number: str,
    section: str = "亚洲有码",
    category: str | None = None,
    title: str | None = None,
) -> dict[str, object]:
    return {
        "tid": tid,
        "number": number,
        "title": title or f"Title {tid}",
        "publish_date": None,
        "magnet": f"urn:fixture-secret-{tid}",
        "preview_images": "",
        "detail_url": "https://www.sehuatang.net/thread-fixture.htm",
        "size": 1024,
        "section": section,
        "category": category,
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


def test_import_persists_overlapping_labels_and_rejection_blocks_reimport(
    context,
) -> None:
    _, factory, importer, rejection_service = context
    importer.import_batch(
        "labels.zip",
        (
            row(1, number="ABP-001", section="中文字幕"),
            row(2, number="ABP-002", category="无码破解"),
            row(3, number="ABP-003", section="4K原版", category="有码"),
            row(4, number="ABP-004", section="亚洲无码"),
        ),
    )

    with factory() as session:
        labels = {
            source.external_post_id: {
                (label.label, label.evidence)
                for label in session.scalars(
                    select(ResourceSourceLabel)
                    .join(ResourceSource)
                    .where(ResourceSource.id == ResourceSourceLabel.source_id)
                )
                if label.source_id == source.id
            }
            for source in session.scalars(select(ResourceSource))
        }
    assert labels[1] == {("subtitle", "section=中文字幕")}
    assert labels[2] == {("cracked", "category=无码破解")}
    assert labels[3] == {("4k", "section=4K原版"), ("censored", "category=有码")}
    assert labels[4] == set()

    rejection_service.reject(
        website="sehuatang", external_post_id=1, reason_code="offline_invalid"
    )
    rejection_service.reject(
        website="sehuatang", external_post_id=1, reason_code="offline_invalid"
    )
    stats = importer.import_batch("rejected.zip", (row(1, number="ABP-001"),))

    with factory() as session:
        source = session.scalar(
            select(ResourceSource).where(ResourceSource.external_post_id == 1)
        )
        rejection = session.scalar(select(SourceRejection))
        rejection_count = session.scalar(select(func.count(SourceRejection.id)))
    assert source is not None and rejection is not None
    assert source.identification_status == "rejected"
    assert source.magnet_envelope is None
    assert rejection.reason_code == "offline_invalid"
    assert rejection_count == 1
    assert stats.skipped == 1


def test_admin_merge_and_split_are_transactional_and_safe(context) -> None:
    client, factory, importer, _ = context
    importer.import_batch(
        "merge.zip",
        (row(10, number="ABP-010"), row(11, number="SSIS-011")),
    )
    headers = auth_headers(client)
    with factory() as session:
        movies = {
            movie.normalized_number: movie for movie in session.scalars(select(Movie))
        }
        first_source = session.scalar(
            select(ResourceSource).where(ResourceSource.external_post_id == 10)
        )
    assert first_source is not None

    merged = client.post(
        "/api/v1/admin/movies/merge",
        json={
            "target_movie_id": str(movies["ABP-010"].id),
            "source_movie_ids": [str(movies["SSIS-011"].id)],
        },
        headers=headers,
    )
    assert merged.status_code == 200
    assert "fixture-secret" not in merged.text
    assert merged.json()["source_count"] == 2

    split = client.post(
        f"/api/v1/admin/movies/{movies['ABP-010'].id}/sources/{first_source.id}/split",
        json={"new_normalized_number": "IPX-012"},
        headers=headers,
    )
    assert split.status_code == 201
    assert split.json()["number"] == "IPX-012"

    with factory() as session:
        sources = list(
            session.scalars(
                select(ResourceSource).order_by(ResourceSource.external_post_id)
            )
        )
        movies_after = list(session.scalars(select(Movie)))
    assert len(movies_after) == 2
    assert sources[0].normalized_number == "IPX-012"
    assert sources[1].normalized_number == "ABP-010"
    assert sources[0].movie_id != sources[1].movie_id


def test_admin_merge_rejects_invalid_or_conflicting_requests(context) -> None:
    client, factory, importer, _ = context
    importer.import_batch("conflict.zip", (row(20, number="ABP-020"),))
    headers = auth_headers(client)
    with factory() as session:
        movie = session.scalar(select(Movie))
        source = session.scalar(select(ResourceSource))
    assert movie is not None and source is not None

    invalid_merge = client.post(
        "/api/v1/admin/movies/merge",
        json={"target_movie_id": str(movie.id), "source_movie_ids": [str(movie.id)]},
        headers=headers,
    )
    conflict_split = client.post(
        f"/api/v1/admin/movies/{movie.id}/sources/{source.id}/split",
        json={"new_normalized_number": "ABP-020"},
        headers=headers,
    )
    assert invalid_merge.status_code == 409
    assert invalid_merge.json()["code"] == "movie_merge_conflict"
    assert conflict_split.status_code == 409
    assert conflict_split.json()["code"] == "movie_merge_conflict"


def test_concurrent_rejection_and_import_never_restore_a_rejected_source(
    context,
) -> None:
    _, factory, importer, rejection_service = context
    importer.import_batch("initial.zip", (row(30, number="ABP-030"),))
    barrier = Barrier(2)

    def reject() -> None:
        barrier.wait()
        rejection_service.reject(
            website="sehuatang",
            external_post_id=30,
            reason_code="offline_invalid",
        )

    def reimport() -> None:
        barrier.wait()
        importer.import_batch("concurrent.zip", (row(30, number="ABP-030"),))

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda action: action(), (reject, reimport)))

    with factory() as session:
        source = session.scalar(
            select(ResourceSource).where(ResourceSource.external_post_id == 30)
        )
        rejection = session.scalar(
            select(SourceRejection).where(SourceRejection.external_post_id == 30)
        )
    assert source is not None and rejection is not None
    assert source.identification_status == "rejected"
    assert source.magnet_envelope is None
