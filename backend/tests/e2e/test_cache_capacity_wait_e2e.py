from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from conftest import CloudE2eContext
from sqlalchemy import func, select

from sakuraplayer.cloud_cache.models import CacheJob, Notification
from sakuraplayer.cloud_cache.ports.cloud115 import OfflineStatus, RemoteFile
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.playback.models import PlaybackSession

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "ac_evidence",
    [pytest.param(None, id="AC-084-AC-085-AC-088-AC-089-AC-090-AC-091-AC-115-AC-118")],
)
def test_cache_capacity_and_client_wait_observation_boundary(
    cloud_e2e_context: CloudE2eContext,
    ac_evidence: None,
) -> None:
    del ac_evidence
    context = cloud_e2e_context
    headers = context.bootstrap_and_bind()
    created: list[dict[str, object]] = []
    for index in range(12):
        created.append(context.create_play_request(headers, index=index))
    overflow = context.client.post(
        f"/api/v1/movies/{context.movie_ids[12]}/play-requests",
        headers={
            **headers,
            "Idempotency-Key": "task113-play-request-overflow",
        },
        json={"source_id": str(context.source_ids[12])},
    )
    assert overflow.status_code == 409
    assert overflow.json()["code"] == "cache_queue_full"
    assert [item["disposition"] for item in created[:2]] == ["started", "started"]
    assert [item["disposition"] for item in created[2:]] == ["queued"] * 10
    reused = context.client.post(
        f"/api/v1/movies/{context.movie_ids[0]}/play-requests",
        headers={**headers, "Idempotency-Key": "task113-capacity-reused"},
        json={"source_id": str(context.source_ids[0])},
    )
    assert reused.status_code == 200
    assert reused.json()["disposition"] == "reused"
    assert reused.json()["cache_job"]["id"] == created[0]["cache_job"]["id"]

    with context.factory() as session:
        before_sequence = session.scalar(
            select(func.coalesce(func.max(DomainEvent.sequence), 0))
        )
        before_jobs = {
            job.id: (job.status, job.capacity_class)
            for job in session.scalars(select(CacheJob))
        }
    context.clock.advance(timedelta(seconds=60))
    with context.factory() as session:
        after_sequence = session.scalar(
            select(func.coalesce(func.max(DomainEvent.sequence), 0))
        )
        after_jobs = {
            job.id: (job.status, job.capacity_class)
            for job in session.scalars(select(CacheJob))
        }
        assert after_sequence == before_sequence
        assert after_jobs == before_jobs

    for index in range(2):
        claim = context.claim_queue.claim_next(worker_id=f"task113-capacity-{index}")
        assert claim is not None
        context.claim_queue.fail(claim, "task113_test_failure")

    assert context.pipeline.run_once(worker_id="task113-capacity-promote") == "worked"
    with context.factory() as session:
        promoted_job = session.scalar(
            select(CacheJob).where(CacheJob.status == "offlining")
        )
        assert promoted_job is not None
        assert promoted_job.task_dir_cid is not None
        assert promoted_job.remote_info_hash is not None
        promoted_job_id = promoted_job.id
        task_dir_cid = promoted_job.task_dir_cid
        info_hash = promoted_job.remote_info_hash
    context.fake.seed_files(task_dir_cid, _video(task_dir_cid))
    context.fake.set_offline_status(
        info_hash,
        OfflineStatus.COMPLETED,
        percent_done=100.0,
    )
    assert context.pipeline.run_once(worker_id="task113-capacity-ready") == "worked"
    promoted = context.client.get(
        f"/api/v1/cache-jobs/{promoted_job_id}",
        headers=headers,
    )
    assert promoted.status_code == 200
    assert promoted.json()["status"] == "ready"
    with context.factory() as session:
        started = list(
            session.scalars(
                select(Notification).where(Notification.type == "cache_started")
            )
        )
        ready = list(
            session.scalars(
                select(Notification).where(Notification.type == "cache_ready")
            )
        )
        assert len(started) == 1
        assert len(ready) == 1
        assert session.scalar(select(func.count(PlaybackSession.id))) == 0

    snapshot = context.client.get("/api/v1/events/snapshot", headers=headers)
    assert snapshot.status_code == 200
    assert snapshot.json()["queues"]["cache_running"] == 0
    assert snapshot.json()["queues"]["cache_queued"] == 9
    assert snapshot.json()["queues"]["cache_ready"] == 1

    for item in created:
        job_id = uuid.UUID(str(item["cache_job"]["id"]))
        response = context.client.get(f"/api/v1/cache-jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["status"] in {"failed", "ready", "queued"}


def _video(task_dir_cid: str) -> tuple[RemoteFile, ...]:
    return (
        RemoteFile(
            file_id="capacity-video",
            parent_cid=task_dir_cid,
            name="E2E-003.mp4",
            size_bytes=600 * 1024 * 1024,
            pickcode="capacity-video-pickcode",
            sha1="9" * 40,
            is_directory=False,
            is_video=True,
            duration_seconds=3600,
        ),
    )
