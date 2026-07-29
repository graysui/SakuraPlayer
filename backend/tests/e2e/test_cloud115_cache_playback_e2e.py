from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from conftest import CloudE2eContext
from sqlalchemy import select

from sakuraplayer.cloud_cache.models import CacheJob, Notification
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    OriginalUrl,
    RemoteFile,
)
from sakuraplayer.cloud_cache.worker.claim import CacheJobClaimLost
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.playback.models import MoviePlaybackState, PlaybackSession
from sakuraplayer.playback.user_agents import WINDOWS_USER_AGENT
from sakuraplayer.resources.models import ResourceSource, SourceRejection

pytestmark = pytest.mark.integration
MIB = 1024 * 1024


@pytest.mark.parametrize(
    "ac_evidence",
    [
        pytest.param(
            None,
            id="AC-013-AC-017-AC-035-AC-079-AC-102-AC-107-AC-113-AC-115-AC-129",
        )
    ],
)
def test_cloud115_cache_playback_cleanup_chain(
    cloud_e2e_context: CloudE2eContext,
    ac_evidence: None,
) -> None:
    del ac_evidence
    context = cloud_e2e_context
    headers = context.bootstrap_and_bind()
    ready = context.complete_cache_job(headers, files=_single_video_with_subtitle)
    job_id = uuid.UUID(ready["id"])
    media_id = uuid.UUID(ready["selected_media_ids"][0])
    subtitle_id = uuid.UUID(ready["subtitles"][0]["id"])
    context.fake.seed_original(
        OriginalUrl(
            url="https://video.115cdn.com/task113.mp4?capability=fixture",
            expires_at=context.clock.now() + timedelta(hours=1),
            file_id="task113-video",
            file_name="E2E-001.mp4",
            file_size_bytes=600 * MIB,
            sha1="a" * 40,
            pickcode="task113-video-pickcode",
            user_agent=WINDOWS_USER_AGENT,
        )
    )
    context.fake.seed_small_file("task113-subtitle-pickcode", b"[Script Info]\n")

    playback = context.client.post(
        f"/api/v1/cache-jobs/{job_id}/playback-sessions",
        headers=headers,
        json={
            "media_id": str(media_id),
            "mode": "original",
            "platform": "windows",
            "client_instance_id": str(context.client_instance_id),
        },
    )
    assert playback.status_code == 201
    manifest = playback.json()
    assert manifest["required_user_agent"] == WINDOWS_USER_AGENT
    assert manifest["embedded_tracks_source"] == "client_player"
    assert manifest["subtitles"][0]["id"] == str(subtitle_id)
    with context.factory() as session:
        assert (
            session.get(PlaybackSession, uuid.UUID(manifest["session_id"])) is not None
        )

    stream = context.client.get(
        manifest["stream_url"],
        headers={"User-Agent": WINDOWS_USER_AGENT},
        follow_redirects=False,
    )
    assert stream.status_code == 302
    assert stream.headers["cache-control"] == "no-store"
    assert stream.headers["location"].startswith("https://video.115cdn.com/")

    subtitle = context.client.get(
        f"/api/v1/playback/sessions/{manifest['session_id']}/subtitles/{subtitle_id}",
        headers=headers,
    )
    assert subtitle.status_code == 200
    assert subtitle.content == b"[Script Info]\n"
    assert subtitle.headers["cache-control"] == "no-store"

    heartbeat = context.client.put(
        f"/api/v1/playback/sessions/{manifest['session_id']}/heartbeat",
        headers=headers,
        json={
            "client_instance_id": str(context.client_instance_id),
            "progress": {
                "position_seconds": 120,
                "duration_seconds": 3600,
                "version": 0,
            },
            "playing": True,
        },
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["progress"]["version"] == 1
    second_client_id = uuid.uuid4()
    second_headers = context.login(second_client_id)
    second_playback = context.client.post(
        f"/api/v1/cache-jobs/{job_id}/playback-sessions",
        headers=second_headers,
        json={
            "media_id": str(media_id),
            "mode": "original",
            "platform": "windows",
            "client_instance_id": str(second_client_id),
        },
    )
    assert second_playback.status_code == 201
    second_manifest = second_playback.json()
    second_heartbeat = context.client.put(
        f"/api/v1/playback/sessions/{second_manifest['session_id']}/heartbeat",
        headers=second_headers,
        json={
            "client_instance_id": str(second_client_id),
            "progress": {
                "position_seconds": 180,
                "duration_seconds": 3600,
                "version": 1,
            },
            "playing": True,
        },
    )
    assert second_heartbeat.status_code == 200
    assert second_heartbeat.json()["progress"]["version"] == 2
    stale = context.client.put(
        f"/api/v1/playback/sessions/{manifest['session_id']}/heartbeat",
        headers=headers,
        json={
            "client_instance_id": str(context.client_instance_id),
            "progress": {
                "position_seconds": 150,
                "duration_seconds": 3600,
                "version": 1,
            },
            "playing": True,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "progress_version_conflict"
    assert stale.json()["details"]["progress"]["version"] == 2
    stopped = context.client.put(
        f"/api/v1/playback/sessions/{manifest['session_id']}/heartbeat",
        headers=headers,
        json={
            "client_instance_id": str(context.client_instance_id),
            "playing": False,
        },
    )
    assert stopped.status_code == 200
    assert stopped.json()["lease_expires_at"] is None
    second_stopped = context.client.put(
        f"/api/v1/playback/sessions/{second_manifest['session_id']}/heartbeat",
        headers=second_headers,
        json={
            "client_instance_id": str(second_client_id),
            "playing": False,
        },
    )
    assert second_stopped.status_code == 200
    assert second_stopped.json()["lease_expires_at"] is None

    requested = context.client.post(
        f"/api/v1/cache-jobs/{job_id}/cleanup",
        headers=headers,
    )
    assert requested.status_code == 202
    assert requested.json()["status"] == "cleaning"
    assert context.pipeline.run_once(worker_id="task113-cleanup") == "worked"
    cleaned = context.client.get(f"/api/v1/cache-jobs/{job_id}", headers=headers)
    assert cleaned.status_code == 200
    assert cleaned.json()["status"] == "cleaned"

    snapshot = context.client.get("/api/v1/events/snapshot", headers=headers)
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["queues"]["cache_ready"] == 0
    assert any(item["id"] == str(job_id) for item in body["cache_jobs"])
    assert context.fake.was_deleted("fake-dir-0002")

    with context.factory() as session:
        job = session.get(CacheJob, job_id)
        progress = session.get(MoviePlaybackState, context.movie_ids[0])
        playback_row = session.get(PlaybackSession, uuid.UUID(manifest["session_id"]))
        events = list(
            session.scalars(
                select(DomainEvent)
                .where(DomainEvent.aggregate_id == job_id)
                .order_by(DomainEvent.sequence)
            )
        )
        notifications = list(
            session.scalars(
                select(Notification).where(Notification.resource_id == job_id)
            )
        )
        assert job is not None and job.status == "cleaned"
        assert progress is not None and progress.version == 2
        assert playback_row is None
        assert [event.event_type for event in events][-1] == "cache.job.cleaned.v1"
        assert {item.type for item in notifications} == {"cache_ready"}
        printable = repr(events) + repr(notifications) + repr(context.fake)
        for secret in (
            "UID=task113-private",
            "magnet:?xt=urn:btih:task113-private",
            "capability=fixture",
            "[Script Info]",
        ):
            assert secret not in printable


@pytest.mark.parametrize(
    "ac_evidence",
    [pytest.param(None, id="AC-092-AC-093-AC-115")],
)
def test_media_candidates_and_continuous_segments_are_selected_through_api(
    cloud_e2e_context: CloudE2eContext,
    ac_evidence: None,
) -> None:
    del ac_evidence
    context = cloud_e2e_context
    headers = context.bootstrap_and_bind()
    ambiguous = context.complete_cache_job(
        headers,
        index=1,
        files=_ambiguous_videos,
        expected_status="awaiting_selection",
    )
    ambiguous_job_id = uuid.UUID(ambiguous["id"])
    candidates = ambiguous["media_candidates"]
    assert len(candidates) == 2
    assert ambiguous["selected_media_ids"] == []
    selected = context.client.put(
        f"/api/v1/cache-jobs/{ambiguous_job_id}/media-selection",
        headers=headers,
        json={"media_ids": [candidates[0]["id"]]},
    )
    assert selected.status_code == 200
    assert selected.json()["status"] == "ready"
    assert selected.json()["selected_media_ids"] == [candidates[0]["id"]]

    segmented = context.complete_cache_job(
        headers,
        index=2,
        files=_segment_candidates,
        expected_status="awaiting_selection",
    )
    segmented_job_id = uuid.UUID(segmented["id"])
    groups: dict[str, list[dict[str, object]]] = {}
    for media in segmented["media_candidates"]:
        groups.setdefault(media["candidate_id"], []).append(media)
    segment_group = next(items for items in groups.values() if len(items) == 2)
    segment_group.sort(key=lambda item: int(item["sequence_no"]))
    partial = context.client.put(
        f"/api/v1/cache-jobs/{segmented_job_id}/media-selection",
        headers=headers,
        json={"media_ids": [segment_group[0]["id"]]},
    )
    assert partial.status_code == 409
    assert partial.json()["code"] == "state_conflict"
    complete = context.client.put(
        f"/api/v1/cache-jobs/{segmented_job_id}/media-selection",
        headers=headers,
        json={"media_ids": [item["id"] for item in reversed(segment_group)]},
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "ready"
    assert complete.json()["selected_media_ids"] == [
        item["id"] for item in segment_group
    ]

    with context.factory() as session:
        events = list(
            session.scalars(
                select(DomainEvent)
                .where(DomainEvent.aggregate_id == segmented_job_id)
                .order_by(DomainEvent.sequence)
            )
        )
    assert [event.event_type for event in events][-2:] == [
        "cache.job.selection_required.v1",
        "cache.job.ready.v1",
    ]


@pytest.mark.parametrize(
    "ac_evidence",
    [pytest.param(None, id="AC-086-AC-094-AC-127")],
)
def test_expired_worker_claim_reconciles_accepted_uncertain_submission_once(
    cloud_e2e_context: CloudE2eContext,
    ac_evidence: None,
) -> None:
    del ac_evidence
    context = cloud_e2e_context
    headers = context.bootstrap_and_bind()
    created = context.create_play_request(headers, index=3)
    job_id = uuid.UUID(created["cache_job"]["id"])
    expired_claim = context.claim_queue.claim_next(worker_id="task113-crashed-worker")
    assert expired_claim is not None and expired_claim.job_id == job_id
    context.fake.inject_post_fault(
        "submit_offline",
        Cloud115Problem("cloud115_submit_uncertain"),
    )
    context.clock.advance(timedelta(seconds=91))

    assert context.pipeline.run_once(worker_id="task113-recovery-worker") == "worked"
    with pytest.raises(CacheJobClaimLost):
        context.claim_queue.defer(expired_claim, "cloud115_unavailable")
    recovered = context.client.get(f"/api/v1/cache-jobs/{job_id}", headers=headers)
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "offlining"
    assert recovered.json()["error_code"] is None
    with context.factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None and job.remote_info_hash is not None
        remote_info_hash = job.remote_info_hash
    assert context.fake.offline_task(remote_info_hash).task_cid == job.task_dir_cid
    operations = [call.operation for call in context.fake.calls]
    assert operations.count("submit_offline") == 1
    assert operations.count("list_offline_tasks") == 1


@pytest.mark.parametrize(
    ("failure_code", "binding_status", "status_code"),
    [
        pytest.param(
            "cloud115_credentials_expired",
            "expired",
            422,
            id="AC-081-AC-127-expired",
        ),
        pytest.param(
            "cloud115_unavailable",
            "unavailable",
            503,
            id="AC-081-AC-127-unavailable",
        ),
    ],
)
def test_cloud_credential_failures_are_persisted_and_gate_new_requests(
    cloud_e2e_context: CloudE2eContext,
    failure_code: str,
    binding_status: str,
    status_code: int,
) -> None:
    context = cloud_e2e_context
    headers = context.bootstrap_and_bind()
    created = context.create_play_request(headers, index=4)
    job_id = uuid.UUID(created["cache_job"]["id"])
    context.fake.inject_fault(
        "find_or_create_directory",
        Cloud115Problem(failure_code),
    )

    assert context.pipeline.run_once(worker_id="task113-credential-worker") == "worked"
    binding = context.client.get("/api/v1/cloud115/binding", headers=headers)
    job = context.client.get(f"/api/v1/cache-jobs/{job_id}", headers=headers)
    blocked = context.client.post(
        f"/api/v1/movies/{context.movie_ids[5]}/play-requests",
        headers={**headers, "Idempotency-Key": "task113-credential-gate"},
        json={"source_id": str(context.source_ids[5])},
    )
    assert binding.status_code == job.status_code == 200
    assert binding.json()["status"] == binding_status
    assert job.json()["status"] == "submitting"
    assert job.json()["error_code"] == failure_code
    assert blocked.status_code == status_code
    assert blocked.json()["code"] == failure_code


@pytest.mark.parametrize("ac_evidence", [pytest.param(None, id="AC-036-AC-096")])
def test_blocked_remote_file_persists_source_rejection_and_clears_payload(
    cloud_e2e_context: CloudE2eContext,
    ac_evidence: None,
) -> None:
    del ac_evidence
    context = cloud_e2e_context
    headers = context.bootstrap_and_bind()
    failed = context.complete_cache_job(
        headers,
        index=6,
        files=_blocked_video,
        expected_status="failed",
    )
    job_id = uuid.UUID(failed["id"])
    assert failed["error_code"] == "cloud115_source_blocked"
    with context.factory() as session:
        source = session.get(ResourceSource, context.source_ids[6])
        assert source is not None
        rejection = session.scalar(
            select(SourceRejection).where(
                SourceRejection.website == source.website,
                SourceRejection.external_post_id == source.external_post_id,
            )
        )
        event = session.scalar(
            select(DomainEvent).where(
                DomainEvent.aggregate_id == job_id,
                DomainEvent.event_type == "cache.job.failed.v1",
            )
        )
        assert source.identification_status == "rejected"
        assert source.magnet_envelope is None
        assert rejection is not None
        assert rejection.reason_code == "cloud115_source_blocked"
        assert event is not None and event.payload["rejected_source"] is True


def _single_video_with_subtitle(task_dir_cid: str) -> tuple[RemoteFile, ...]:
    return (
        RemoteFile(
            file_id="task113-video",
            parent_cid=task_dir_cid,
            name="E2E-001.mp4",
            size_bytes=600 * MIB,
            pickcode="task113-video-pickcode",
            sha1="a" * 40,
            is_directory=False,
            is_video=True,
            duration_seconds=3600,
        ),
        RemoteFile(
            file_id="task113-subtitle",
            parent_cid=task_dir_cid,
            name="E2E-001.zh.ass",
            size_bytes=1024,
            pickcode="task113-subtitle-pickcode",
            sha1="b" * 40,
            is_directory=False,
            is_video=False,
        ),
    )


def _ambiguous_videos(task_dir_cid: str) -> tuple[RemoteFile, ...]:
    return (
        _video("ambiguous-a", task_dir_cid, "feature-a.mkv", 1_000 * MIB),
        _video("ambiguous-b", task_dir_cid, "feature-b.mkv", 1_000 * MIB),
    )


def _segment_candidates(task_dir_cid: str) -> tuple[RemoteFile, ...]:
    return (
        _video("segment-main", task_dir_cid, "E2E-003.mkv", 1_300 * MIB),
        _video("segment-cd2", task_dir_cid, "E2E-003-CD2.mkv", 700 * MIB),
        _video("segment-cd1", task_dir_cid, "E2E-003-CD1.mkv", 700 * MIB),
    )


def _blocked_video(task_dir_cid: str) -> tuple[RemoteFile, ...]:
    return (
        RemoteFile(
            file_id="blocked-video",
            parent_cid=task_dir_cid,
            name="E2E-007.mkv",
            size_bytes=1_000 * MIB,
            pickcode="blocked-video-pickcode",
            sha1="c" * 40,
            is_directory=False,
            is_video=True,
            duration_seconds=3600,
            blocked=True,
        ),
    )


def _video(
    file_id: str,
    parent_cid: str,
    name: str,
    size_bytes: int,
) -> RemoteFile:
    return RemoteFile(
        file_id=file_id,
        parent_cid=parent_cid,
        name=name,
        size_bytes=size_bytes,
        pickcode=f"{file_id}-pickcode",
        sha1=None,
        is_directory=False,
        is_video=True,
        duration_seconds=3600,
    )
