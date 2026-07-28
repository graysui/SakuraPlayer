from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog import models as _catalog_models  # noqa: F401
from sakuraplayer.cloud_cache import models as _cache_models  # noqa: F401
from sakuraplayer.cloud_cache.models import CacheJob
from sakuraplayer.identity.models import Base
from sakuraplayer.playback.lease import PlaybackLeaseProblem, PlaybackLeaseService
from sakuraplayer.playback.models import PlaybackSession
from sakuraplayer.resources import models as _resource_models  # noqa: F401

NOW = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)


def test_lease_acquire_renews_same_session_client_and_end_releases() -> None:
    factory, session_id, job_id = _context()
    current = [NOW]
    ttl_hours = [24]
    service = PlaybackLeaseService(
        factory,
        now=lambda: current[0],
        duration=timedelta(seconds=90),
        ttl_hours=lambda: ttl_hours[0],
    )
    client_id = uuid.uuid4()

    first = service.acquire(
        playback_session_id=session_id,
        client_instance_id=client_id,
    )
    current[0] += timedelta(seconds=30)
    ttl_hours[0] = 48
    renewed = service.acquire(
        playback_session_id=session_id,
        client_instance_id=client_id,
    )

    assert renewed.id == first.id
    assert renewed.expires_at == NOW + timedelta(seconds=120)
    assert service.active_for_job(job_id)
    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        assert _as_utc(job.ready_at) == NOW
        assert _as_utc(job.last_accessed_at) == NOW + timedelta(seconds=30)
        assert _as_utc(job.expires_at) == NOW + timedelta(hours=48, seconds=30)

    service.end(playback_session_id=session_id, client_instance_id=client_id)
    assert not service.active_for_job(job_id)


def test_lease_never_outlives_playback_session() -> None:
    factory, session_id, _ = _context(session_duration=timedelta(seconds=45))

    lease = PlaybackLeaseService(
        factory,
        now=lambda: NOW,
        duration=timedelta(seconds=90),
    ).acquire(
        playback_session_id=session_id,
        client_instance_id=uuid.uuid4(),
    )

    assert lease.expires_at == NOW + timedelta(seconds=45)


def test_lease_cannot_start_after_cleanup_locks_job_out_of_ready() -> None:
    factory, session_id, job_id = _context()
    with factory.begin() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        job.status = "cleaning"

    with pytest.raises(PlaybackLeaseProblem):
        PlaybackLeaseService(factory, now=lambda: NOW).acquire(
            playback_session_id=session_id,
            client_instance_id=uuid.uuid4(),
        )


def _context(
    *, session_duration: timedelta = timedelta(hours=12)
) -> tuple[sessionmaker, uuid.UUID, uuid.UUID]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    session_id = uuid.uuid4()
    job_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(
            CacheJob(
                id=job_id,
                movie_id=uuid.uuid4(),
                source_id=uuid.uuid4(),
                binding_id=uuid.uuid4(),
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
        session.add(
            PlaybackSession(
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
                expires_at=NOW + session_duration,
                revoked_at=None,
            )
        )
    return factory, session_id, job_id


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
