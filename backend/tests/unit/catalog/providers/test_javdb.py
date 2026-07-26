from __future__ import annotations

from pathlib import Path
import json
from urllib.parse import parse_qs

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.catalog.providers.javdb import (
    EncryptedJavdbCredentialStore,
    CoreActorMetadata,
    CoreMovieMetadata,
    JavdbCredentials,
    JavdbProvider,
    MetadataProviderProblem,
    RankedMovieNumber,
)
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import Base, EncryptedSetting
from sakuraplayer.identity.secrets import EncryptedSettingRepository


FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "metadata"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def provider(handler) -> JavdbProvider:
    return JavdbProvider(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_search_requires_exact_normalized_number_and_fetches_boundary_dto() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/search":
            assert request.url.params["q"] == "ABP-123"
            return httpx.Response(200, text=fixture("javdb-search.html"))
        assert request.url.path == "/v/fixture-abp-123"
        return httpx.Response(200, text=fixture("javdb-detail.html"))

    javdb = provider(handler)
    candidate = javdb.search_movie("ABP-123")
    assert candidate is not None
    assert candidate.javdb_id == "fixture-abp-123"

    metadata = javdb.fetch_movie(candidate.javdb_id)

    assert metadata.normalized_number == "ABP-123"
    assert metadata.title_original == "Fixture Original Title"
    assert metadata.maker == "Fixture Maker"
    assert metadata.series == "Fixture Series"
    assert metadata.director == "Fixture Director"
    assert str(metadata.score) == "4.25"
    assert [actor.javdb_id for actor in metadata.actors] == [
        "actor-one",
        "actor-two",
    ]
    assert metadata.actors[0].aliases == ("Alias One", "Actor One")
    assert metadata.tags == ("Drama", "HD")
    assert metadata.cover_url == "https://c0.jdbstatic.com/covers/fixture.jpg"
    assert len(metadata.plot_urls) == 2
    assert len(requested) == 2


def test_public_core_lookup_works_without_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "cookie" not in request.headers
        assert "authorization" not in request.headers
        return httpx.Response(200, text=fixture("javdb-search.html"))

    assert provider(handler).search_movie("ABP-123") is not None


@pytest.mark.parametrize("board", ["daily", "weekly", "monthly"])
def test_public_rankings_preserve_original_rank_and_first_number(board: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v1/rankings/playback"
        assert dict(request.url.params) == {
            "filter_by": "all",
            "period": board,
        }
        assert "authorization" not in request.headers
        return httpx.Response(200, text=fixture("javdb-ranking-playback.json"))

    result = provider(handler).fetch_rankings(board, year=None, credentials=None)

    assert result == (
        RankedMovieNumber(rank=1, normalized_number="ABP-123"),
        RankedMovieNumber(rank=4, normalized_number="IPX-456"),
    )


@pytest.mark.parametrize(
    ("year", "ranking_type", "type_value"),
    [(None, "all", ""), (2020, "year", "2020")],
)
def test_top250_logs_in_and_stops_on_empty_page(
    year: int | None,
    ranking_type: str,
    type_value: str,
) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/api/v1/sessions":
            assert request.method == "POST"
            assert request.headers["content-type"].startswith(
                "application/x-www-form-urlencoded"
            )
            form = parse_qs(request.content.decode("utf-8"))
            assert form["username"] == ["fixture-user"]
            assert form["password"] == ["fixture-password"]
            assert form["device_uuid"]
            return httpx.Response(200, json={"success": 1, "data": {"token": "t"}})
        assert request.url.path == "/api/v1/movies/top"
        assert request.headers["authorization"] == "Bearer t"
        assert request.url.params["type"] == ranking_type
        assert request.url.params["type_value"] == type_value
        assert request.url.params["limit"] == "50"
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            text=fixture(
                "javdb-ranking-top-page.json"
                if page == 1
                else "javdb-ranking-empty.json"
            ),
        )

    result = provider(handler).fetch_rankings(
        "top250",
        year=year,
        credentials=JavdbCredentials("fixture-user", "fixture-password"),
    )

    assert result == (
        RankedMovieNumber(rank=1, normalized_number="SSIS-001"),
        RankedMovieNumber(rank=2, normalized_number="FC2-PPV-1234567"),
    )
    assert requests == ["/api/v1/sessions", "/api/v1/movies/top", "/api/v1/movies/top"]


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"success": 1, "data": {}}, "javdb_upstream_error"),
        ({"success": 1, "data": {"movies": []}}, "javdb_upstream_error"),
        ({"success": 0, "message": "fixture"}, "javdb_upstream_error"),
    ],
)
def test_ranking_empty_or_changed_payload_is_rejected(
    payload: dict,
    expected_code: str,
) -> None:
    javdb = provider(lambda request: httpx.Response(200, json=payload))

    with pytest.raises(MetadataProviderProblem) as error:
        javdb.fetch_rankings("daily", year=None, credentials=None)

    assert error.value.code == expected_code


def test_top250_login_rejection_maps_to_credentials_error() -> None:
    javdb = provider(
        lambda request: httpx.Response(
            200,
            json={"success": 0, "message": "fixture rejected"},
        )
    )

    with pytest.raises(MetadataProviderProblem) as error:
        javdb.fetch_rankings(
            "top250",
            year=None,
            credentials=JavdbCredentials("fixture-user", "fixture-password"),
        )

    assert error.value.code == "javdb_credentials_invalid"
    assert "fixture" not in str(error.value)


