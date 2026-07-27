from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import MetadataJob
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.discovery.favorites import FavoriteService
from sakuraplayer.discovery.models import Favorite
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.resources.models import Movie, ResourceSource
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 26, 11, 0, tzinfo=timezone.utc)


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task011_discovery_{uuid.uuid4().hex}"
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
    favorites = FavoriteService(factory, now=lambda: NOW)
    queue = MetadataQueue(factory, now=lambda: NOW)
    search = SearchService(
        CatalogQueryService(factory, favorite_port=favorites),
        queue,
    )
    try:
        yield factory, favorites, queue, search
    finally:
        engine.dispose()


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


def _source(movie: Movie, external_id: int) -> ResourceSource:
    return ResourceSource(
        id=uuid.uuid4(),
        website="sehuatang",
        external_post_id=external_id,
        movie_id=movie.id,
        raw_number=movie.normalized_number,
        normalized_number=movie.normalized_number,
        title=f"source {external_id}",
        publish_date=date(2026, 7, 26),
        section="亚洲有码",
        category=None,
        resource_size_mb=1000,
        detail_url=None,
        preview_urls=[],
        identification_status="identified",
        imported_at=NOW,
    )


def test_postgres_concurrent_favorite_puts_create_one_row(context) -> None:
    factory, favorites, _, _ = context
    movie = _movie("ABP-301", state="core_ready")
    with factory.begin() as session:
        session.add_all([movie, _source(movie, 301)])
    barrier = Barrier(2)

    def favorite_once() -> None:
        barrier.wait()
        favorites.set_favorite("movie", movie.id, enabled=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: favorite_once(), range(2)))

    with factory() as session:
        assert session.scalar(select(func.count(Favorite.id))) == 1
    favorites.set_favorite("movie", movie.id, enabled=False)
    favorites.set_favorite("movie", movie.id, enabled=False)
    assert favorites.target_ids("movie") == set()


def test_postgres_concurrent_search_priority_reuses_and_promotes_one_job(
    context,
) -> None:
    factory, _, queue, search = context
    raw = _movie("ABP-302", state="raw_only")
    with factory.begin() as session:
        session.add_all([raw, _source(raw, 302)])
    original = queue.enqueue(
        movie_id=raw.id,
        normalized_number=raw.normalized_number,
        sort_date=date(2026, 7, 25),
        reason="history",
    )
    barrier = Barrier(2)

    def search_once():
        barrier.wait()
        return search.search("ABP-302", limit=24)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: search_once(), range(2)))

    assert {result.pending_metadata[0].metadata_job_id for result in results} == {
        original.job_id
    }
    with factory() as session:
        job = session.get(MetadataJob, original.job_id)
        assert job is not None
        assert (job.priority, job.reason) == (10, "manual_or_search")
        assert session.scalar(select(func.count(MetadataJob.id))) == 1

    claim = queue.claim_next("search-worker", lease_duration=timedelta(seconds=30))
    assert claim is not None
    running = search.search("ABP-302", limit=24)
    assert running.pending_metadata[0].state == "running"
    queue.fail(claim, code="javdb_movie_not_found", detail="fixture")
    failed = search.search("ABP-302", limit=24)
    assert failed.pending_metadata[0].state == "failed"
    with factory() as session:
        assert session.scalar(select(func.count(MetadataJob.id))) == 1
