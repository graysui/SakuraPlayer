from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.cancellation import CancellationService
from sakuraplayer.cloud_cache.cleanup import CleanupQueue
from sakuraplayer.cloud_cache.events import CacheEventPublisher
from sakuraplayer.cloud_cache.models import CacheJob, Notification
from sakuraplayer.cloud_cache.notifications import NotificationWriter
from sakuraplayer.cloud_cache.worker.claim import CacheJobClaimQueue
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.identity.models import Base

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)


def test_queued_start_and_ordinary_failure_publish_once() -> None:
    factory, engine = _context(_job(status="queued", capacity_class="queued"))
    publisher = _publisher()
    queue = CacheJobClaimQueue(
        factory,
        now=lambda: NOW,
        event_publisher=publisher,
    )
    try:
        claim = queue.claim_next(worker_id="worker-1")
        assert claim is not None
        queue.fail(claim, "cloud115_offline_failed")

        with factory() as session:
            job = session.get(CacheJob, claim.job_id)
            assert job is not None
            assert (job.status, job.failure_stage) == ("failed", "submitting")
            assert [
                event.event_type
                for event in session.scalars(
                    select(DomainEvent).order_by(DomainEvent.sequence)
                )
            ] == [
                "cache.job.updated.v1",
                "notification.created.v1",
                "cache.job.failed.v1",
                "notification.created.v1",
            ]
            assert [
                item.type
                for item in session.scalars(
                    select(Notification).order_by(Notification.created_at)
                )
            ] == ["cache_started", "cache_failed"]
    finally:
        engine.dispose()


def test_immediate_cancel_persists_reason_and_publishes_cancelled() -> None:
    job = _job(status="queued", capacity_class="queued")
    factory, engine = _context(job)
    service = CancellationService(
        factory,
        now=lambda: NOW,
        event_publisher=_publisher(),
    )
    try:
        result = service.request(job.id, confirmed=True)
        assert result.status == "cleaned"
        with factory() as session:
            saved = session.get(CacheJob, job.id)
            assert saved is not None and saved.cleanup_reason == "cancelled"
            events = list(session.scalars(select(DomainEvent)))
            assert [event.event_type for event in events] == ["cache.job.cancelled.v1"]
            assert events[0].payload["cleanup_reason"] == "cancelled"
    finally:
        engine.dispose()


def test_manual_cleanup_keeps_reason_through_success() -> None:
    job = _job(status="ready", capacity_class="ready", materialized=True)
    factory, engine = _context(job)
    queue = CleanupQueue(
        factory,
        now=lambda: NOW,
        event_publisher=_publisher(),
    )
    try:
        assert queue.request(job.id).status == "cleaning"
        claim = queue.claim_next(worker_id="cleanup-1")
        assert claim is not None
        queue.succeed(claim, ownership_evidence={"owned": True})

        with factory() as session:
            saved = session.get(CacheJob, job.id)
            assert saved is not None
            assert (saved.status, saved.cleanup_reason) == ("cleaned", "manual")
            assert [
                event.event_type
                for event in session.scalars(
                    select(DomainEvent).order_by(DomainEvent.sequence)
                )
            ] == ["cache.job.updated.v1", "cache.job.cleaned.v1"]
    finally:
        engine.dispose()


def _publisher() -> CacheEventPublisher:
    writer = DomainEventWriter(now=lambda: NOW)
    return CacheEventPublisher(writer, NotificationWriter(writer, now=lambda: NOW))


def _context(job: CacheJob):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(job)
    return factory, engine


def _job(
    *,
    status: str,
    capacity_class: str,
    materialized: bool = False,
) -> CacheJob:
    return CacheJob(
        id=uuid.uuid4(),
        movie_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        binding_id=uuid.uuid4(),
        status=status,
        capacity_class=capacity_class,
        account_key="account",
        cache_root_cid="root-cid",
        task_dir_cid="task-cid" if materialized else None,
        task_dir_name="cache-task",
        remote_percent=100 if materialized else 0,
        ready_at=NOW - timedelta(hours=1) if materialized else None,
        last_accessed_at=NOW - timedelta(hours=1) if materialized else None,
        expires_at=NOW + timedelta(hours=1) if materialized else None,
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(hours=1),
    )
