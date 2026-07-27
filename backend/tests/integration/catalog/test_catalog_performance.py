from __future__ import annotations

import math
import os
import uuid
from pathlib import Path
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.discovery.favorites import FavoriteService
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.identity.service import AuthService
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
SOURCE_COUNT = 289_858
MOVIE_COUNT = 5_000
ACTOR_COUNT = 1_000
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task011_perf_{uuid.uuid4().hex}"
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


def test_catalog_api_meets_real_scale_p95_and_uses_search_indexes(
    database_url: str,
    pytestconfig,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    _seed_scale_fixture(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    favorites = FavoriteService(factory)
    catalog = CatalogQueryService(factory, favorite_port=favorites)
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
    )
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        catalog_query_service=catalog,
        search_service=SearchService(catalog, MetadataQueue(factory)),
        favorite_service=favorites,
    )
    app.add_event_handler("shutdown", engine.dispose)
    with TestClient(app) as client:
        headers = _auth_headers(client)
        requests = {
            "movies": lambda: client.get(
                "/api/v1/movies", params={"limit": 24}, headers=headers
            ),
            "actors": lambda: client.get(
                "/api/v1/actors", params={"limit": 24}, headers=headers
            ),
            "exact": lambda: client.get(
                "/api/v1/search", params={"q": "ABP-4999"}, headers=headers
            ),
            "title": lambda: client.get(
                "/api/v1/search",
                params={"q": "Needle Title 4999"},
                headers=headers,
            ),
            "alias": lambda: client.get(
                "/api/v1/search",
                params={"q": "Needle Alias 999"},
                headers=headers,
            ),
        }
        samples = {name: _measure(call) for name, call in requests.items()}

    p95 = {name: _p95(values) for name, values in samples.items()}
    terminal = pytestconfig.pluginmanager.get_plugin("terminalreporter")
    if terminal is not None:
        metrics = ", ".join(f"{name}={value:.1f}" for name, value in p95.items())
        terminal.write_line(f"TASK-011 performance p95 ms: {metrics}")

    assert p95["movies"] < 500
    assert p95["actors"] < 500
    assert p95["exact"] < 300
    assert p95["title"] < 800
    assert p95["alias"] < 800

    with engine.connect() as connection:
        connection.execute(text("SET enable_seqscan = off"))
        exact_plan = _plan(
            connection,
            "SELECT id FROM movie WHERE normalized_number = 'ABP-4999'",
        )
        title_plan = _plan(
            connection,
            "SELECT id FROM movie WHERE title_original ILIKE '%needle title 4999%'",
        )
        alias_plan = _plan(
            connection,
            "SELECT actor_id FROM actor_alias "
            "WHERE normalized_alias ILIKE '%needle alias 999%'",
        )
        source_plan = _plan(
            connection,
            "SELECT max(publish_date) FROM resource_source "
            "WHERE movie_id = (md5('movie4999'))::uuid",
        )

    assert "uq_movie_normalized_number" in exact_plan
    assert "ix_movie_title_original_trgm" in title_plan
    assert "ix_actor_alias_normalized_trgm" in alias_plan
    assert "ix_resource_source_movie_id" in source_plan
    if terminal is not None:
        terminal.write_line(
            "TASK-011 query indexes: uq_movie_normalized_number, "
            "ix_movie_title_original_trgm, ix_actor_alias_normalized_trgm, "
            "ix_resource_source_movie_id"
        )


def _seed_scale_fixture(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                INSERT INTO movie (
                    id, normalized_number, raw_numbers, title_original,
                    catalog_state, created_at, updated_at
                )
                SELECT
                    (md5('movie' || g))::uuid,
                    'ABP-' || g,
                    to_jsonb(ARRAY['ABP-' || g]),
                    'Needle Title ' || g,
                    'core_ready',
                    TIMESTAMPTZ '2026-07-26 00:00:00+00',
                    TIMESTAMPTZ '2026-07-26 00:00:00+00'
                FROM generate_series(1, {MOVIE_COUNT}) AS g
                """
            )
        )
        connection.execute(
            text(
                f"""
                INSERT INTO resource_source (
                    id, website, external_post_id, movie_id, raw_number,
                    normalized_number, title, publish_date, section, category,
                    resource_size_mb, detail_url, preview_urls,
                    identification_status, imported_at
                )
                SELECT
                    (md5('source' || g))::uuid,
                    'sehuatang',
                    g,
                    (md5('movie' || (((g - 1) % {MOVIE_COUNT}) + 1)))::uuid,
                    'ABP-' || (((g - 1) % {MOVIE_COUNT}) + 1),
                    'ABP-' || (((g - 1) % {MOVIE_COUNT}) + 1),
                    'Scale source ' || g,
                    DATE '2026-07-26' - ((g % 365)::integer),
                    CASE WHEN g % 2 = 0 THEN '4K原版' ELSE '中文字幕' END,
                    NULL,
                    1000 + (g % 5000),
                    NULL,
                    '[]'::jsonb,
                    'identified',
                    TIMESTAMPTZ '2026-07-26 00:00:00+00'
                FROM generate_series(1, {SOURCE_COUNT}) AS g
                """
            )
        )
        connection.execute(
            text(
                f"""
                INSERT INTO actor (
                    id, javdb_id, name_ja, name_zh, gender, created_at, updated_at
                )
                SELECT
                    (md5('actor' || g))::uuid,
                    'actor-' || g,
                    'Needle Actor ' || g,
                    NULL,
                    'female',
                    TIMESTAMPTZ '2026-07-26 00:00:00+00',
                    TIMESTAMPTZ '2026-07-26 00:00:00+00'
                FROM generate_series(1, {ACTOR_COUNT}) AS g
                """
            )
        )
        connection.execute(
            text(
                f"""
                INSERT INTO actor_alias (actor_id, alias, normalized_alias, authority)
                SELECT
                    (md5('actor' || g))::uuid,
                    CASE
                        WHEN alias_no = 0 THEN 'Needle Alias ' || g
                        ELSE 'Noise Alias ' || g || ' ' || alias_no
                    END,
                    CASE
                        WHEN alias_no = 0 THEN 'needle alias ' || g
                        ELSE 'noise alias ' || g || ' ' || alias_no
                    END,
                    'javdb'
                FROM generate_series(1, {ACTOR_COUNT}) AS g
                CROSS JOIN generate_series(0, 99) AS alias_no
                """
            )
        )
        connection.execute(
            text(
                f"""
                INSERT INTO movie_actor (movie_id, actor_id, position)
                SELECT
                    (md5('movie' || g))::uuid,
                    (md5('actor' || (((g - 1) % {ACTOR_COUNT}) + 1)))::uuid,
                    0
                FROM generate_series(1, {MOVIE_COUNT}) AS g
                """
            )
        )
        connection.execute(text("ANALYZE"))


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


def _measure(call, *, samples: int = 20) -> list[float]:
    for _ in range(3):
        response = call()
        assert response.status_code == 200
    durations = []
    for _ in range(samples):
        started = perf_counter()
        response = call()
        durations.append((perf_counter() - started) * 1000)
        assert response.status_code == 200
    return durations


def _p95(samples: list[float]) -> float:
    return sorted(samples)[math.ceil(len(samples) * 0.95) - 1]


def _plan(connection, query: str) -> str:
    return "\n".join(
        row[0] for row in connection.execute(text(f"EXPLAIN (COSTS OFF) {query}"))
    )
