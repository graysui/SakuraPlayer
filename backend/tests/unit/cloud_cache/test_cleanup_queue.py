from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog import models as _catalog_models  # noqa: F401
from sakuraplayer.cloud_cache.cleanup import CleanupProblem, CleanupQueue
from sakuraplayer.cloud_cache.models import (
    CacheCleanupAttempt,
    CacheJob,
    CacheJobMediaSelection,
    RemoteMedia,
)
from sakuraplayer.identity.models import Base
from sakuraplayer.playback.models import PlaybackLease, PlaybackSession
from sakuraplayer.resources import models as _resource_models  # noqa: F401

NOW = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)


def test_expired_cache_is_claimed_before_capacity_lru() -> None:
    factory = _factory()
    expired_id = uuid.UUID(int=50)
    old_lru_id = uuid.UUID(int=1)
    with factory.begin() as session:
        session.add(_job(old_lru_id, accessed=NOW - timedelta(days=4)))
        session.add(
            _job(
                expired_id,
                accessed=NOW - timedelta(hours=2),
                expires=NOW - timedelta(seconds=1),
            )
        )

    claim = CleanupQueue(factory, now=lambda: NOW).claim_next(worker_id="cleanup-1")

    assert claim is not None and claim.job_id == expired_id


def test_capacity_over_target_uses_stable_lru_tiebreaker() -> None:
    factory = _factory()
    ids = [uuid.UUID(int=index) for index in range(1, 22)]
    with factory.begin() as session:
        for job_id in reversed(ids):
            session.add(_job(job_id, accessed=NOW - timedelta(hours=1)))

    claim = CleanupQueue(factory, now=lambda: NOW).claim_next(worker_id="cleanup-1")

    assert claim is not None and claim.job_id == ids[0]


def test_capacity_lru_accounts_for_cleanup_already_in_progress() -> None:
    factory = _factory()
    ids = [uuid.UUID(int=index) for index in range(1, 22)]
    with factory.begin() as session:
        for job_id in ids:
            session.add(_job(job_id, accessed=NOW - timedelta(hours=1)))
    queue = CleanupQueue(factory, now=lambda: NOW)

    first = queue.claim_next(worker_id="cleanup-1")
    second = queue.claim_next(worker_id="cleanup-2")

    assert first is not None and first.job_id == ids[0]
    assert second is None


@pytest.mark.parametrize(
    ("status", "capacity_class"),
    [
        ("offlining", "running"),
        ("cancelling", "ready"),
        ("cleanup_failed", "ready"),
    ],
)
def test_automatic_cleanup_excludes_non_materialized_states(
    status: str,
    capacity_class: str,
) -> None:
    factory = _factory()
    with factory.begin() as session:
        session.add(
            _job(
                uuid.uuid4(),
                status=status,
                capacity_class=capacity_class,
                expires=NOW - timedelta(seconds=1),
            )
        )

    assert (
        CleanupQueue(factory, now=lambda: NOW).claim_next(worker_id="cleanup-1") is None
    )


def test_manual_cleanup_rejects_active_lease() -> None:
    factory = _factory()
    job_id = uuid.uuid4()
    playback_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(_job(job_id))
        session.add(_playback(playback_id, job_id))
        session.add(
            PlaybackLease(
                id=uuid.uuid4(),
                playback_session_id=playback_id,
                client_instance_id=uuid.uuid4(),
                last_heartbeat_at=NOW,
                expires_at=NOW + timedelta(minutes=1),
                ended_at=None,
            )
        )

    with pytest.raises(CleanupProblem) as raised:
        CleanupQueue(factory, now=lambda: NOW).request(job_id)

    assert raised.value.code == "cache_active_lease"


def test_cleanup_success_finishes_attempt_deletes_media_and_releases_capacity() -> None:
    factory = _factory()
    job_id = uuid.uuid4()
    media_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(
            _job(
                job_id,
                accessed=NOW - timedelta(hours=2),
                expires=NOW - timedelta(seconds=1),
            )
        )
        session.add(
            RemoteMedia(
                id=media_id,
                cache_job_id=job_id,
                file_id="media-file",
                pickcode="media-pickcode",
                parent_cid="task-cid",
                name="movie.mkv",
                size_bytes=300_000_000,
                duration_seconds=600,
                candidate_id=uuid.uuid4(),
                sequence_no=0,
                selection_score=100,
                selection_evidence=[],
                is_valid=True,
                created_at=NOW,
            )
        )
        session.add(
            CacheJobMediaSelection(
                cache_job_id=job_id,
                sequence_no=0,
                media_id=media_id,
            )
        )
    queue = CleanupQueue(factory, now=lambda: NOW)
    claim = queue.claim_next(worker_id="cleanup-1")
    assert claim is not None

    queue.succeed(claim, ownership_evidence={"root_cid": "root-cid"})

    with factory() as session:
        job = session.get(CacheJob, job_id)
        attempt = session.get(CacheCleanupAttempt, claim.attempt_id)
        assert job is not None and job.status == "cleaned"
        assert job.capacity_class == "released"
        assert attempt is not None and attempt.status == "succeeded"
        assert session.scalar(select(func.count(RemoteMedia.id))) == 0
        assert session.scalar(select(func.count(CacheJobMediaSelection.media_id))) == 0


def _factory() -> sessionmaker:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _job(
    job_id: uuid.UUID,
    *,
    status: str = "ready",
    capacity_class: str = "ready",
    accessed: datetime = NOW,
    expires: datetime = NOW + timedelta(hours=24),
) -> CacheJob:
    return CacheJob(
        id=job_id,
        movie_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        binding_id=uuid.uuid4(),
        status=status,
        capacity_class=capacity_class,
        account_key="account",
        cache_root_cid="root-cid",
        task_dir_cid="task-cid-" + job_id.hex,
        task_dir_name="cache-" + job_id.hex,
        remote_percent=100,
        ready_at=NOW - timedelta(days=1),
        last_accessed_at=accessed,
        expires_at=expires,
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=1),
    )


def _playback(session_id: uuid.UUID, job_id: uuid.UUID) -> PlaybackSession:
    return PlaybackSession(
        id=session_id,
        admin_id=uuid.uuid4(),
        session_epoch=0,
        movie_id=uuid.uuid4(),
        cache_job_id=job_id,
        media_id=uuid.uuid4(),
        mode="original",
        platform="windows",
        user_agent_hash="a" * 64,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=12),
        revoked_at=None,
    )
