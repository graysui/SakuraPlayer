from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    HlsInfo,
    HlsVariant,
    OriginalUrl,
)
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.service import AuthService
from sakuraplayer.playback.hls import HlsStreamResolver
from sakuraplayer.playback.original import OriginalStreamResolver
from sakuraplayer.playback.resolver import PlaybackStreamResolver
from sakuraplayer.playback.session import PlaybackSessionService
from sakuraplayer.playback.user_agents import WINDOWS_USER_AGENT
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.shared.migration import upgrade_database
from tests.fakes.cloud115 import FakeCloud115
from tests.integration.playback.test_original_redirect import (
    BOOTSTRAP_TOKEN,
    NOW,
    CloudScopeStub,
    _assert_database_does_not_contain,
    _bootstrap,
    _seed_binding,
    _seed_ready_media,
    _source_row,
)

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


@pytest.fixture
def database_url() -> Iterator[str]:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task109_playback_{uuid.uuid4().hex}"
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


def test_compatibility_and_original_fallback_redirects(database_url: str) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    variants = (
        _variant("https://cdn.115.com/720.m3u8", 1_800_000),
        _variant("https://cdn.115.com/1080-first.m3u8", 3_600_000),
        _variant("https://cdn.115.com/1080-second.m3u8", 3_600_000),
    )
    fake = FakeCloud115(
        original_urls=[
            OriginalUrl(
                url="https://cdn.115.com/original-fixture",
                expires_at=NOW + timedelta(hours=1),
                file_id="media-file-1",
                file_name="fixture.part2.mkv",
                file_size_bytes=300_000_000,
                sha1="fixture-sha1",
                pickcode="fixture-pickcode-1",
                user_agent=WINDOWS_USER_AGENT,
            ),
            Cloud115Problem("cloud115_original_unavailable"),
            Cloud115Problem("cloud115_credentials_expired"),
        ],
        hls_infos=[
            HlsInfo(pickcode="fixture-pickcode-1", variants=variants),
            HlsInfo(pickcode="fixture-pickcode-1", variants=variants),
            Cloud115Problem("cloud115_hls_membership_required"),
            Cloud115Problem("cloud115_hls_not_ready"),
            Cloud115Problem("cloud115_hls_unavailable"),
        ],
    )
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    source_cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"s" * 32},
        )
    )
    SourceImporter(factory, cipher=source_cipher, now=lambda: NOW).import_batch(
        "task109-fixture.zip", (_source_row(),)
    )
    binding_id = _seed_binding(factory, source_cipher)
    scope = CloudScopeStub(fake)
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        playback_session_service=PlaybackSessionService(
            factory,
            signing_key=b"p" * 32,
            now=lambda: NOW,
        ),
        playback_stream_resolver=PlaybackStreamResolver(
            OriginalStreamResolver(scope),  # type: ignore[arg-type]
            HlsStreamResolver(scope),  # type: ignore[arg-type]
        ),
    )
    client_instance_id = uuid.uuid4()
    try:
        with TestClient(app) as client:
            headers = _bootstrap(client, client_instance_id)
            job_id, media_ids = _seed_ready_media(factory, binding_id)

            original = _create_manifest(
                client, headers, job_id, media_ids[1], client_instance_id, "original"
            )
            original_redirect = _get_stream(client, original)

            fallback = _create_manifest(
                client, headers, job_id, media_ids[1], client_instance_id, "original"
            )
            fallback_redirect = _get_stream(client, fallback)

            credentials = _create_manifest(
                client, headers, job_id, media_ids[1], client_instance_id, "original"
            )
            credentials_error = _get_stream(client, credentials)

            compatibility = _create_manifest(
                client,
                headers,
                job_id,
                media_ids[1],
                client_instance_id,
                "compatibility",
            )
            compatibility_redirect = _get_stream(client, compatibility)

            hls_errors = []
            for _ in range(3):
                manifest = _create_manifest(
                    client,
                    headers,
                    job_id,
                    media_ids[1],
                    client_instance_id,
                    "compatibility",
                )
                hls_errors.append(_get_stream(client, manifest))

            for location in (
                "https://cdn.115.com/original-fixture",
                "https://cdn.115.com/1080-first.m3u8",
            ):
                _assert_database_does_not_contain(factory, location)
    finally:
        engine.dispose()

    assert original["mode"] == "original"
    assert compatibility["mode"] == "compatibility"
    assert "variants" not in original
    assert "variants" not in compatibility
    _assert_redirect(original_redirect, "https://cdn.115.com/original-fixture")
    _assert_redirect(fallback_redirect, "https://cdn.115.com/1080-first.m3u8")
    _assert_redirect(compatibility_redirect, "https://cdn.115.com/1080-first.m3u8")
    assert credentials_error.status_code == 422
    assert credentials_error.json()["code"] == "cloud115_credentials_expired"
    assert [(item.status_code, item.json()["code"]) for item in hls_errors] == [
        (422, "cloud115_hls_membership_required"),
        (503, "cloud115_hls_not_ready"),
        (502, "cloud115_hls_unavailable"),
    ]
    assert [call.operation for call in fake.calls] == [
        "resolve_original",
        "resolve_original",
        "resolve_hls",
        "resolve_original",
        "resolve_hls",
        "resolve_hls",
        "resolve_hls",
        "resolve_hls",
    ]


def _create_manifest(
    client: TestClient,
    headers: dict[str, str],
    job_id: uuid.UUID,
    media_id: uuid.UUID,
    client_instance_id: uuid.UUID,
    mode: str,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/cache-jobs/{job_id}/playback-sessions",
        headers=headers,
        json={
            "media_id": str(media_id),
            "mode": mode,
            "platform": "windows",
            "client_instance_id": str(client_instance_id),
        },
    )
    assert response.status_code == 201
    return response.json()


def _get_stream(client: TestClient, manifest: dict[str, object]):
    return client.get(
        str(manifest["stream_url"]),
        headers={"User-Agent": WINDOWS_USER_AGENT},
        follow_redirects=False,
    )


def _variant(url: str, bandwidth: int) -> HlsVariant:
    return HlsVariant(
        url=url,
        bandwidth=bandwidth,
        resolution="1920x1080",
        label="fixture",
        user_agent=WINDOWS_USER_AGENT,
    )


def _assert_redirect(response, location: str) -> None:
    assert response.status_code == 302
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["location"] == location
    assert response.content == b""
