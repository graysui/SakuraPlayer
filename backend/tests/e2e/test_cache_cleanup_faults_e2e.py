from __future__ import annotations

import uuid

import pytest
from conftest import CloudE2eContext
from sqlalchemy import select

from sakuraplayer.cloud_cache.models import CacheJob, Cloud115Binding
from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "ac_evidence",
    [pytest.param(None, id="AC-081-AC-082-AC-094-AC-096-AC-098-AC-121-AC-122")],
)
def test_cleanup_ownership_lease_failure_and_retry(
    cloud_e2e_context: CloudE2eContext,
    ac_evidence: None,
) -> None:
    del ac_evidence
    context = cloud_e2e_context
    headers = context.bootstrap_and_bind()
    ready = context.complete_cache_job(headers, files=_files)
    job_id = uuid.UUID(ready["id"])
    session = context.client.post(
        f"/api/v1/cache-jobs/{job_id}/playback-sessions",
        headers=headers,
        json={
            "media_id": ready["selected_media_ids"][0],
            "mode": "original",
            "platform": "windows",
            "client_instance_id": str(context.client_instance_id),
        },
    )
    assert session.status_code == 201
    blocked = context.client.post(
        f"/api/v1/cache-jobs/{job_id}/cleanup", headers=headers
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "cache_active_lease"
    stopped = context.client.put(
        f"/api/v1/playback/sessions/{session.json()['session_id']}/heartbeat",
        headers=headers,
        json={
            "client_instance_id": str(context.client_instance_id),
            "playing": False,
        },
    )
    assert stopped.status_code == 200
    assert _cleanup(context, headers, job_id) == "cleaned"

    moved = context.complete_cache_job(headers, index=1, files=_files)
    moved_id = uuid.UUID(moved["id"])
    moved_dir = _task_dir(context, moved_id)
    context.fake.move_directory(moved_dir, "outside-cid")
    assert _cleanup(context, headers, moved_id) == "detached"
    assert not context.fake.was_deleted(moved_dir)

    failed = context.complete_cache_job(headers, index=2, files=_files)
    failed_id = uuid.UUID(failed["id"])
    failed_dir = _task_dir(context, failed_id)
    context.fake.inject_fault(
        "delete_managed_entries",
        Cloud115Problem("cloud115_unavailable"),
    )
    assert _cleanup(context, headers, failed_id) == "cleanup_failed"
    failed_snapshot = context.client.get(
        f"/api/v1/cache-jobs/{failed_id}", headers=headers
    )
    assert failed_snapshot.status_code == 200
    assert failed_snapshot.json()["status"] == "cleanup_failed"
    assert not context.fake.was_deleted(failed_dir)
    assert _cleanup(context, headers, failed_id) == "cleaned"

    account_changed = context.complete_cache_job(headers, index=3, files=_files)
    account_id = uuid.UUID(account_changed["id"])
    account_dir = _task_dir(context, account_id)
    with context.factory.begin() as db:
        binding = db.scalar(select(Cloud115Binding))
        assert binding is not None
        binding.account_key = "different-account"
    assert _cleanup(context, headers, account_id) == "detached"
    assert not context.fake.was_deleted(account_dir)


def _cleanup(
    context: CloudE2eContext,
    headers: dict[str, str],
    job_id: uuid.UUID,
) -> str:
    requested = context.client.post(
        f"/api/v1/cache-jobs/{job_id}/cleanup",
        headers=headers,
    )
    assert requested.status_code == 202
    assert (
        context.pipeline.run_once(worker_id=f"task113-cleanup-{job_id.hex[:6]}")
        == "worked"
    )
    with context.factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        return job.status


def _task_dir(context: CloudE2eContext, job_id: uuid.UUID) -> str:
    with context.factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None and job.task_dir_cid is not None
        return job.task_dir_cid


def _files(task_dir_cid: str):
    from sakuraplayer.cloud_cache.ports.cloud115 import RemoteFile

    return (
        RemoteFile(
            file_id="cleanup-video",
            parent_cid=task_dir_cid,
            name="E2E-002.mp4",
            size_bytes=600 * 1024 * 1024,
            pickcode="cleanup-video-pickcode",
            sha1="c" * 40,
            is_directory=False,
            is_video=True,
            duration_seconds=3600,
        ),
    )
