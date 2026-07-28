from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    Cloud115Binding,
    RemoteMedia,
)
from sakuraplayer.cloud_cache.ports.cloud115 import OriginalUrl
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.identity.service import AuthService
from sakuraplayer.playback.hls import HlsStreamResolver
from sakuraplayer.playback.original import OriginalStreamResolver
from sakuraplayer.playback.resolver import PlaybackStreamResolver
from sakuraplayer.playback.session import PlaybackSessionService
from sakuraplayer.playback.user_agents import WINDOWS_USER_AGENT
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.shared.migration import upgrade_database
from tests.fakes.cloud115 import FakeCloud115

pytestmark = pytest.mark.integration

BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 28, 14, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"task108-bootstrap-token-at-least-32-bytes"


class CloudScopeStub:
    def __init__(self, fake: FakeCloud115) -> None:
        self._fake = fake

    @asynccontextmanager
    async def cache_operation_scope(self, **_kwargs: object):
        yield self._fake


@pytest.fixture
def database_url() -> Iterator[str]:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task108_playback_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()
    database_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        upgrade_database(database_url, ALEMBIC_INI)
        yield database_url
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


def test_original_redirect_uses_fixed_ua_and_never_proxies_bytes(
    database_url: str,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
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
            )
        ]
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
        "task108-fixture.zip", (_source_row(),)
    )
    binding_id = _seed_binding(factory, source_cipher)
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        playback_session_service=PlaybackSessionService(
            factory,
            signing_key=b"p" * 32,
            now=lambda: NOW,
        ),
        playback_stream_resolver=PlaybackStreamResolver(
            OriginalStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
            HlsStreamResolver(CloudScopeStub(fake)),  # type: ignore[arg-type]
        ),
    )
    client_instance_id = uuid.uuid4()
    try:
        with TestClient(app) as client:
            headers = _bootstrap(client, client_instance_id)
            job_id, media_ids = _seed_ready_media(factory, binding_id)
            created = client.post(
                f"/api/v1/cache-jobs/{job_id}/playback-sessions",
                headers=headers,
                json={
                    "media_id": str(media_ids[1]),
                    "mode": "original",
                    "platform": "windows",
                    "client_instance_id": str(client_instance_id),
                },
            )
            assert created.status_code == 201
            manifest = created.json()
            assert manifest["required_user_agent"] == WINDOWS_USER_AGENT
            assert [item["media"]["id"] for item in manifest["media_queue"]] == [
                str(media_id) for media_id in media_ids
            ]
            assert len({item["session_id"] for item in manifest["media_queue"]}) == len(
                media_ids
            )
            assert manifest["session_id"] == manifest["media_queue"][1]["session_id"]
            assert manifest["stream_url"] == manifest["media_queue"][1]["stream_url"]
            assert manifest["progress"] is None

            rejected = client.get(
                manifest["stream_url"],
                headers={"User-Agent": "wrong-user-agent"},
                follow_redirects=False,
            )
            redirected = client.get(
                manifest["stream_url"],
                headers={"User-Agent": WINDOWS_USER_AGENT},
                follow_redirects=False,
            )
            _assert_database_does_not_contain(
                factory, "https://cdn.115.com/original-fixture"
            )
    finally:
        engine.dispose()

    assert rejected.status_code == 403
    assert redirected.status_code == 302
    assert redirected.headers["cache-control"] == "no-store"
    assert redirected.headers["location"] == "https://cdn.115.com/original-fixture"
    assert redirected.content == b""
    assert [call.operation for call in fake.calls] == ["resolve_original"]
    assert fake.calls[0].safe_arguments[1] == WINDOWS_USER_AGENT


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


def _seed_binding(factory: sessionmaker, cipher: SecretCipher) -> uuid.UUID:
    binding_id = uuid.uuid4()
    secrets = EncryptedSettingRepository(factory, cipher, now=lambda: NOW)
    credential_version = secrets.create_secret(
        "cloud115.cookie", b"credential-fixture"
    ).version
    with factory.begin() as session:
        session.add(
            Cloud115Binding(
                id=binding_id,
                singleton_key=True,
                account_key="account",
                display_name=None,
                cookie_setting_key="cloud115.cookie",
                login_app="alipaymini",
                cache_root_cid="root",
                status="active",
                credential_version=credential_version,
                last_verified_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return binding_id


def _seed_ready_media(
    factory: sessionmaker, binding_id: uuid.UUID
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    job_id = uuid.uuid4()
    media_ids = [uuid.uuid4(), uuid.uuid4()]
    with factory.begin() as session:
        source = session.execute(
            text("SELECT movie_id, id FROM resource_source LIMIT 1")
        ).one()
        session.add(
            CacheJob(
                id=job_id,
                movie_id=source.movie_id,
                source_id=source.id,
                binding_id=binding_id,
                status="ready",
                capacity_class="ready",
                account_key="account",
                cache_root_cid="root",
                task_dir_cid="task",
                task_dir_name="cache-task",
                remote_percent=100,
                ready_at=NOW,
                last_accessed_at=NOW,
                expires_at=NOW + timedelta(hours=24),
                created_at=NOW,
                updated_at=NOW,
            )
        )
        for sequence_no, media_id in enumerate(media_ids):
            session.add(
                RemoteMedia(
                    id=media_id,
                    cache_job_id=job_id,
                    file_id=f"media-file-{sequence_no}",
                    pickcode=f"fixture-pickcode-{sequence_no}",
                    parent_cid="task",
                    name=f"fixture.part{sequence_no + 1}.mkv",
                    size_bytes=300_000_000,
                    duration_seconds=1200,
                    candidate_id=uuid.uuid4(),
                    sequence_no=sequence_no,
                    selection_score=100,
                    selection_evidence=[],
                    is_valid=True,
                    created_at=NOW,
                )
            )
        session.flush()
        for sequence_no, media_id in enumerate(media_ids):
            session.add(
                CacheJobMediaSelection(
                    cache_job_id=job_id,
                    sequence_no=sequence_no,
                    media_id=media_id,
                )
            )
    return job_id, media_ids


def _assert_database_does_not_contain(
    factory: sessionmaker, sensitive_value: str
) -> None:
    with factory() as session:
        columns = session.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND udt_name IN ('varchar', 'text', 'json', 'jsonb', 'bpchar')"
            )
        ).all()
        preparer = session.bind.dialect.identifier_preparer
        for table_name, column_name in columns:
            table = preparer.quote(table_name)
            column = preparer.quote(column_name)
            found = session.scalar(
                text(
                    f"SELECT 1 FROM {table} "
                    f"WHERE CAST({column} AS text) LIKE :needle LIMIT 1"
                ),
                {"needle": f"%{sensitive_value}%"},
            )
            assert found is None, f"short-lived URL persisted in {table}.{column}"


def _source_row() -> dict[str, object]:
    return {
        "website": "sehuatang",
        "tid": 108,
        "magnet": "task108-source-fixture",
        "title": "IPX-108",
        "number": "IPX-108",
        "size": 1024,
        "publish_date": date(2026, 7, 28),
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/thread-task108.htm",
        "section": "亚洲有码",
        "category": None,
        "create_time": NOW,
        "update_time": NOW,
    }
