from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.cloud_cache.models import RemoteSubtitle
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    DirectoryBreadcrumb,
    DirectoryInfo,
    OriginalUrl,
    RemoteFile,
)
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.service import AuthService
from sakuraplayer.playback.hls import HlsStreamResolver
from sakuraplayer.playback.original import OriginalStreamResolver
from sakuraplayer.playback.resolver import PlaybackStreamResolver
from sakuraplayer.playback.session import PlaybackSessionService
from sakuraplayer.playback.subtitles import MAX_SUBTITLE_BYTES, SubtitleDownloadService
from sakuraplayer.playback.user_agents import WINDOWS_USER_AGENT
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.shared.migration import upgrade_database
from tests.fakes.cloud115 import FakeCloud115
from tests.integration.playback.test_original_redirect import (
    BOOTSTRAP_TOKEN,
    NOW,
    CloudScopeStub,
    _bootstrap,
    _seed_binding,
    _seed_ready_media,
    _source_row,
)

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class SubtitleScopeStub:
    def __init__(self, fake: FakeCloud115) -> None:
        self.fake = fake

    @asynccontextmanager
    async def cache_operation_scope(self, **_kwargs: object):
        yield self.fake


@pytest.fixture
def database_url() -> Iterator[str]:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task110_subtitle_{uuid.uuid4().hex}"
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


