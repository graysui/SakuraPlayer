from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.discovery.favorites import FavoriteService
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.models import Movie, ResourceSource


NOW = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"bootstrap-token-with-at-least-32-bytes"


def test_catalog_discovery_api_is_authenticated_paginated_and_safe() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with TemporaryDirectory() as image_directory:
        favorites = FavoriteService(factory, now=lambda: NOW)
        catalog = CatalogQueryService(
            factory,
            favorite_port=favorites,
            image_root=Path(image_directory),
        )
        queue = MetadataQueue(factory, now=lambda: NOW)
        search = SearchService(catalog, queue)
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
            search_service=search,
            favorite_service=favorites,
        )
        movie = Movie(
            id=uuid.uuid4(),
            normalized_number="ABP-100",
            raw_numbers=["ABP-100"],
            title_original="Safe title",
            catalog_state="core_ready",
            created_at=NOW,
            updated_at=NOW,
        )
        source = ResourceSource(
            id=uuid.uuid4(),
            website="sehuatang",
            external_post_id=100,
            movie_id=movie.id,
            raw_number="ABP-100",
            normalized_number="ABP-100",
            title="Source title",
            publish_date=date(2026, 7, 26),
            section="亚洲有码",
            category=None,
            resource_size_mb=1000,
            detail_url="https://www.sehuatang.net/private-fixture",
            preview_urls=["https://www.sehuatang.net/private-preview"],
            identification_status="identified",
            imported_at=NOW,
        )
        with factory.begin() as session:
            session.add_all([movie, source])

        with TestClient(app) as client:
            anonymous = client.get("/api/v1/movies")
            headers = _auth_headers(client)
            listed = client.get("/api/v1/movies", headers=headers)
            duplicate_filter = client.get(
                "/api/v1/movies",
                params={"categories": "亚洲有码,亚洲有码"},
                headers=headers,
            )
            oversized_filter = client.get(
                "/api/v1/movies",
                params={"categories": ",".join(["亚洲有码"] * 101)},
                headers=headers,
            )
            detail = client.get(f"/api/v1/movies/{movie.id}", headers=headers)
            favorited = client.put(
                f"/api/v1/movies/{movie.id}/favorite",
                headers=headers,
            )
            favorites_page = client.get(
                "/api/v1/movies",
                params={"favorite": "true"},
                headers=headers,
            )
            searched = client.get(
                "/api/v1/search",
                params={"q": "ABP-100"},
                headers=headers,
            )
            malformed = client.get(
                "/api/v1/movies",
                params={"cursor": "not-a-cursor"},
                headers=headers,
            )

        assert anonymous.status_code == 401
        assert listed.status_code == detail.status_code == 200
        assert duplicate_filter.status_code == 200
        assert duplicate_filter.json()["items"][0]["number"] == "ABP-100"
        assert oversized_filter.status_code == 422
        assert oversized_filter.json()["code"] == "validation_failed"
        assert favorited.status_code == 204
        assert favorites_page.json()["items"][0]["favorite"] is True
        assert searched.headers["Cache-Control"] == "no-store"
        assert searched.json()["movies"][0]["number"] == "ABP-100"
        assert malformed.status_code == 422
        assert malformed.json()["code"] == "validation_failed"
        for response in (listed, detail, favorites_page, searched):
            assert "private-fixture" not in response.text
            assert "private-preview" not in response.text
            assert "magnet" not in response.text
    engine.dispose()


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
