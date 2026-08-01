from __future__ import annotations

import base64
import io
import json
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path
from typing import AsyncIterator, Callable, Iterator
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select, text
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
from sakuraplayer.cloud_cache.binding_service import BindingService
from sakuraplayer.cloud_cache.cancellation import CancellationService
from sakuraplayer.cloud_cache.capacity import active_cache_jobs
from sakuraplayer.cloud_cache.cleanup import CleanupClaim, CleanupQueue, CleanupWorker
from sakuraplayer.cloud_cache.events import CacheEventPublisher
from sakuraplayer.cloud_cache.models import CacheJob
from sakuraplayer.cloud_cache.notifications import (
    NotificationService,
    NotificationWriter,
)
from sakuraplayer.cloud_cache.play_request import PlayRequestService
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Port,
    OfflineStatus,
    QrLoginResult,
    QrSession,
    QrStatus,
    QrToken,
    RemoteFile,
)
from sakuraplayer.cloud_cache.qr_service import QrSessionService
from sakuraplayer.cloud_cache.snapshot import CacheSnapshotExtension
from sakuraplayer.cloud_cache.source_rejection_client import SourceRejectionClient
from sakuraplayer.cloud_cache.worker.claim import CacheJobClaim, CacheJobClaimQueue
from sakuraplayer.cloud_cache.worker.offline import CacheOfflineWorker
from sakuraplayer.cloud_cache.worker.resolution import (
    CacheMediaResolver,
    CacheWorkerPipeline,
)
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
from sakuraplayer.playback.heartbeat import PlaybackHeartbeatService
from sakuraplayer.playback.hls import HlsStreamResolver
from sakuraplayer.playback.original import OriginalStreamResolver
from sakuraplayer.playback.progress import MoviePlaybackStateService
from sakuraplayer.playback.resolver import PlaybackStreamResolver
from sakuraplayer.playback.session import PlaybackSessionService
from sakuraplayer.playback.subtitles import SubtitleDownloadService
from sakuraplayer.resources.avdb_crypto import decrypt_asset
from sakuraplayer.resources.avdb_release import FetchedAsset, FetchedRelease
from sakuraplayer.resources.models import Movie, ResourceSource
from sakuraplayer.resources.rejection import SourceRejectionService
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import SourceSubmissionService
from sakuraplayer.resources.sync_service import AvdbSyncService
from sakuraplayer.shared.config import Settings
from sakuraplayer.shared.migration import upgrade_database
from tests.fakes.cloud115_state import StatefulFakeCloud115

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


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