def test_authenticated_subtitle_download_has_safe_headers_and_preserves_bytes(
    database_url: str,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    body = b"1\r\n00:00:00,000 --> 00:00:01,000\r\nfixture\xff\r\n"
    fake = _owned_fake(body=body)
    auth, source_cipher = _services(factory)
    SourceImporter(factory, cipher=source_cipher, now=lambda: NOW).import_batch(
        "task110-fixture.zip", (_source_row(),)
    )
    binding_id = _seed_binding(factory, source_cipher)
    scope = SubtitleScopeStub(fake)
    session_service = PlaybackSessionService(
        factory, signing_key=b"p" * 32, now=lambda: NOW
    )
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        playback_session_service=session_service,
        playback_stream_resolver=PlaybackStreamResolver(
            OriginalStreamResolver(CloudScopeStub(FakeCloud115())),  # type: ignore[arg-type]
            HlsStreamResolver(CloudScopeStub(FakeCloud115())),  # type: ignore[arg-type]
        ),
        subtitle_download_service=SubtitleDownloadService(
            factory,
            scope,
            now=lambda: NOW,  # type: ignore[arg-type]
        ),
    )
    client_instance_id = uuid.uuid4()
    try:
        with TestClient(app) as client:
            headers = _bootstrap(client, client_instance_id)
            job_id, media_ids = _seed_ready_media(factory, binding_id)
            subtitle_id = _seed_subtitle(factory, job_id, None)
            manifest_response = client.post(
                f"/api/v1/cache-jobs/{job_id}/playback-sessions",
                headers=headers,
                json={
                    "media_id": str(media_ids[1]),
                    "mode": "original",
                    "platform": "windows",
                    "client_instance_id": str(client_instance_id),
                },
            )
            assert manifest_response.status_code == 201
            manifest = manifest_response.json()
            assert manifest["cache_job_id"] == str(job_id)
            assert manifest["embedded_tracks_source"] == "client_player"
            assert manifest["subtitle_cache_expires_at"] == manifest["expires_at"]
            option = manifest["subtitles"][0]
            assert option["media_id"] is None
            assert option["selected_by_default"] is False

            unauthorized = client.get(
                f"/api/v1/playback/sessions/{manifest['session_id']}/subtitles/{subtitle_id}"
            )
            downloaded = client.get(
                f"/api/v1/playback/sessions/{manifest['media_queue'][0]['session_id']}/subtitles/{subtitle_id}",
                headers=headers,
            )
    finally:
        engine.dispose()

    assert unauthorized.status_code == 401
    assert downloaded.status_code == 200
    assert downloaded.content == body
    assert downloaded.headers["content-type"] == "application/x-subrip"
    assert downloaded.headers["content-disposition"] == (
        f'attachment; filename="{subtitle_id}.srt"'
    )
    assert downloaded.headers["cache-control"] == "no-store"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert [call.operation for call in fake.calls] == [
        "directory_info",
        "directory_info",
        "list_files_recursive",
        "download_small_file",
    ]
    assert fake.calls[-1].safe_arguments[-1] == str(MAX_SUBTITLE_BYTES)


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_code"),
    [
        ("wrong_media_session", 404, "subtitle_not_found"),
        ("root_moved", 404, "subtitle_not_found"),
        ("task_moved", 404, "subtitle_not_found"),
        ("remote_missing", 404, "subtitle_not_found"),
        ("remote_too_large", 413, "subtitle_too_large"),
    ],
)
def test_subtitle_failures_are_isolated_and_do_not_revoke_video_session(
    database_url: str, case: str, expected_status: int, expected_code: str
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    fake = _owned_fake(
        root_parent="outside-top-level" if case == "root_moved" else "0",
        task_parent="outside-root" if case == "task_moved" else "root",
        remote_missing=case == "remote_missing",
        remote_size=MAX_SUBTITLE_BYTES + 1 if case == "remote_too_large" else 128,
    )
    auth, source_cipher = _services(factory)
    SourceImporter(factory, cipher=source_cipher, now=lambda: NOW).import_batch(
        f"task110-{case}.zip", (_source_row(),)
    )
    binding_id = _seed_binding(factory, source_cipher)
    scope = SubtitleScopeStub(fake)
    video_fake = FakeCloud115(original_urls=[_original_url()])
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        playback_session_service=PlaybackSessionService(
            factory, signing_key=b"p" * 32, now=lambda: NOW
        ),
        playback_stream_resolver=PlaybackStreamResolver(
            OriginalStreamResolver(CloudScopeStub(video_fake)),  # type: ignore[arg-type]
            HlsStreamResolver(CloudScopeStub(FakeCloud115())),  # type: ignore[arg-type]
        ),
        subtitle_download_service=SubtitleDownloadService(
            factory,
            scope,
            now=lambda: NOW,  # type: ignore[arg-type]
        ),
    )
    client_instance_id = uuid.uuid4()
    try:
        with TestClient(app) as client:
            headers = _bootstrap(client, client_instance_id)
            job_id, media_ids = _seed_ready_media(factory, binding_id)
            subtitle_id = _seed_subtitle(factory, job_id, media_ids[1])
            manifest = client.post(
                f"/api/v1/cache-jobs/{job_id}/playback-sessions",
                headers=headers,
                json={
                    "media_id": str(media_ids[1]),
                    "mode": "original",
                    "platform": "windows",
                    "client_instance_id": str(client_instance_id),
                },
            ).json()
            session_id = (
                manifest["media_queue"][0]["session_id"]
                if case == "wrong_media_session"
                else manifest["session_id"]
            )
            failed = client.get(
                f"/api/v1/playback/sessions/{session_id}/subtitles/{subtitle_id}",
                headers=headers,
            )
            assert failed.status_code == expected_status
            assert failed.json()["code"] == expected_code
            video = client.get(
                manifest["stream_url"],
                headers={"User-Agent": WINDOWS_USER_AGENT},
                follow_redirects=False,
            )
            assert video.status_code == 302
            assert video.headers["location"] == "https://cdn.115.com/video"
            with factory() as session:
                assert (
                    session.scalar(
                        text(
                            "SELECT count(*) FROM playback_session "
                            "WHERE id = :id AND revoked_at IS NULL"
                        ),
                        {"id": uuid.UUID(manifest["session_id"])},
                    )
                    == 1
                )
    finally:
        engine.dispose()


