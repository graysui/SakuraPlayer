from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import math
import os
from pathlib import Path
from time import perf_counter
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import MetadataJob
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.discovery.models import RankingEntry, RankingSnapshot
from sakuraplayer.discovery.ranking_query import RankingQueryService
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.models import Movie, ResourceSource
from sakuraplayer.shared.migration import upgrade_database


pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task012_ranking_{uuid.uuid4().hex}"
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
    catalog = CatalogQueryService(factory)
    ranking = RankingQueryService(
        factory,
        catalog=catalog,
        completion=queue,
        credential_status=lambda: "not_configured",
        current_year=lambda: 2026,
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
        ranking_query_service=ranking,
    )
    app.add_event_handler("shutdown", engine.dispose)
    with TestClient(app) as client:
        yield client, factory


def _movie(number: str, *, state: str) -> Movie:
    return Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        title_original=f"Movie {number}",
        catalog_state=state,
        created_at=NOW,
        updated_at=NOW,
    )


def _source(movie: Movie, tid: int) -> ResourceSource:
    return ResourceSource(
        id=uuid.uuid4(),
        website="sehuatang",
        external_post_id=tid,
        movie_id=movie.id,
        raw_number=movie.normalized_number,
        normalized_number=movie.normalized_number,
        title=f"Source {tid}",
        publish_date=date(2026, 7, min(tid, 28)),
        section="亚洲有码",
        category=None,
        resource_size_mb=1000,
        detail_url="https://www.sehuatang.net/private-fixture",
        preview_urls=[],
        identification_status="identified",
        imported_at=NOW,
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


def test_postgres_ranking_api_filters_and_enqueues_metadata(api_context) -> None:
    client, factory = api_context
    snapshot_id = uuid.uuid4()
    visible = _movie("ABP-501", state="core_ready")
    raw = _movie("ABP-502", state="raw_only")
    with factory.begin() as session:
        session.add_all(
            [
                visible,
                raw,
                _source(visible, 1),
                _source(raw, 2),
                RankingSnapshot(
                    id=snapshot_id,
                    board="daily",
                    year=None,
                    status="current",
                    source_synced_at=NOW,
                    created_at=NOW,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                RankingEntry(
                    snapshot_id=snapshot_id,
                    rank=1,
                    normalized_number=visible.normalized_number,
                    movie_id=visible.id,
                ),
                RankingEntry(
                    snapshot_id=snapshot_id,
                    rank=2,
                    normalized_number=raw.normalized_number,
                    movie_id=raw.id,
                ),
            ]
        )

    assert client.get("/api/v1/rankings", params={"board": "daily"}).status_code == 401
    headers = _auth_headers(client)
    response = client.get(
        "/api/v1/rankings",
        params={"board": "daily"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["items"][0]["rank"] == 1
    assert response.json()["items"][0]["movie"]["number"] == "ABP-501"
    assert "private-fixture" not in response.text
    with factory() as session:
        queued = session.scalar(
            select(MetadataJob).where(
                MetadataJob.normalized_number == raw.normalized_number
            )
        )
        assert queued is not None
        assert (queued.priority, queued.reason) == (20, "ranking")


def test_postgres_ranking_api_returns_safe_unavailable_details(api_context) -> None:
    client, _ = api_context
    headers = _auth_headers(client)

    response = client.get(
        "/api/v1/rankings",
        params={"board": "top250"},
        headers=headers,
    )

    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["code"] == "ranking_snapshot_unavailable"
    assert response.json()["details"] == {"reason": "credentials_not_configured"}


def test_postgres_ranking_priority_is_concurrent_idempotent(api_context) -> None:
    _, factory = api_context
    movie = _movie("ABP-503", state="raw_only")
    with factory.begin() as session:
        session.add_all([movie, _source(movie, 3)])
    queue = MetadataQueue(factory, now=lambda: NOW)

    def ensure():
        return queue.ensure_ranking_priority(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 26),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: ensure(), range(2)))

    assert outcomes[0].job_id == outcomes[1].job_id
    with factory() as session:
        assert session.scalar(select(func.count(MetadataJob.id))) == 1


def test_postgres_cached_ranking_query_meets_p95(api_context, pytestconfig) -> None:
    client, factory = api_context
    snapshot_id = uuid.uuid4()
    with factory.begin() as session:
        session.execute(
            text(
                """
                INSERT INTO movie (
                    id, normalized_number, raw_numbers, title_original,
                    catalog_state, created_at, updated_at
                )
                SELECT
                    (md5('ranking-movie-' || g))::uuid,
                    'RANK-' || g,
                    to_jsonb(ARRAY['RANK-' || g]),
                    'Ranking Movie ' || g,
                    'core_ready',
                    :now,
                    :now
                FROM generate_series(1, 250) AS g
                """
            ),
            {"now": NOW},
        )
        session.execute(
            text(
                """
                INSERT INTO resource_source (
                    id, website, external_post_id, movie_id, raw_number,
                    normalized_number, title, publish_date, section, category,
                    resource_size_mb, detail_url, preview_urls,
                    identification_status, imported_at
                )
                SELECT
                    (md5('ranking-source-' || g))::uuid,
                    'sehuatang',
                    10000 + g,
                    (md5('ranking-movie-' || g))::uuid,
                    'RANK-' || g,
                    'RANK-' || g,
                    'Ranking Source ' || g,
                    DATE '2026-07-26',
                    '亚洲有码',
                    NULL,
                    1000,
                    NULL,
                    '[]'::jsonb,
                    'identified',
                    :now
                FROM generate_series(1, 250) AS g
                """
            ),
            {"now": NOW},
        )
        session.execute(
            text(
                "INSERT INTO ranking_snapshot "
                "(id, board, year, status, source_synced_at, created_at) "
                "VALUES (:id, 'monthly', NULL, 'current', :now, :now)"
            ),
            {"id": snapshot_id, "now": NOW},
        )
        session.execute(
            text(
                """
                INSERT INTO ranking_entry (
                    snapshot_id, rank, normalized_number, movie_id
                )
                SELECT
                    :snapshot_id,
                    g,
                    'RANK-' || g,
                    (md5('ranking-movie-' || g))::uuid
                FROM generate_series(1, 250) AS g
                """
            ),
            {"snapshot_id": snapshot_id},
        )
        session.execute(text("ANALYZE"))
    headers = _auth_headers(client)

    def request():
        return client.get(
            "/api/v1/rankings",
            params={"board": "monthly", "limit": 100},
            headers=headers,
        )

    for _ in range(3):
        assert request().status_code == 200
    samples: list[float] = []
    for _ in range(20):
        started = perf_counter()
        response = request()
        samples.append((perf_counter() - started) * 1000)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 100
    p95 = sorted(samples)[math.ceil(len(samples) * 0.95) - 1]
    terminal = pytestconfig.pluginmanager.get_plugin("terminalreporter")
    if terminal is not None:
        terminal.write_line(f"TASK-012 ranking p95 ms: {p95:.1f}")
    assert p95 < 500
