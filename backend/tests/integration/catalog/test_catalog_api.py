from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import Actor, ActorAlias, CatalogImage, MovieActor
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.discovery.favorites import FavoriteService
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.models import Movie, ResourceSource, ResourceSourceLabel
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
    database_name = f"task011_catalog_{uuid.uuid4().hex}"
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
    with TemporaryDirectory() as image_directory:
        favorites = FavoriteService(factory, now=lambda: NOW)
        catalog = CatalogQueryService(
            factory,
            favorite_port=favorites,
            image_root=Path(image_directory),
        )
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
            catalog_query_service=catalog,
            search_service=SearchService(catalog, queue),
            favorite_service=favorites,
        )
        app.add_event_handler("shutdown", engine.dispose)
        with TestClient(app) as client:
            yield client, factory, Path(image_directory)


def _movie(
    number: str,
    *,
    state: str = "core_ready",
    release_date: date = date(2026, 1, 1),
) -> Movie:
    return Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        title_original=f"Needle title {number}",
        title_zh=f"Translated {number}",
        release_date=release_date,
        catalog_state=state,
        created_at=NOW,
        updated_at=NOW,
    )


def _source(
    movie: Movie,
    external_id: int,
    *,
    publish_date: date,
    section: str,
    size: int,
) -> ResourceSource:
    return ResourceSource(
        id=uuid.uuid4(),
        website="sehuatang",
        external_post_id=external_id,
        movie_id=movie.id,
        raw_number=movie.normalized_number,
        normalized_number=movie.normalized_number,
        title=f"source {external_id}",
        publish_date=publish_date,
        section=section,
        category=None,
        resource_size_mb=size,
        detail_url="https://www.sehuatang.net/private-fixture",
        preview_urls=["https://www.sehuatang.net/private-preview"],
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


def test_postgres_catalog_filters_cursor_details_and_images_are_safe(
    api_context,
) -> None:
    client, factory, image_root = api_context
    first = _movie("ABP-101", release_date=date(2026, 1, 2))
    second = _movie("ABP-102")
    hidden = _movie("ABP-103", state="raw_only")
    first_subtitle = _source(
        first,
        101,
        publish_date=date(2026, 7, 26),
        section="中文字幕",
        size=900,
    )
    first_4k = _source(
        first,
        102,
        publish_date=date(2026, 7, 25),
        section="4K原版",
        size=1200,
    )
    second_both = _source(
        second,
        103,
        publish_date=date(2026, 7, 24),
        section="4K原版",
        size=1500,
    )
    hidden_source = _source(
        hidden,
        104,
        publish_date=date(2026, 7, 27),
        section="4K原版",
        size=1500,
    )
    actor = Actor(
        id=uuid.uuid4(),
        javdb_id="task011-actor",
        name_ja="Catalog Actor",
        name_zh="Catalog Actor ZH",
        bio_original="bio",
        bio_zh=None,
        bio_zh_source=None,
        gender="female",
        created_at=NOW,
        updated_at=NOW,
    )
    image_id = uuid.uuid4()
    relative_path = Path("movie") / str(second.id) / "cover.png"
    (image_root / relative_path).parent.mkdir(parents=True)
    (image_root / relative_path).write_bytes(b"safe-image")
    with factory.begin() as session:
        session.add_all(
            [
                first,
                second,
                hidden,
                actor,
            ]
        )
        session.flush()
        session.add_all(
            [
                first_subtitle,
                first_4k,
                second_both,
                hidden_source,
            ]
        )
        session.flush()
        session.add(MovieActor(movie_id=second.id, actor_id=actor.id, position=0))
        session.add(
            ActorAlias(
                actor_id=actor.id,
                alias="Shared Catalog Alias",
                normalized_alias="shared catalog alias",
                authority="javdb",
            )
        )
        for source, label in (
            (first_subtitle, "subtitle"),
            (first_4k, "4k"),
            (second_both, "subtitle"),
            (second_both, "4k"),
        ):
            session.add(
                ResourceSourceLabel(
                    source_id=source.id,
                    label=label,
                    evidence="fixture",
                    created_at=NOW,
                )
            )
        session.add(
            CatalogImage(
                id=image_id,
                owner_type="movie",
                owner_id=second.id,
                kind="cover",
                position=0,
                source_url="https://c0.jdbstatic.com/private-source.png",
                relative_path=relative_path.as_posix(),
                sha256="a" * 64,
                status="ready",
                created_at=NOW,
            )
        )

    assert client.get("/api/v1/movies").status_code == 401
    headers = _auth_headers(client)
    filtered = client.get(
        "/api/v1/movies",
        params={"labels": "subtitle,4k", "min_resource_size_mb": 1400},
        headers=headers,
    )
    first_page = client.get("/api/v1/movies", params={"limit": 1}, headers=headers)
    second_page = client.get(
        "/api/v1/movies",
        params={"limit": 1, "cursor": first_page.json()["next_cursor"]},
        headers=headers,
    )
    detail = client.get(f"/api/v1/movies/{second.id}", headers=headers)
    actor_search = client.get(
        "/api/v1/actors", params={"q": "shared catalog"}, headers=headers
    )
    image = client.get(f"/api/v1/catalog/images/{image_id}", headers=headers)
    playable = client.get(
        "/api/v1/movies", params={"playable": "true"}, headers=headers
    )

    assert filtered.status_code == 200
    assert [item["number"] for item in filtered.json()["items"]] == ["ABP-102"]
    assert [
        first_page.json()["items"][0]["number"],
        second_page.json()["items"][0]["number"],
    ] == ["ABP-101", "ABP-102"]
    assert detail.status_code == 200
    assert detail.json()["cover_url"] == f"/api/v1/catalog/images/{image_id}"
    assert detail.json()["progress"] is None
    assert detail.json()["sources"][0]["availability"] == "available"
    assert actor_search.json()["items"][0]["id"] == str(actor.id)
    assert image.status_code == 200
    assert image.content == b"safe-image"
    assert playable.json()["items"] == []
    for response in (filtered, first_page, second_page, detail, actor_search):
        assert "private-fixture" not in response.text
        assert "private-preview" not in response.text
        assert "private-source" not in response.text
        assert "magnet" not in response.text


def test_postgres_catalog_rejects_cursor_reuse_across_filters(api_context) -> None:
    client, factory, _ = api_context
    first_movie = _movie("ABP-201")
    second_movie = _movie("ABP-202")
    first_source = _source(
        first_movie,
        201,
        publish_date=date(2026, 7, 26),
        section="亚洲有码",
        size=1000,
    )
    second_source = _source(
        second_movie,
        202,
        publish_date=date(2026, 7, 25),
        section="亚洲有码",
        size=1000,
    )
    with factory.begin() as session:
        session.add_all([first_movie, second_movie, first_source, second_source])
    headers = _auth_headers(client)
    first = client.get("/api/v1/movies", params={"limit": 1}, headers=headers)
    reused = client.get(
        "/api/v1/movies",
        params={"limit": 1, "labels": "4k", "cursor": first.json()["next_cursor"]},
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["next_cursor"] is not None
    assert reused.status_code == 422
    assert reused.json()["code"] == "validation_failed"
