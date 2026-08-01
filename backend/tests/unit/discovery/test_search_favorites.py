from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import Actor, ActorAlias, MetadataJob, MovieActor
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.discovery.favorites import FavoriteProblem, FavoriteService
from sakuraplayer.discovery.models import Favorite
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie, ResourceSource

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def context(tmp_path: Path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    favorites = FavoriteService(factory, now=lambda: NOW)
    catalog = CatalogQueryService(
        factory,
        favorite_port=favorites,
        image_root=tmp_path,
    )
    queue = MetadataQueue(factory, now=lambda: NOW)
    search = SearchService(catalog, queue)
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


def _source(movie: Movie, tid: int) -> ResourceSource:
    return ResourceSource(
        id=uuid.uuid4(),
        website="sehuatang",
        external_post_id=tid,
        movie_id=movie.id,
        raw_number=movie.normalized_number,
        normalized_number=movie.normalized_number,
        title=f"Source {tid}",
        publish_date=date(2026, 7, tid),
        section="亚洲有码",
        category=None,
        resource_size_mb=1000,
        detail_url="https://www.sehuatang.net/fixture",
        preview_urls=[],
        identification_status="identified",
        imported_at=NOW,
    )


def test_favorites_are_idempotent_visible_and_single_collection(context) -> None:
    factory, favorites, _, _ = context
    movie = _movie("ABP-001", state="core_ready")
    raw = _movie("ABP-002", state="raw_only")
    actor = Actor(
        id=uuid.uuid4(),
        javdb_id="actor-1",
        name_ja="Actor",
        name_zh=None,
        bio_original=None,
        bio_zh=None,
        bio_zh_source=None,
        gender="female",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add_all([movie, raw, _source(movie, 1), _source(raw, 2), actor])
        session.add(MovieActor(movie_id=movie.id, actor_id=actor.id, position=0))

    favorites.set_favorite("movie", movie.id, enabled=True)
    favorites.set_favorite("movie", movie.id, enabled=True)
    favorites.set_favorite("actor", actor.id, enabled=True)
    with pytest.raises(FavoriteProblem, match="resource_not_found"):
        favorites.set_favorite("movie", raw.id, enabled=True)

    with factory() as session:
        assert session.scalar(select(func.count(Favorite.id))) == 2
    assert favorites.target_ids("movie") == {movie.id}
    assert favorites.target_ids("actor") == {actor.id}

    favorites.set_favorite("movie", movie.id, enabled=False)
    favorites.set_favorite("movie", movie.id, enabled=False)
    assert favorites.target_ids("movie") == set()


def test_search_promotes_raw_candidate_and_never_retries_failed(context) -> None:
    factory, _, queue, search = context
    raw = _movie("ABP-010", state="raw_only")
    with factory.begin() as session:
        session.add_all([raw, _source(raw, 10)])
    original = queue.enqueue(
        movie_id=raw.id,
        normalized_number=raw.normalized_number,
        sort_date=date(2026, 7, 10),
        reason="history",
    )

    pending = search.search("abp-010", limit=24)
    with factory() as session:
        promoted = session.get(MetadataJob, original.job_id)
        assert promoted is not None
        assert (promoted.priority, promoted.reason) == (10, "manual_or_search")
    assert pending.movies == []
    assert pending.pending_metadata[0].movie_id == raw.id
    assert pending.pending_metadata[0].state == "queued"

    claim = queue.claim_next("search-worker", lease_duration=timedelta(seconds=30))
    assert claim is not None
    queue.fail(claim, code="javdb_movie_not_found", detail="fixture")
    failed = search.search("ABP-010", limit=24)
    with factory() as session:
        assert session.scalar(select(func.count(MetadataJob.id))) == 1
    assert failed.pending_metadata[0].state == "failed"
    assert failed.pending_metadata[0].movie_id == raw.id


def test_search_returns_all_actors_for_ambiguous_alias(context) -> None:
    factory, _, _, search = context
    movie = _movie("ABP-020", state="core_ready")
    actors = [
        Actor(
            id=uuid.uuid4(),
            javdb_id=f"actor-{index}",
            name_ja=f"Actor {index}",
            name_zh=None,
            bio_original=None,
            bio_zh=None,
            bio_zh_source=None,
            gender="female",
            created_at=NOW,
            updated_at=NOW,
        )
        for index in (1, 2)
    ]
    with factory.begin() as session:
        session.add_all([movie, _source(movie, 20), *actors])
        for position, actor in enumerate(actors):
            session.add(
                MovieActor(
                    movie_id=movie.id,
                    actor_id=actor.id,
                    position=position,
                )
            )
            session.add(
                ActorAlias(
                    actor_id=actor.id,
                    alias="Shared Alias",
                    normalized_alias="shared alias",
                    authority="javdb",
                )
            )

    result = search.search("shared alias", limit=24)

    assert {actor.id for actor in result.actors} == {actor.id for actor in actors}


def test_search_refreshes_when_raw_candidate_becomes_core_ready(context) -> None:
    factory, favorites, _, _ = context
    movie = _movie("ABP-030", state="raw_only")
    with factory.begin() as session:
        session.add_all([movie, _source(movie, 30)])

    class CompletingPort:
        def ensure_search_priority(self, **_):
            with factory.begin() as session:
                persisted = session.get(Movie, movie.id, with_for_update=True)
                assert persisted is not None
                persisted.catalog_state = "core_ready"
            return SimpleNamespace(job_id=uuid.uuid4(), state="completed")

    catalog = CatalogQueryService(factory, favorite_port=favorites)
    search = SearchService(catalog, CompletingPort())

    result = search.search("ABP-030", limit=24)

    assert [item.number for item in result.movies] == ["ABP-030"]
    assert result.pending_metadata == []
