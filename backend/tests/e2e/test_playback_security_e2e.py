from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from conftest import (
    CloudE2eContext,
    app_settings,
    fake_metadata_client,
)
from sqlalchemy import select

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import MetadataStage
from sakuraplayer.catalog.providers.runtime import build_metadata_stage_executor
from sakuraplayer.cloud_cache.models import CacheJob
from sakuraplayer.cloud_cache.ports.cloud115 import (
    HlsInfo,
    HlsVariant,
    OriginalUrl,
    RemoteFile,
)
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.playback.user_agents import WINDOWS_USER_AGENT
from sakuraplayer.resources.models import Movie, ResourceSource
from sakuraplayer.worker.metadata_child import MetadataChildRunner

pytestmark = pytest.mark.integration
MIB = 1024 * 1024


@pytest.mark.parametrize(
    "ac_evidence",
    [pytest.param(None, id="AC-099-AC-102-AC-107-AC-110-AC-128-AC-129")],
)
def test_playback_signature_fallback_subtitle_and_secret_boundaries(
    cloud_e2e_context: CloudE2eContext,
    ac_evidence: None,
) -> None:
    del ac_evidence
    context = cloud_e2e_context
    headers = context.bootstrap_and_bind()
    ready = context.complete_cache_job(headers, files=_video_and_subtitle)
    job_id = uuid.UUID(ready["id"])
    media_id = ready["selected_media_ids"][0]
    subtitle_id = ready["subtitles"][0]["id"]
    context.fake.inject_fault(
        "resolve_original",
        _cloud_problem("cloud115_original_unavailable"),
    )
    context.fake.seed_hls(_hls())
    context.fake.seed_small_file("security-subtitle-pickcode", b"private subtitle")

    manifest = _create_session(context, headers, job_id, media_id, mode="original")
    wrong_ua = context.client.get(
        manifest["stream_url"],
        headers={"User-Agent": "not-sakuraplayer"},
        follow_redirects=False,
    )
    assert wrong_ua.status_code == 403
    assert wrong_ua.json()["code"] == "playback_user_agent_mismatch"
    tampered_url = manifest["stream_url"][:-1] + (
        "0" if manifest["stream_url"][-1] != "0" else "1"
    )
    tampered = context.client.get(
        tampered_url,
        headers={"User-Agent": WINDOWS_USER_AGENT},
        follow_redirects=False,
    )
    assert tampered.status_code == 401
    assert tampered.json()["code"] == "playback_signature_invalid"
    fallback = context.client.get(
        manifest["stream_url"],
        headers={"User-Agent": WINDOWS_USER_AGENT},
        follow_redirects=False,
    )
    assert fallback.status_code == 302
    assert fallback.headers["location"].endswith("high.m3u8?capability=private")

    compatibility = _create_session(
        context,
        headers,
        job_id,
        media_id,
        mode="compatibility",
    )
    compatible_stream = context.client.get(
        compatibility["stream_url"],
        headers={"User-Agent": WINDOWS_USER_AGENT},
        follow_redirects=False,
    )
    assert compatible_stream.status_code == 302
    operations = [call.operation for call in context.fake.calls]
    assert operations.count("resolve_original") == 1
    assert operations.count("resolve_hls") == 2

    subtitle = context.client.get(
        f"/api/v1/playback/sessions/{manifest['session_id']}/subtitles/{subtitle_id}",
        headers=headers,
    )
    assert subtitle.status_code == 200
    with context.factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None and job.task_dir_cid is not None
        task_dir_cid = job.task_dir_cid
    context.fake.move_directory(task_dir_cid, "outside-cid")
    detached_subtitle = context.client.get(
        f"/api/v1/playback/sessions/{manifest['session_id']}/subtitles/{subtitle_id}",
        headers=headers,
    )
    assert detached_subtitle.status_code == 404
    assert detached_subtitle.json()["code"] == "subtitle_not_found"

    with context.factory() as session:
        persisted = repr(list(session.scalars(select(DomainEvent))))
    printable = persisted + repr(context.fake) + repr(context.fake.calls)
    for secret in (
        "UID=task113-private",
        "magnet:?xt=urn:btih:task113-private",
        "capability=private",
        "private subtitle",
    ):
        assert secret not in printable


