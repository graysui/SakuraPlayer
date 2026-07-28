from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.cloud_cache.models import CacheJob
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.service import AuthService
from sakuraplayer.playback.heartbeat import PlaybackHeartbeatService
from sakuraplayer.playback.models import PlaybackLease
from sakuraplayer.playback.progress import (
    MoviePlaybackStateService,
    ProgressVersionConflict,
)
from sakuraplayer.playback.session import PlaybackSessionService
from sakuraplayer.resources.models import Movie
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.shared.migration import upgrade_database
from tests.integration.playback.test_original_redirect import (
    BOOTSTRAP_TOKEN,
    NOW,
    _seed_binding,
    _seed_ready_media,
    _source_row,
)

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


@pytest.fixture
def database_url():
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task111_progress_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()
    isolated_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        upgrade_database(isolated_url, ALEMBIC_INI)
        yield isolated_url
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


def test_cross_client_progress_conflict_manifest_catalog_and_cache_lifecycle(
    database_url: str,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"s" * 32},
        )
    )
    SourceImporter(factory, cipher=cipher, now=lambda: NOW).import_batch(
        "task111-fixture.zip", (_source_row(),)
    )
    binding_id = _seed_binding(factory, cipher)
    job_id, media_ids = _seed_ready_media(factory, binding_id)
    with factory.begin() as session:
        movie_id = session.scalar(
            select(CacheJob.movie_id).where(CacheJob.id == job_id)
        )
        assert movie_id is not None
        movie = session.get(Movie, movie_id)
        assert movie is not None
        movie.catalog_state = "core_ready"
        movie.title_original = "TASK-111 progress fixture"

    progress = MoviePlaybackStateService(factory, now=lambda: NOW)
    heartbeat = PlaybackHeartbeatService(
        factory,
        progress_service=progress,
        now=lambda: NOW,
    )
    sessions = PlaybackSessionService(
        factory,
        signing_key=b"p" * 32,
        now=lambda: NOW,
        progress_service=progress,
    )
    catalog = CatalogQueryService(factory, playback_port=progress)
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        catalog_query_service=catalog,
        playback_progress_service=progress,
        playback_heartbeat_service=heartbeat,
    )
    windows_id = uuid.uuid4()
    harmony_id = uuid.uuid4()
    try:
        with TestClient(app) as client:
            windows_headers = _bootstrap(client, windows_id)
            harmony_headers = _login(client, harmony_id)
            windows_admin = auth.authenticate_access(_token(windows_headers))
            harmony_admin = auth.authenticate_access(_token(harmony_headers))
            windows_manifest = sessions.create(
                admin=windows_admin,
                cache_job_id=job_id,
                media_id=media_ids[0],
                mode="original",
                platform="windows",
                client_instance_id=windows_id,
            )
            harmony_manifest = sessions.create(
                admin=harmony_admin,
                cache_job_id=job_id,
                media_id=media_ids[0],
                mode="original",
                platform="harmonyos",
                client_instance_id=harmony_id,
            )

            first = client.put(
                f"/api/v1/playback/sessions/{windows_manifest.session_id}/heartbeat",
                headers=windows_headers,
                json={
                    "client_instance_id": str(windows_id),
                    "progress": {
                        "position_seconds": 42.5,
                        "duration_seconds": None,
                        "version": 0,
                    },
                },
            )
            second = client.put(
                f"/api/v1/playback/sessions/{harmony_manifest.session_id}/heartbeat",
                headers=harmony_headers,
                json={
                    "client_instance_id": str(harmony_id),
                    "progress": {
                        "position_seconds": 950,
                        "duration_seconds": 1000,
                        "version": 1,
                    },
                },
            )
            assert first.status_code == 200
            assert first.json()["progress"] == {
                "position_seconds": 42.5,
                "duration_seconds": None,
                "completed": False,
                "version": 1,
            }
            assert second.status_code == 200
            assert second.json()["progress"] == {
                "position_seconds": 0.0,
                "duration_seconds": 1000.0,
                "completed": True,
                "version": 2,
            }

            lease_before, ttl_before = _lease_and_ttl(
                factory, windows_manifest.session_id, job_id
            )
            conflict = client.put(
                f"/api/v1/playback/sessions/{windows_manifest.session_id}/heartbeat",
                headers=windows_headers,
                json={
                    "client_instance_id": str(windows_id),
                    "progress": {
                        "position_seconds": 50,
                        "duration_seconds": 1000,
                        "version": 1,
                    },
                },
            )
            assert conflict.status_code == 409
            assert conflict.json()["code"] == "progress_version_conflict"
            assert conflict.json()["details"]["progress"]["version"] == 2
            assert _lease_and_ttl(factory, windows_manifest.session_id, job_id) == (
                lease_before,
                ttl_before,
            )

            detail = client.get(f"/api/v1/movies/{movie_id}", headers=harmony_headers)
            assert detail.status_code == 200
            assert detail.json()["progress"]["completed"] is True
            resumed = sessions.create(
                admin=windows_admin,
                cache_job_id=job_id,
                media_id=media_ids[0],
                mode="original",
                platform="windows",
                client_instance_id=windows_id,
            )
            assert resumed.progress is not None
            assert resumed.progress.position_seconds == 0
            assert resumed.progress.version == 2

        with factory.begin() as session:
            job = session.get(CacheJob, job_id)
            assert job is not None
            job.status = "cleaned"
            job.capacity_class = "released"
            job.binding_id = None
        state = progress.get(movie_id)
        assert state is not None and state.version == 2 and state.completed
    finally:
        engine.dispose()


def test_concurrent_first_writes_allow_exactly_one_expected_version_zero(
    database_url: str,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    movie_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(
            Movie(
                id=movie_id,
                normalized_number="TASK-111-CAS",
                raw_numbers=["TASK-111-CAS"],
                catalog_state="core_ready",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    service = MoviePlaybackStateService(factory, now=lambda: NOW)
    barrier = Barrier(2)

    def write(position: int) -> tuple[str, int]:
        barrier.wait()
        try:
            state = service.update(
                movie_id=movie_id,
                expected_version=0,
                position_seconds=Decimal(position),
                duration_seconds=None,
            )
            return "committed", state.version
        except ProgressVersionConflict as error:
            assert error.authoritative is not None
            return "conflict", error.authoritative.version

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(write, (10, 20)))
        assert sorted(results) == [("committed", 1), ("conflict", 1)]
        assert service.get(movie_id) is not None
    finally:
        engine.dispose()


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


def _login(client: TestClient, client_instance_id: uuid.UUID) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "admin",
            "password": "correct horse battery staple",
            "client_instance_id": str(client_instance_id),
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _token(headers: dict[str, str]) -> str:
    return headers["Authorization"].removeprefix("Bearer ")


def _lease_and_ttl(
    factory: sessionmaker,
    playback_session_id: uuid.UUID,
    job_id: uuid.UUID,
):
    with factory() as session:
        lease = session.scalar(
            select(PlaybackLease).where(
                PlaybackLease.playback_session_id == playback_session_id
            )
        )
        job = session.get(CacheJob, job_id)
        assert lease is not None and job is not None
        return lease.expires_at, job.expires_at