def test_logout_epoch_prevents_new_login_from_using_old_subtitle_session(
    database_url: str,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    auth, source_cipher = _services(factory)
    SourceImporter(factory, cipher=source_cipher, now=lambda: NOW).import_batch(
        "task110-logout.zip", (_source_row(),)
    )
    binding_id = _seed_binding(factory, source_cipher)
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        playback_session_service=PlaybackSessionService(
            factory, signing_key=b"p" * 32, now=lambda: NOW
        ),
        playback_stream_resolver=PlaybackStreamResolver(
            OriginalStreamResolver(CloudScopeStub(FakeCloud115())),  # type: ignore[arg-type]
            HlsStreamResolver(CloudScopeStub(FakeCloud115())),  # type: ignore[arg-type]
        ),
        subtitle_download_service=SubtitleDownloadService(
            factory,
            SubtitleScopeStub(_owned_fake()),
            now=lambda: NOW,  # type: ignore[arg-type]
        ),
    )
    first_client_id = uuid.uuid4()
    second_client_id = uuid.uuid4()
    try:
        with TestClient(app) as client:
            old_headers = _bootstrap(client, first_client_id)
            job_id, media_ids = _seed_ready_media(factory, binding_id)
            subtitle_id = _seed_subtitle(factory, job_id, media_ids[1])
            manifest = client.post(
                f"/api/v1/cache-jobs/{job_id}/playback-sessions",
                headers=old_headers,
                json={
                    "media_id": str(media_ids[1]),
                    "mode": "original",
                    "platform": "windows",
                    "client_instance_id": str(first_client_id),
                },
            ).json()
            assert (
                client.post("/api/v1/auth/logout", headers=old_headers).status_code
                == 204
            )
            login = client.post(
                "/api/v1/auth/login",
                json={
                    "username": "admin",
                    "password": "correct horse battery staple",
                    "client_instance_id": str(second_client_id),
                },
            )
            assert login.status_code == 200
            new_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            denied = client.get(
                f"/api/v1/playback/sessions/{manifest['session_id']}/subtitles/{subtitle_id}",
                headers=new_headers,
            )
    finally:
        engine.dispose()

    assert denied.status_code == 404
    assert denied.json()["code"] == "subtitle_not_found"


def test_cloud_failures_keep_stable_codes_and_retry_after(database_url: str) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    problems = [
        Cloud115Problem("cloud115_credentials_expired"),
        Cloud115Problem("cloud115_rate_limited", retry_after_seconds=17),
        Cloud115Problem("cloud115_unavailable"),
        Cloud115Problem("cloud115_protocol_error"),
    ]
    fake = FakeCloud115(
        directory_infos=[item for _ in problems for item in _owned_directories()],
        file_batches=[_owned_files() for _ in problems],
        small_files=problems,
    )
    auth, source_cipher = _services(factory)
    SourceImporter(factory, cipher=source_cipher, now=lambda: NOW).import_batch(
        "task110-cloud-errors.zip", (_source_row(),)
    )
    binding_id = _seed_binding(factory, source_cipher)
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=auth,
        playback_session_service=PlaybackSessionService(
            factory, signing_key=b"p" * 32, now=lambda: NOW
        ),
        playback_stream_resolver=PlaybackStreamResolver(
            OriginalStreamResolver(CloudScopeStub(FakeCloud115())),  # type: ignore[arg-type]
            HlsStreamResolver(CloudScopeStub(FakeCloud115())),  # type: ignore[arg-type]
        ),
        subtitle_download_service=SubtitleDownloadService(
            factory,
            SubtitleScopeStub(fake),
            now=lambda: NOW,  # type: ignore[arg-type]
        ),
    )
    client_instance_id = uuid.uuid4()
    try:
        with TestClient(app) as client:
            headers = _bootstrap(client, client_instance_id)
            job_id, media_ids = _seed_ready_media(factory, binding_id)
            subtitle_id = _seed_subtitle(factory, job_id, media_ids[1])
            manifest = client.post(
                f"/api/v1/cache-jobs/{job_id}/playback-sessions",
                headers=headers,
                json={
                    "media_id": str(media_ids[1]),
                    "mode": "original",
                    "platform": "windows",
                    "client_instance_id": str(client_instance_id),
                },
            ).json()
            results = [
                client.get(
                    f"/api/v1/playback/sessions/{manifest['session_id']}/subtitles/{subtitle_id}",
                    headers=headers,
                )
                for _ in problems
            ]
    finally:
        engine.dispose()

    assert [(item.status_code, item.json()["code"]) for item in results] == [
        (422, "cloud115_credentials_expired"),
        (429, "cloud115_rate_limited"),
        (503, "cloud115_unavailable"),
        (502, "cloud115_protocol_error"),
    ]
    assert results[1].headers["retry-after"] == "17"


