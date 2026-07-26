from __future__ import annotations

import base64
from datetime import date, datetime, timezone
import json
from pathlib import Path
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.models import (
    Actor,
    ActorAlias,
    CatalogImage,
    MovieActor,
)
from sakuraplayer.catalog.ports import (
    EmptyFavoriteStatePort,
    EmptyPlaybackStatePort,
    EmptySourceAvailabilityPort,
    SourceAvailability,
)
from sakuraplayer.catalog.query_service import (
    CatalogProblem,
    CatalogQueryService,
    MovieFilters,
)
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie, ResourceSource, ResourceSourceLabel


NOW = datetime(2026, 7, 26, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def catalog(tmp_path: Path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    service = CatalogQueryService(
        factory,
        availability_port=EmptySourceAvailabilityPort(),
        playback_port=EmptyPlaybackStatePort(),
        favorite_port=EmptyFavoriteStatePort(),
        image_root=tmp_path,
    )
    try:
        yield service, factory, tmp_path
    finally:
        engine.dispose()


def _movie(number: str, *, state: str = "core_ready") -> Movie:
    return Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        title_original=f"Original {number}",
        title_zh=f"中文 {number}",
        release_date=date(2026, 1, 1),
        catalog_state=state,
        created_at=NOW,
        updated_at=NOW,
    )


def _source(
    movie: Movie,
    tid: int,
    *,
    publish_date: date | None,
    section: str,
    size: int = 1000,
) -> ResourceSource:
    return ResourceSource(
        id=uuid.uuid4(),
        website="sehuatang",
        external_post_id=tid,
        movie_id=movie.id,
        raw_number=movie.normalized_number,
        normalized_number=movie.normalized_number,
        title=f"source {tid}",
        publish_date=publish_date,
        section=section,
        category=None,
        resource_size_mb=size,
        detail_url="https://www.sehuatang.net/fixture",
        preview_urls=[],
        identification_status="identified",
        imported_at=NOW,
    )


def test_movie_filters_are_correlated_to_one_source_and_cursor_is_query_bound(
    catalog,
) -> None:
    service, factory, _ = catalog
    first = _movie("ABP-001")
    second = _movie("ABP-002")
    hidden = _movie("ABP-003", state="raw_only")
    first_subtitle = _source(
        first,
        1,
        publish_date=date(2026, 7, 20),
        section="中文字幕",
    )
    first_4k = _source(
        first,
        2,
        publish_date=date(2026, 7, 21),
        section="4K原版",
    )
    second_both = _source(
        second,
        3,
        publish_date=date(2026, 7, 19),
        section="4K原版",
    )
    hidden_source = _source(
        hidden,
        4,
        publish_date=date(2026, 7, 22),
        section="4K原版",
    )
    with factory.begin() as session:
        session.add_all(
            [
                first,
                second,
                hidden,
                first_subtitle,
                first_4k,
                second_both,
                hidden_source,
            ]
        )
        session.add_all(
            [
                ResourceSourceLabel(
                    source_id=first_subtitle.id,
                    label="subtitle",
                    evidence="fixture",
                    created_at=NOW,
                ),
                ResourceSourceLabel(
                    source_id=first_4k.id,
                    label="4k",
                    evidence="fixture",
                    created_at=NOW,
                ),
                ResourceSourceLabel(
                    source_id=second_both.id,
                    label="subtitle",
                    evidence="fixture",
                    created_at=NOW,
                ),
                ResourceSourceLabel(
                    source_id=second_both.id,
                    label="4k",
                    evidence="fixture",
                    created_at=NOW,
                ),
            ]
        )

    filtered = service.list_movies(
        filters=MovieFilters(labels=("subtitle", "4k")),
        cursor=None,
        limit=24,
    )
    first_page = service.list_movies(
        filters=MovieFilters(),
        cursor=None,
        limit=1,
    )
    second_page = service.list_movies(
        filters=MovieFilters(),
        cursor=first_page.next_cursor,
        limit=1,
    )

    assert [item.number for item in filtered.items] == ["ABP-002"]
    assert [item.number for item in first_page.items] == ["ABP-001"]
    assert [item.number for item in second_page.items] == ["ABP-002"]
    with pytest.raises(CatalogProblem, match="validation_failed"):
        service.list_movies(
            filters=MovieFilters(labels=("4k",)),
            cursor=first_page.next_cursor,
            limit=1,
        )


def test_phase_one_ports_and_safe_aggregated_detail(catalog) -> None:
    service, factory, image_root = catalog
    movie = _movie("ABP-010")
    source = _source(
        movie,
        10,
        publish_date=date(2026, 7, 25),
        section="中文字幕",
    )
    actor = Actor(
        id=uuid.uuid4(),
        javdb_id="actor-1",
        name_ja="Actor One",
        name_zh="演员一",
        bio_original="bio",
        bio_zh="简介",
        bio_zh_source="actor_mapping",
        gender="female",
        created_at=NOW,
        updated_at=NOW,
    )
    image_id = uuid.uuid4()
    relative_path = Path("movie") / str(movie.id) / "cover.png"
    (image_root / relative_path).parent.mkdir(parents=True)
    (image_root / relative_path).write_bytes(b"fixture")
    with factory.begin() as session:
        session.add_all([movie, source, actor])
        session.add(MovieActor(movie_id=movie.id, actor_id=actor.id, position=0))
        session.add(
            ActorAlias(
                actor_id=actor.id,
                alias="Alias One",
                normalized_alias="alias one",
                authority="javdb",
            )
        )
        session.add(
            CatalogImage(
                id=image_id,
                owner_type="movie",
                owner_id=movie.id,
                kind="cover",
                position=0,
                source_url="https://c0.jdbstatic.com/fixture.png",
                relative_path=relative_path.as_posix(),
                sha256="a" * 64,
                status="ready",
                created_at=NOW,
            )
        )

    not_playable = service.list_movies(
        filters=MovieFilters(playable=True),
        cursor=None,
        limit=24,
    )
    detail = service.get_movie(movie.id)
    image = service.resolve_image(image_id)

    assert not_playable.items == []
    assert detail.progress is None
    assert detail.cover_url == f"/api/v1/catalog/images/{image_id}"
    assert detail.sources[0].availability == "available"
    assert detail.sources[0].video_file_size_bytes is None
    assert detail.actors[0].aliases == ["Alias One"]
    assert image.path == (image_root / relative_path).resolve()
    assert image.media_type == "image/png"
    serialized = repr(detail)
    assert "magnet" not in serialized
    assert "sehuatang.net" not in serialized


def test_invalid_size_range_and_escaping_image_are_rejected(catalog) -> None:
    service, factory, image_root = catalog
    movie = _movie("ABP-020")
    source = _source(
        movie,
        20,
        publish_date=date(2026, 7, 20),
        section="亚洲有码",
    )
    image_id = uuid.uuid4()
    outside = image_root.parent / f"outside-{uuid.uuid4().hex}"
    outside.mkdir()
    (outside / "outside.png").write_bytes(b"outside")
    (image_root / "escape").symlink_to(outside, target_is_directory=True)
    with factory.begin() as session:
        session.add_all([movie, source])
        session.add(
            CatalogImage(
                id=image_id,
                owner_type="movie",
                owner_id=movie.id,
                kind="cover",
                position=0,
                source_url=None,
                relative_path="escape/outside.png",
                sha256="b" * 64,
                status="placeholder",
                created_at=NOW,
            )
        )

    with pytest.raises(CatalogProblem, match="validation_failed"):
        service.list_movies(
            filters=MovieFilters(min_resource_size_mb=2, max_resource_size_mb=1),
            cursor=None,
            limit=24,
        )
    with pytest.raises(CatalogProblem, match="resource_not_found"):
        service.resolve_image(image_id)


def test_publish_date_ascending_cursor_continues_through_null_dates(catalog) -> None:
    service, factory, _ = catalog
    dated = _movie("ABP-030")
    first_null = _movie("ABP-031")
    second_null = _movie("ABP-032")
    dated.id = uuid.UUID("00000000-0000-0000-0000-000000000100")
    first_null.id = uuid.UUID("00000000-0000-0000-0000-000000000200")
    second_null.id = uuid.UUID("00000000-0000-0000-0000-000000000300")
    with factory.begin() as session:
        session.add_all(
            [
                dated,
                first_null,
                second_null,
                _source(
                    dated,
                    30,
                    publish_date=date(2026, 7, 1),
                    section="亚洲有码",
                ),
                _source(
                    first_null,
                    31,
                    publish_date=None,
                    section="亚洲有码",
                ),
                _source(
                    second_null,
                    32,
                    publish_date=None,
                    section="亚洲有码",
                ),
            ]
        )

    first_page = service.list_movies(
        filters=MovieFilters(sort="publish_date_asc"),
        cursor=None,
        limit=2,
    )
    second_page = service.list_movies(
        filters=MovieFilters(sort="publish_date_asc"),
        cursor=first_page.next_cursor,
        limit=2,
    )

    assert [item.number for item in first_page.items] == ["ABP-030", "ABP-031"]
    assert [item.number for item in second_page.items] == ["ABP-032"]


def test_playable_filter_scans_past_nonmatching_database_rows(catalog) -> None:
    _, factory, image_root = catalog
    movies = [_movie(f"ABP-04{index}") for index in range(3)]
    sources = [
        _source(
            movie,
            40 + index,
            publish_date=date(2026, 7, 3 - index),
            section="亚洲有码",
        )
        for index, movie in enumerate(movies)
    ]
    with factory.begin() as session:
        session.add_all([*movies, *sources])

    class AvailabilityPort:
        def get_many(self, source_ids):
            return {
                source_id: SourceAvailability(state="ready")
                for source_id in source_ids
                if source_id == sources[2].id
            }

    service = CatalogQueryService(
        factory,
        availability_port=AvailabilityPort(),
        favorite_port=EmptyFavoriteStatePort(),
        image_root=image_root,
    )

    page = service.list_movies(
        filters=MovieFilters(playable=True),
        cursor=None,
        limit=1,
    )

    assert [item.number for item in page.items] == [movies[2].normalized_number]
    assert page.next_cursor is None


def test_actor_alias_limit_is_applied_per_actor(catalog) -> None:
    service, factory, _ = catalog
    movie = _movie("ABP-050")
    source = _source(
        movie,
        50,
        publish_date=date(2026, 7, 5),
        section="亚洲有码",
    )
    actors = [
        Actor(
            id=uuid.uuid4(),
            javdb_id=f"alias-actor-{index}",
            name_ja=f"Actor {index}",
            name_zh=None,
            bio_original=None,
            bio_zh=None,
            bio_zh_source=None,
            gender="female",
            created_at=NOW,
            updated_at=NOW,
        )
        for index in range(2)
    ]
    with factory.begin() as session:
        session.add_all([movie, source, *actors])
        for position, actor in enumerate(actors):
            session.add(
                MovieActor(
                    movie_id=movie.id,
                    actor_id=actor.id,
                    position=position,
                )
            )
        session.add_all(
            ActorAlias(
                actor_id=actors[0].id,
                alias=f"Alias {index:03d}",
                normalized_alias=f"alias {index:03d}",
                authority="javdb",
            )
            for index in range(201)
        )
        session.add(
            ActorAlias(
                actor_id=actors[1].id,
                alias="Visible Alias",
                normalized_alias="visible alias",
                authority="javdb",
            )
        )

    page = service.list_actors(q=None, cursor=None, limit=24, favorite=False)
    by_id = {actor.id: actor for actor in page.items}

    assert len(by_id[actors[0].id].aliases) == 100
    assert by_id[actors[1].id].aliases == ["Visible Alias"]


@pytest.mark.parametrize(
    ("key", "version"),
    [("not-a-date", 1), ("2026-07-01", True)],
)
def test_publish_cursor_rejects_invalid_date_and_version_types(
    catalog,
    key,
    version,
) -> None:
    service, _, _ = catalog
    payload = {
        "categories": [],
        "favorite": False,
        "id": str(uuid.uuid4()),
        "key": key,
        "labels": [],
        "max_size": None,
        "min_size": None,
        "playable": None,
        "sort": "publish_date_desc",
        "v": version,
        "website": None,
    }
    cursor = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")

    with pytest.raises(CatalogProblem, match="validation_failed"):
        service.list_movies(filters=MovieFilters(), cursor=cursor, limit=24)


def test_number_cursor_uses_normalized_number_instead_of_publish_date(catalog) -> None:
    service, factory, _ = catalog
    movies = [_movie(number) for number in ("ABP-060", "ABP-061", "ABP-062")]
    with factory.begin() as session:
        session.add_all(
            [
                *movies,
                _source(
                    movies[0],
                    60,
                    publish_date=date(2026, 7, 3),
                    section="亚洲有码",
                ),
                _source(
                    movies[1],
                    61,
                    publish_date=date(2026, 7, 1),
                    section="亚洲有码",
                ),
                _source(
                    movies[2],
                    62,
                    publish_date=date(2026, 7, 2),
                    section="亚洲有码",
                ),
            ]
        )

    first = service.list_movies(
        filters=MovieFilters(sort="number_asc"),
        cursor=None,
        limit=1,
    )
    second = service.list_movies(
        filters=MovieFilters(sort="number_asc"),
        cursor=first.next_cursor,
        limit=1,
    )

    assert [item.number for item in first.items] == ["ABP-060"]
    assert [item.number for item in second.items] == ["ABP-061"]