@pytest.mark.parametrize("ac_evidence", [pytest.param(None, id="AC-132")])
def test_optional_metadata_failures_do_not_block_cloud115_playback(
    cloud_e2e_context: CloudE2eContext,
    tmp_path: Path,
    ac_evidence: None,
) -> None:
    del ac_evidence
    context = cloud_e2e_context
    headers = context.bootstrap_and_bind()
    with context.factory.begin() as session:
        movie = session.get(Movie, context.movie_ids[4])
        source = session.get(ResourceSource, context.source_ids[4])
        assert movie is not None and source is not None
        movie.normalized_number = "ABP-123"
        movie.raw_numbers = ["ABP-123"]
        source.normalized_number = "ABP-123"
        source.raw_number = "ABP-123"
    queue = MetadataQueue(context.factory, now=context.clock.now)
    queued = queue.enqueue(
        movie_id=context.movie_ids[4],
        normalized_number="ABP-123",
        sort_date=date(2026, 7, 29),
        reason="manual_or_search",
    )
    claim = queue.claim_next("task113-metadata", lease_duration=timedelta(seconds=30))
    assert claim is not None
    http_client = fake_metadata_client(fail_optional=True)
    try:
        executor = build_metadata_stage_executor(
            settings=app_settings(context.database_url),
            session_factory=context.factory,
            http_client=http_client,
            image_root=tmp_path / "catalog-images",
            now=context.clock.now,
        )
        result = MetadataChildRunner(queue=queue, executor=executor).run(claim)
    finally:
        http_client.close()
    assert result == "completed_with_warnings"
    with context.factory() as session:
        warnings = list(
            session.scalars(
                select(MetadataStage).where(
                    MetadataStage.job_id == queued.job_id,
                    MetadataStage.status == "warning",
                )
            )
        )
        assert warnings

    ready = context.complete_cache_job(headers, index=4, files=_video_with_subtitle)
    context.fake.seed_original(
        OriginalUrl(
            url="https://video.115cdn.com/ac132.mp4?capability=fixture",
            expires_at=context.clock.now() + timedelta(hours=1),
            file_id="ac132-video",
            file_name="E2E-005.mp4",
            file_size_bytes=600 * MIB,
            sha1="e" * 40,
            pickcode="ac132-video-pickcode",
            user_agent=WINDOWS_USER_AGENT,
        )
    )
    context.fake.seed_small_file("ac132-subtitle-pickcode", b"AC-132 subtitle")
    manifest = _create_session(
        context,
        headers,
        uuid.UUID(ready["id"]),
        ready["selected_media_ids"][0],
        mode="original",
    )
    stream = context.client.get(
        manifest["stream_url"],
        headers={"User-Agent": WINDOWS_USER_AGENT},
        follow_redirects=False,
    )
    assert stream.status_code == 302
    subtitle = context.client.get(
        f"/api/v1/playback/sessions/{manifest['session_id']}/subtitles/"
        f"{ready['subtitles'][0]['id']}",
        headers=headers,
    )
    assert subtitle.status_code == 200
    heartbeat = context.client.put(
        f"/api/v1/playback/sessions/{manifest['session_id']}/heartbeat",
        headers=headers,
        json={
            "client_instance_id": str(context.client_instance_id),
            "progress": {
                "position_seconds": 60,
                "duration_seconds": 3600,
                "version": 0,
            },
            "playing": False,
        },
    )
    assert heartbeat.status_code == 200
    cleanup = context.client.post(
        f"/api/v1/cache-jobs/{ready['id']}/cleanup",
        headers=headers,
    )
    assert cleanup.status_code == 202
    assert context.pipeline.run_once(worker_id="task113-ac132-cleanup") == "worked"
    cleaned = context.client.get(
        f"/api/v1/cache-jobs/{ready['id']}",
        headers=headers,
    )
    assert cleaned.status_code == 200
    assert cleaned.json()["status"] == "cleaned"


def _create_session(
    context: CloudE2eContext,
    headers: dict[str, str],
    job_id: uuid.UUID,
    media_id: str,
    *,
    mode: str,
) -> dict[str, object]:
    response = context.client.post(
        f"/api/v1/cache-jobs/{job_id}/playback-sessions",
        headers=headers,
        json={
            "media_id": media_id,
            "mode": mode,
            "platform": "windows",
            "client_instance_id": str(context.client_instance_id),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _hls() -> HlsInfo:
    return HlsInfo(
        pickcode="security-video-pickcode",
        variants=(
            HlsVariant(
                url="https://video.115cdn.com/low.m3u8?capability=private",
                bandwidth=500_000,
                resolution="1280x720",
                label="720p",
                user_agent=WINDOWS_USER_AGENT,
            ),
            HlsVariant(
                url="https://video.115cdn.com/high.m3u8?capability=private",
                bandwidth=1_000_000,
                resolution="1920x1080",
                label="1080p",
                user_agent=WINDOWS_USER_AGENT,
            ),
        ),
    )


def _video_and_subtitle(task_dir_cid: str) -> tuple[RemoteFile, ...]:
    return (
        RemoteFile(
            file_id="security-video",
            parent_cid=task_dir_cid,
            name="E2E-001.mp4",
            size_bytes=600 * MIB,
            pickcode="security-video-pickcode",
            sha1="f" * 40,
            is_directory=False,
            is_video=True,
            duration_seconds=3600,
        ),
        RemoteFile(
            file_id="security-subtitle",
            parent_cid=task_dir_cid,
            name="E2E-001.ass",
            size_bytes=1024,
            pickcode="security-subtitle-pickcode",
            sha1="1" * 40,
            is_directory=False,
            is_video=False,
        ),
    )


def _video_with_subtitle(task_dir_cid: str) -> tuple[RemoteFile, ...]:
    return (
        RemoteFile(
            file_id="ac132-video",
            parent_cid=task_dir_cid,
            name="ABP-123.mp4",
            size_bytes=600 * MIB,
            pickcode="ac132-video-pickcode",
            sha1="e" * 40,
            is_directory=False,
            is_video=True,
            duration_seconds=3600,
        ),
        RemoteFile(
            file_id="ac132-subtitle",
            parent_cid=task_dir_cid,
            name="ABP-123.srt",
            size_bytes=1024,
            pickcode="ac132-subtitle-pickcode",
            sha1="d" * 40,
            is_directory=False,
            is_video=False,
        ),
    )


def _cloud_problem(code: str):
    from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem

    return Cloud115Problem(code)