@dataclass
class CloudE2eContext:
    client: TestClient
    database_url: str = field(repr=False)
    factory: sessionmaker[Session]
    fake: StatefulFakeCloud115 = field(repr=False)
    pipeline: CacheWorkerPipeline
    claim_queue: CacheJobClaimQueue
    cleanup_queue: CleanupQueue
    clock: MutableClock
    movie_ids: tuple[uuid.UUID, ...]
    source_ids: tuple[uuid.UUID, ...]
    client_instance_id: uuid.UUID

    def bootstrap_and_bind(self) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN.decode("ascii")},
            json={
                "username": "admin",
                "password": "correct horse battery staple",
                "client_instance_id": str(self.client_instance_id),
            },
        )
        assert response.status_code == 201
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        qr = self.client.post("/api/v1/cloud115/qr-sessions", headers=headers)
        assert qr.status_code == 201
        bound = self.client.post(
            f"/api/v1/cloud115/qr-sessions/{qr.json()['id']}/confirm",
            headers=headers,
        )
        assert bound.status_code == 200
        assert bound.json()["status"] == "active"
        return headers

    def login(self, client_instance_id: uuid.UUID) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "correct horse battery staple",
                "client_instance_id": str(client_instance_id),
            },
        )
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def create_play_request(
        self,
        headers: dict[str, str],
        *,
        index: int = 0,
    ) -> dict[str, object]:
        response = self.client.post(
            f"/api/v1/movies/{self.movie_ids[index]}/play-requests",
            headers={
                **headers,
                "Idempotency-Key": f"task113-play-request-{index}",
            },
            json={"source_id": str(self.source_ids[index])},
        )
        assert response.status_code in {200, 202}, response.text
        return response.json()

    def complete_cache_job(
        self,
        headers: dict[str, str],
        *,
        index: int = 0,
        files: Callable[[str], tuple[RemoteFile, ...]],
        expected_status: str = "ready",
    ) -> dict[str, object]:
        created = self.create_play_request(headers, index=index)
        job_id = uuid.UUID(str(created["cache_job"]["id"]))  # type: ignore[index]
        assert self.pipeline.run_once(worker_id=f"task113-submit-{index}") == "worked"
        with self.factory() as session:
            job = session.get(CacheJob, job_id)
            assert job is not None
            assert job.status == "offlining"
            assert job.task_dir_cid is not None
            assert job.remote_info_hash is not None
            task_dir_cid = job.task_dir_cid
            info_hash = job.remote_info_hash
        self.fake.seed_files(task_dir_cid, files(task_dir_cid))
        self.fake.set_offline_status(
            info_hash,
            OfflineStatus.COMPLETED,
            percent_done=100.0,
        )
        assert self.pipeline.run_once(worker_id=f"task113-resolve-{index}") == "worked"
        response = self.client.get(f"/api/v1/cache-jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] == expected_status
        return response.json()


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


@pytest.fixture
def cloud_e2e_context(database_url: str) -> Iterator[CloudE2eContext]:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    clock = MutableClock(datetime(2026, 7, 29, 8, 0, tzinfo=timezone.utc))
    writer = DomainEventWriter(now=clock.now)
    event_log = EventLog(factory, now=clock.now)
    cache_events = CacheEventPublisher(
        writer,
        NotificationWriter(writer, now=clock.now),
    )
    cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="task113-v1",
            keys={"task113-v1": b"c" * 32},
        )
    )
    secrets = EncryptedSettingRepository(factory, cipher, now=clock.now)
    fake = StatefulFakeCloud115(cookie_snapshot="UID=task113-private")
    token = QrToken(uid="task113-qr-uid", time=1, sign="task113-sign")
    fake.queue_qr_session(QrSession(token, b"task113-png"))
    fake.queue_qr_status(QrStatus.CONFIRMED)
    fake.queue_qr_result(
        QrLoginResult(
            account_key="task113-account",
            cookie_snapshot="UID=task113-private",
        )
    )

    @asynccontextmanager
    async def cloud_scope(_cookies: str | None) -> AsyncIterator[StatefulFakeCloud115]:
        yield fake

    binding = BindingService(
        factory,
        secrets,
        cloud_scope,
        active_cache_jobs=active_cache_jobs,
        now=clock.now,
        event_publisher=cache_events,
    )
    qr = QrSessionService(cloud_scope, now=clock.now)
    source_importer = SourceImporter(factory, cipher=cipher, now=clock.now)
    source_importer.import_batch(
        "task113-fixture.zip",
        tuple(_cloud_source_row(index) for index in range(1, 14)),
    )
    with factory.begin() as session:
        sources = list(
            session.scalars(
                select(ResourceSource).order_by(ResourceSource.external_post_id)
            )
        )
        movies = [session.get(Movie, source.movie_id) for source in sources]
        assert all(movie is not None for movie in movies)
        for movie in movies:
            assert movie is not None
            movie.catalog_state = "core_ready"
            movie.updated_at = clock.now()
    movie_ids = tuple(movie.id for movie in movies if movie is not None)
    source_ids = tuple(source.id for source in sources)

    source_submission = SourceSubmissionService(factory, cipher=cipher)
    rejection = SourceRejectionClient(
        source_submission,
        SourceRejectionService(factory, now=clock.now),
    )
    play_requests = PlayRequestService(
        factory,
        source_submission,
        now=clock.now,
        ttl_hours=lambda: 24,
        event_publisher=cache_events,
    )
    claim_queue = CacheJobClaimQueue(
        factory,
        now=clock.now,
        ttl_hours=lambda: 24,
        event_publisher=cache_events,
    )
    cleanup_queue = CleanupQueue(
        factory,
        now=clock.now,
        event_publisher=cache_events,
    )

    @asynccontextmanager
    async def cache_cloud_scope(
        claim: CacheJobClaim,
    ) -> AsyncIterator[Cloud115Port]:
        async with binding.cache_operation_scope(
            binding_id=claim.binding_id,
            account_key=claim.account_key,
            cache_root_cid=claim.cache_root_cid,
        ) as cloud:
            yield cloud

    @asynccontextmanager
    async def cleanup_cloud_scope(
        claim: CleanupClaim,
    ) -> AsyncIterator[Cloud115Port]:
        async with binding.cache_operation_scope(
            binding_id=claim.binding_id,
            account_key=claim.account_key,
            cache_root_cid=claim.cache_root_cid,
        ) as cloud:
            yield cloud

    pipeline = CacheWorkerPipeline(
        CacheOfflineWorker(
            claim_queue,
            source_submission,
            rejection,
            cache_cloud_scope,
            now=clock.now,
        ),
        CacheMediaResolver(claim_queue, rejection, cache_cloud_scope),
        CleanupWorker(cleanup_queue, cleanup_cloud_scope),
    )
    progress = MoviePlaybackStateService(factory, now=clock.now)
    playback = PlaybackSessionService(
        factory,
        signing_key=b"p" * 32,
        now=clock.now,
        ttl_hours=lambda: 24,
        progress_service=progress,
    )
    heartbeat = PlaybackHeartbeatService(
        factory,
        progress_service=progress,
        now=clock.now,
        ttl_hours=lambda: 24,
    )
    resolver = PlaybackStreamResolver(
        OriginalStreamResolver(binding),
        HlsStreamResolver(binding),
    )
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=clock.now,
    )
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        event_snapshot_service=EventSnapshotService(
            factory,
            event_log,
            extension=CacheSnapshotExtension(),
        ),
        event_log=event_log,
        cloud115_binding_service=binding,
        cloud115_qr_service=qr,
        cache_service=play_requests,
        cache_cleanup_service=cleanup_queue,
        cache_cancellation_service=CancellationService(
            factory,
            now=clock.now,
            event_publisher=cache_events,
        ),
        notification_service=NotificationService(
            factory,
            event_writer=writer,
            now=clock.now,
        ),
        playback_session_service=playback,
        playback_stream_resolver=resolver,
        subtitle_download_service=SubtitleDownloadService(
            factory,
            binding,
            now=clock.now,
        ),
        playback_progress_service=progress,
        playback_heartbeat_service=heartbeat,
    )
    client_instance_id = uuid.uuid4()
    with TestClient(app) as client:
        yield CloudE2eContext(
            client=client,
            database_url=database_url,
            factory=factory,
            fake=fake,
            pipeline=pipeline,
            claim_queue=claim_queue,
            cleanup_queue=cleanup_queue,
            clock=clock,
            movie_ids=movie_ids,
            source_ids=source_ids,
            client_instance_id=client_instance_id,
        )
    engine.dispose()


