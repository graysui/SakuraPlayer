from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.events import CacheEventPublisher
from sakuraplayer.cloud_cache.models import CacheJob, Notification
from sakuraplayer.cloud_cache.notifications import NotificationWriter
from sakuraplayer.cloud_cache.snapshot import CacheSnapshotExtension
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.identity.models import Base

NOW = datetime(2026, 7, 28, 14, 0, tzinfo=timezone.utc)


def test_cache_event_and_notification_share_transaction_and_snapshot_shape() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    writer = DomainEventWriter(now=lambda: NOW)
    publisher = CacheEventPublisher(
        writer,
        NotificationWriter(writer, now=lambda: NOW),
    )
    job = _job(status="ready", capacity_class="ready")
    try:
        with factory.begin() as session:
            session.add(job)
            session.flush()
            publisher.publish_cache(
                session,
                job,
                event_type="cache.job.ready.v1",
                notification_type="cache_ready",
            )

        with factory() as session:
            events = list(
                session.scalars(select(DomainEvent).order_by(DomainEvent.sequence))
            )
            assert [event.event_type for event in events] == [
                "cache.job.ready.v1",
                "notification.created.v1",
            ]
            cache_resource = events[0].payload
            assert cache_resource["id"] == str(job.id)
            assert cache_resource["movie_id"] == str(job.movie_id)
            assert cache_resource["status"] == "ready"
            assert cache_resource["media_candidates"] == []
            assert cache_resource["selected_media_ids"] == []
            assert cache_resource["subtitles"] == []

            snapshot = CacheSnapshotExtension().snapshot(session, limit=100)
            assert snapshot.cache_ready == 1
            assert snapshot.cache_jobs[0]["id"] == str(job.id)
            assert snapshot.cloud115_binding["status"] == "unbound"
            assert len(snapshot.notifications) == 1
            assert snapshot.notifications[0]["type"] == "cache_ready"
    finally:
        engine.dispose()


def test_cache_event_rolls_back_with_domain_state() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    writer = DomainEventWriter(now=lambda: NOW)
    publisher = CacheEventPublisher(writer, NotificationWriter(writer, now=lambda: NOW))
    job = _job(status="failed", capacity_class="released")
    try:
        try:
            with factory.begin() as session:
                session.add(job)
                publisher.publish_cache(
                    session,
                    job,
                    event_type="cache.job.failed.v1",
                    notification_type="cache_failed",
                )
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        with factory() as session:
            assert session.get(CacheJob, job.id) is None
            assert list(session.scalars(select(DomainEvent))) == []
            assert list(session.scalars(select(Notification))) == []
    finally:
        engine.dispose()


def _job(*, status: str, capacity_class: str) -> CacheJob:
    return CacheJob(
        id=uuid.uuid4(),
        movie_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        binding_id=uuid.uuid4(),
        status=status,
        capacity_class=capacity_class,
        account_key="account",
        cache_root_cid="root-cid",
        task_dir_name="cache-task",
        remote_percent=100,
        ready_at=NOW if status == "ready" else None,
        last_accessed_at=NOW if status == "ready" else None,
        expires_at=(
            datetime(2026, 7, 29, 14, 0, tzinfo=timezone.utc)
            if status == "ready"
            else None
        ),
        failure_code="cache_no_valid_media" if status == "failed" else None,
        failure_stage="resolving" if status == "failed" else None,
        created_at=NOW,
        updated_at=NOW,
    )