def _services(factory: sessionmaker) -> tuple[AuthService, SecretCipher]:
    auth = AuthService(
        session_factory=factory,
        token_key=b"t" * 32,
        bootstrap_token=BOOTSTRAP_TOKEN,
        now=lambda: NOW,
    )
    cipher = SecretCipher(
        InMemorySecretKeyProvider(active_key_id="test-v1", keys={"test-v1": b"s" * 32})
    )
    return auth, cipher


def _seed_subtitle(
    factory: sessionmaker, job_id: uuid.UUID, media_id: uuid.UUID | None
) -> uuid.UUID:
    subtitle_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(
            RemoteSubtitle(
                id=subtitle_id,
                cache_job_id=job_id,
                media_id=media_id,
                file_id="subtitle-file",
                pickcode="subtitle-pickcode",
                parent_cid="task",
                name="fixture.part2.srt",
                extension="srt",
                size_bytes=128,
                match_score=110,
                match_evidence=["exact_stem", "same_parent"],
                created_at=NOW,
            )
        )
    return subtitle_id


def _owned_fake(
    *,
    body: bytes = b"fixture",
    root_parent: str = "0",
    task_parent: str = "root",
    remote_missing: bool = False,
    remote_size: int = 128,
) -> FakeCloud115:
    return FakeCloud115(
        directory_infos=_owned_directories(
            root_parent=root_parent, task_parent=task_parent
        ),
        file_batches=[() if remote_missing else _owned_files(remote_size=remote_size)],
        small_files=[body],
    )


def _owned_directories(
    *, root_parent: str = "0", task_parent: str = "root"
) -> tuple[DirectoryInfo, ...]:
    return (
        DirectoryInfo(
            cid="root",
            parent_cid=root_parent,
            name="SakuraPlayer-Cache",
            path=(DirectoryBreadcrumb(cid="root", name="SakuraPlayer-Cache"),),
        ),
        DirectoryInfo(
            cid="task",
            parent_cid=task_parent,
            name="cache-task",
            path=(
                DirectoryBreadcrumb(cid="root", name="SakuraPlayer-Cache"),
                DirectoryBreadcrumb(cid="task", name="cache-task"),
            ),
        ),
    )


def _owned_files(*, remote_size: int = 128) -> tuple[RemoteFile, ...]:
    return (
        RemoteFile(
            file_id="subtitle-file",
            parent_cid="task",
            name="fixture.part2.srt",
            size_bytes=remote_size,
            pickcode="subtitle-pickcode",
            sha1=None,
            is_directory=False,
            is_video=False,
        ),
    )


def _original_url() -> OriginalUrl:
    return OriginalUrl(
        url="https://cdn.115.com/video",
        expires_at=NOW + timedelta(hours=1),
        file_id="media-file-1",
        file_name="fixture.part2.mkv",
        file_size_bytes=300_000_000,
        sha1="a" * 40,
        pickcode="fixture-pickcode-1",
        user_agent=WINDOWS_USER_AGENT,
    )