def test_core_dto_merges_duplicate_actor_ids_and_rejects_conflicting_names() -> None:
    duplicate = CoreMovieMetadata(
        javdb_id="movie-1",
        normalized_number="ABP-123",
        title_original="Fixture",
        actors=(
            CoreActorMetadata(
                javdb_id="actor-1",
                name="Actor One",
                aliases=("Alias One",),
            ),
            CoreActorMetadata(
                javdb_id="actor-1",
                name="Actor One",
                aliases=("Alias Two",),
            ),
        ),
    )

    assert len(duplicate.actors) == 1
    assert duplicate.actors[0].aliases == ("Alias One", "Alias Two")
    with pytest.raises(ValidationError):
        CoreMovieMetadata(
            javdb_id="movie-1",
            normalized_number="ABP-123",
            title_original="Fixture",
            actors=(
                CoreActorMetadata(javdb_id="actor-1", name="Actor One"),
                CoreActorMetadata(javdb_id="actor-1", name="Different Actor"),
            ),
        )


def test_search_not_found_and_structure_change_are_distinct() -> None:
    not_found = provider(lambda request: httpx.Response(404))
    assert not_found.search_movie("ABP-123") is None

    changed = provider(
        lambda request: httpx.Response(
            200,
            text=fixture("javdb-structure-changed.html"),
        )
    )
    with pytest.raises(MetadataProviderProblem) as error:
        changed.fetch_movie("fixture-abp-123")
    assert error.value.code == "javdb_upstream_error"


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_transient_status_maps_to_stable_error(status: int) -> None:
    javdb = provider(lambda request: httpx.Response(status))

    with pytest.raises(MetadataProviderProblem) as error:
        javdb.search_movie("ABP-123")

    assert error.value.code == "javdb_upstream_error"


def test_optional_credentials_are_loaded_only_as_a_complete_encrypted_pair() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    cipher = SecretCipher(
        InMemorySecretKeyProvider(active_key_id="v1", keys={"v1": b"k" * 32})
    )
    repository = EncryptedSettingRepository(factory, cipher)
    credentials = EncryptedJavdbCredentialStore(repository)
    try:
        assert credentials.load() is None

        saved = credentials.save(
            JavdbCredentials(
                username="fixture-user",
                password="fixture-password",
            ),
            expected_version=0,
        )
        assert saved.version == 1
        loaded = credentials.load()
        assert loaded is not None
        assert loaded.username == "fixture-user"
        assert loaded.password == "fixture-password"
        assert "fixture-user" not in repr(loaded)
        assert "fixture-password" not in repr(loaded)
        with factory() as session:
            rows = list(session.scalars(select(EncryptedSetting)))
        assert all(b"fixture" not in (row.ciphertext or b"") for row in rows)
    finally:
        engine.dispose()


def test_invalid_utf8_credentials_are_rejected_without_exposing_value() -> None:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    cipher = SecretCipher(
        InMemorySecretKeyProvider(active_key_id="v1", keys={"v1": b"k" * 32})
    )
    repository = EncryptedSettingRepository(factory, cipher)
    repository.create_secret("javdb.credentials", b"\xff")
    try:
        with pytest.raises(MetadataProviderProblem) as error:
            EncryptedJavdbCredentialStore(repository).load()
        assert error.value.code == "javdb_credentials_invalid"
        assert str(error.value) == "javdb_credentials_invalid"
    finally:
        engine.dispose()


def test_credential_decryption_failure_maps_to_credentials_invalid() -> None:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    original = EncryptedSettingRepository(
        factory,
        SecretCipher(
            InMemorySecretKeyProvider(
                active_key_id="v1",
                keys={"v1": b"k" * 32},
            )
        ),
    )
    EncryptedJavdbCredentialStore(original).save(
        JavdbCredentials("fixture-user", "fixture-password"),
        expected_version=0,
    )
    wrong_key = EncryptedSettingRepository(
        factory,
        SecretCipher(
            InMemorySecretKeyProvider(
                active_key_id="v1",
                keys={"v1": b"z" * 32},
            )
        ),
    )
    try:
        with pytest.raises(MetadataProviderProblem) as error:
            EncryptedJavdbCredentialStore(wrong_key).load()
        assert error.value.code == "javdb_credentials_invalid"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "fixture-user"},
        {"password": "fixture-password"},
        {"username": "", "password": "fixture-password"},
        {"username": "fixture-user", "password": ""},
        {"username": "fixture-user", "password": "fixture-password", "extra": True},
    ],
)
def test_malformed_atomic_credential_payload_is_rejected(payload: dict) -> None:
    engine = create_engine("sqlite+pysqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    repository = EncryptedSettingRepository(
        factory,
        SecretCipher(
            InMemorySecretKeyProvider(
                active_key_id="v1",
                keys={"v1": b"k" * 32},
            )
        ),
    )
    repository.create_secret(
        "javdb.credentials",
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )
    try:
        with pytest.raises(MetadataProviderProblem) as error:
            EncryptedJavdbCredentialStore(repository).load()
        assert error.value.code == "javdb_credentials_invalid"
    finally:
        engine.dispose()