def _cloud_source_row(index: int) -> dict[str, object]:
    return {
        "tid": 10_000 + index,
        "number": f"E2E-{index:03d}",
        "title": f"TASK-113 fixture {index}",
        "publish_date": date(2026, 7, 29),
        "magnet": f"magnet:?xt=urn:btih:task113-private-{index}",
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/task113.htm",
        "size": 1024,
        "section": "亚洲有码",
        "category": None,
        "website": "sehuatang",
        "create_time": NOW,
        "update_time": NOW,
    }


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
        if (
            request.url.host == "jdforrepam.com"
            and request.url.path == "/api/v2/search"
        ):
            return httpx.Response(
                200,
                text=(metadata_fixtures / "javdb-search.json").read_text(
                    encoding="utf-8"
                ),
            )
        if request.url.host == "jdforrepam.com" and request.url.path.startswith(
            "/api/v4/movies/"
        ):
            return httpx.Response(
                200,
                text=(metadata_fixtures / "javdb-detail.json").read_text(
                    encoding="utf-8"
                ),
            )
        if request.url.host == "www.dmm.co.jp":
            if fail_optional:
                return httpx.Response(503)
            return httpx.Response(
                200,
                text=(
                    metadata_fixtures
                    / (
                        "dmm-search.html"
                        if request.url.path.startswith("/search/")
                        else "dmm-mono-detail.html"
                    )
                ).read_text(encoding="utf-8"),
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
