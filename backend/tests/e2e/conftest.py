from __future__ import annotations

import base64
import io
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path
from typing import Iterator
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.api.diagnostics import DiagnosticsService
from sakuraplayer.api.settings import SettingsService
from sakuraplayer.catalog.metadata_api import MetadataAdminService
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.providers.javdb import EncryptedJavdbCredentialStore
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.catalog.translation.config import EncryptedAiConfigurationStore
from sakuraplayer.discovery.favorites import FavoriteService
from sakuraplayer.discovery.ranking_query import RankingQueryService
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.events.outbox import DomainEventWriter, EventLog
from sakuraplayer.events.snapshot import EventSnapshotService
from sakuraplayer.identity.crypto import (
    InMemorySecretKeyProvider,
    SecretCipher,
    SettingsSecretKeyProvider,
)
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.identity.service import AuthService
from sakuraplayer.resources.avdb_crypto import decrypt_asset
from sakuraplayer.resources.avdb_release import FetchedAsset, FetchedRelease
from sakuraplayer.resources.rejection import SourceRejectionService
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.sync_service import AvdbSyncService
from sakuraplayer.shared.config import Settings
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
FIXTURES = BACKEND_ROOT / "tests" / "fixtures"
NOW = datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc)
BOOTSTRAP_TOKEN = b"task014-bootstrap-token-at-least-32-bytes"
_AVDB_KEY_MATERIAL = bytes.fromhex(
    "ca42e687df5818e2e88da0ff5b9fd2c60f7e22721f682b66c3e50485a00d06d5"
)


@dataclass
class E2eContext:
    client: TestClient
    database_url: str = field(repr=False)
    factory: sessionmaker[Session]
    queue: MetadataQueue
    source_importer: SourceImporter
    sync_service: AvdbSyncService
    rejection_service: SourceRejectionService

    def auth_headers(self) -> dict[str, str]:
        response = self.client.post(
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


@pytest.fixture
def database_url() -> Iterator[str]:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task014_{uuid.uuid4().hex}"
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
def e2e_context(database_url: str, tmp_path: Path) -> Iterator[E2eContext]:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    writer = DomainEventWriter(now=lambda: NOW)
    queue = MetadataQueue(factory, now=lambda: NOW, event_writer=writer)
    source_cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="task014-v1",
            keys={"task014-v1": b"m" * 32},
        )
    )
    source_importer = SourceImporter(factory, cipher=source_cipher, now=lambda: NOW)
    sync_service = AvdbSyncService(factory, batch_size=2, now=lambda: NOW)
    rejection_service = SourceRejectionService(factory, now=lambda: NOW)

    settings_repository = EncryptedSettingRepository(
        factory,
        SecretCipher(SettingsSecretKeyProvider(key_id="v1", key=b"s" * 32)),
        now=lambda: NOW,
    )
    settings_service = SettingsService(
        factory,
        settings_repository,
        EncryptedJavdbCredentialStore(settings_repository),
        EncryptedAiConfigurationStore(settings_repository),
        now=lambda: NOW,
    )
    favorites = FavoriteService(factory, now=lambda: NOW)
    catalog = CatalogQueryService(
        factory,
        favorite_port=favorites,
        image_root=tmp_path / "catalog-images",
    )
    event_log = EventLog(factory, now=lambda: NOW)
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        metadata_admin_service=MetadataAdminService(factory, queue),
        catalog_query_service=catalog,
        search_service=SearchService(catalog, queue),
        favorite_service=favorites,
        ranking_query_service=RankingQueryService(
            factory,
            catalog=catalog,
            completion=queue,
            credential_status=lambda: "not_configured",
            current_year=lambda: 2026,
        ),
        event_snapshot_service=EventSnapshotService(factory, event_log),
        event_log=event_log,
        settings_service=settings_service,
        diagnostics_service=DiagnosticsService(
            factory,
            settings_service,
            now=lambda: NOW,
        ),
    )
    with TestClient(app) as client:
        yield E2eContext(
            client=client,
            database_url=database_url,
            factory=factory,
            queue=queue,
            source_importer=source_importer,
            sync_service=sync_service,
            rejection_service=rejection_service,
        )
    engine.dispose()


def app_settings(database_url: str) -> Settings:
    return Settings(
        environment="test",
        database_url=database_url,
        log_level="INFO",
        publish_host="127.0.0.1",
        api_port=8000,
        trust_proxy_headers=False,
        settings_key_id="v1",
        settings_key=b"s" * 32,
        token_key=b"t" * 32,
        playback_key=b"p" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
    )


def fetched_release(tmp_path: Path, release_id: str) -> FetchedRelease:
    csv_content = (FIXTURES / "e2e" / "avdb-mixed.csv").read_bytes()
    payload = _encrypt_avdb_csv(csv_content)
    release_directory = tmp_path / release_id
    release_directory.mkdir(parents=True)
    asset_path = release_directory / "30D_202607270300.zip"
    asset_path.write_bytes(payload)
    return FetchedRelease(
        repository="fixture/task014",
        release_id=release_id,
        tag="task014",
        mode="incremental_30d",
        assets=(
            FetchedAsset(
                name=asset_path.name,
                path=asset_path,
                sha256=sha256(payload).hexdigest(),
                byte_size=len(payload),
                validation=decrypt_asset(payload),
            ),
        ),
    )


def fake_metadata_client(*, fail_optional: bool) -> httpx.Client:
    metadata_fixtures = FIXTURES / "metadata"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "javdb.com" and request.url.path == "/search":
            return httpx.Response(
                200,
                text=(metadata_fixtures / "javdb-search.html").read_text(
                    encoding="utf-8"
                ),
            )
        if request.url.host == "javdb.com":
            return httpx.Response(
                200,
                text=(metadata_fixtures / "javdb-detail.html").read_text(
                    encoding="utf-8"
                ),
            )
        if request.url.host == "www.dmm.co.jp":
            if fail_optional:
                return httpx.Response(503)
            return httpx.Response(
                200,
                text=(metadata_fixtures / "dmm-description.html").read_text(
                    encoding="utf-8"
                ),
            )
        if request.url.host == "c0.jdbstatic.com":
            if fail_optional:
                return httpx.Response(503)
            output = io.BytesIO()
            Image.new("RGB", (2, 2), color=(120, 30, 60)).save(output, format="PNG")
            return httpx.Response(
                200,
                headers={"Content-Type": "image/png"},
                content=output.getvalue(),
            )
        raise AssertionError(f"unexpected fake request host: {request.url.host}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def _encrypt_avdb_csv(csv_content: bytes) -> bytes:
    inner = io.BytesIO()
    with ZipFile(inner, "w", ZIP_DEFLATED) as archive:
        archive.writestr("resource.csv", csv_content)
    salt = b"s" * 16
    nonce = b"n" * 12
    iterations = 200_000
    key = pbkdf2_hmac(
        "sha256",
        _AVDB_KEY_MATERIAL,
        salt,
        iterations,
        dklen=32,
    )
    encrypted = AESGCM(key).encrypt(nonce, inner.getvalue(), None)
    manifest = {
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "tag": base64.b64encode(encrypted[-16:]).decode("ascii"),
        "iterations": iterations,
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "key_length": 32,
    }
    outer = io.BytesIO()
    with ZipFile(outer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("avdb-resource-library.json", json.dumps(manifest))
        archive.writestr("avdb-resource-library.bin", encrypted[:-16])
    return outer.getvalue()
