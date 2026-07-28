from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog import models as _catalog_models  # noqa: F401
from sakuraplayer.cloud_cache import models as _cache_models  # noqa: F401
from sakuraplayer.cloud_cache.models import CacheJob
from sakuraplayer.identity.domain import CurrentAdmin
from sakuraplayer.identity.models import Base
from sakuraplayer.playback.heartbeat import PlaybackHeartbeatService
from sakuraplayer.playback.models import PlaybackLease, PlaybackSession
from sakuraplayer.playback.progress import (
    MoviePlaybackStateService,
    ProgressUpdate,
    ProgressVersionConflict,
)
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)


def test_heartbeat_without_progress_renews_lease_and_cache_ttl() -> None:
    heartbeat, _, factory, admin, session_id, job_id = _context()

    result = heartbeat.heartbeat(
        admin=admin,
        playback_session_id=session_id,
        client_instance_id=admin.client_instance_id,
        progress=None,
        playing=True,
    )

    assert result.progress is None
    assert result.lease_expires_at == NOW + timedelta(seconds=90)
    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        assert _utc(job.last_accessed_at) == NOW
        assert _utc(job.expires_at) == NOW + timedelta(hours=24)


def test_conflicting_progress_rolls_back_lease_and_cache_refresh() -> None:
    heartbeat, progress, factory, admin, session_id, job_id = _context()
    progress.update(
        movie_id=_movie_id(factory, session_id),
        expected_version=0,
        position_seconds=Decimal("10"),
        duration_seconds=Decimal("1000"),
    )
    with factory() as session:
        lease_before = session.scalar(
            select(PlaybackLease).where(PlaybackLease.playback_session_id == session_id)
        )
        job_before = session.get(CacheJob, job_id)
        assert lease_before is not None and job_before is not None
        old_lease_expiry = _utc(lease_before.expires_at)
        old_last_accessed = _utc(job_before.last_accessed_at)

    with pytest.raises(ProgressVersionConflict):
        heartbeat.heartbeat(
            admin=admin,
            playback_session_id=session_id,
            client_instance_id=admin.client_instance_id,
            progress=ProgressUpdate(
                expected_version=0,
                position_seconds=Decimal("20"),
                duration_seconds=Decimal("1000"),
            ),
            playing=True,
        )

    with factory() as session:
        lease = session.scalar(
            select(PlaybackLease).where(PlaybackLease.playback_session_id == session_id)
        )
        job = session.get(CacheJob, job_id)
        assert lease is not None and job is not None
        assert _utc(lease.expires_at) == old_lease_expiry
        assert _utc(job.last_accessed_at) == old_last_accessed


def test_playing_false_flushes_progress_and_ends_lease_without_ttl_refresh() -> None:
    heartbeat, _, factory, admin, session_id, job_id = _context()

    result = heartbeat.heartbeat(
        admin=admin,
        playback_session_id=session_id,
        client_instance_id=admin.client_instance_id,
        progress=ProgressUpdate(
            expected_version=0,
            position_seconds=Decimal("30"),
            duration_seconds=None,
        ),
        playing=False,
    )

    assert result.lease_expires_at is None
    assert result.progress is not None and result.progress.version == 1
    with factory() as session:
        lease = session.scalar(
            select(PlaybackLease).where(PlaybackLease.playback_session_id == session_id)
        )
        job = session.get(CacheJob, job_id)
        assert lease is not None and job is not None
        assert _utc(lease.ended_at) == NOW
        assert _utc(job.last_accessed_at) == NOW - timedelta(minutes=5)


def _context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    admin = CurrentAdmin(
        admin_id=uuid.uuid4(),
        username="admin",
        session_id=uuid.uuid4(),
        client_instance_id=uuid.uuid4(),
        session_epoch=3,
    )
    movie_id = uuid.uuid4()
    job_id = uuid.uuid4()
    session_id = uuid.uuid4()
    old = NOW - timedelta(minutes=5)
    with factory.begin() as session:
        session.add(
            Movie(
                id=movie_id,
                normalized_number="TASK-111-HB",
                raw_numbers=["TASK-111-HB"],
                catalog_state="core_ready",
                created_at=old,
                updated_at=old,
            )
        )
        session.add(
            CacheJob(
                id=job_id,
                movie_id=movie_id,
                source_id=uuid.uuid4(),
                binding_id=uuid.uuid4(),
                status="ready",
                capacity_class="ready",
                account_key="account",
                cache_root_cid="root",
                task_dir_cid="task",
                task_dir_name="cache-task",
                remote_percent=100,
                ready_at=old,
                last_accessed_at=old,
                expires_at=old + timedelta(hours=24),
                created_at=old,
                updated_at=old,
            )
        )
        session.add(
            PlaybackSession(
                id=session_id,
                admin_id=admin.admin_id,
                session_epoch=admin.session_epoch,
                movie_id=movie_id,
                cache_job_id=job_id,
                media_id=uuid.uuid4(),
                mode="original",
                platform="windows",
                user_agent_hash="a" * 64,
                issued_at=old,
                expires_at=NOW + timedelta(hours=1),
                revoked_at=None,
            )
        )
        session.add(
            PlaybackLease(
                id=uuid.uuid4(),
                playback_session_id=session_id,
                client_instance_id=admin.client_instance_id,
                last_heartbeat_at=old,
                expires_at=NOW + timedelta(seconds=10),
                ended_at=None,
            )
        )
    progress = MoviePlaybackStateService(factory, now=lambda: NOW)
    heartbeat = PlaybackHeartbeatService(
        factory,
        progress_service=progress,
        now=lambda: NOW,
        ttl_hours=lambda: 24,
    )
    return heartbeat, progress, factory, admin, session_id, job_id


def _movie_id(factory: sessionmaker, session_id: uuid.UUID) -> uuid.UUID:
    with factory() as session:
        playback = session.get(PlaybackSession, session_id)
        assert playback is not None
        return playback.movie_id


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
