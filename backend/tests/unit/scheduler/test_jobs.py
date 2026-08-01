from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.models import ProviderSnapshotRequest
from sakuraplayer.cloud_cache.models import Notification
from sakuraplayer.resources.models import AvdbSyncRequest, AvdbSyncRun, Base
from sakuraplayer.resources.sync_service import AvdbSyncQueue
from sakuraplayer.scheduler.__main__ import build_scheduler
from sakuraplayer.scheduler.events import register_event_prune_job
from sakuraplayer.scheduler.jobs import register_avdb_jobs
from sakuraplayer.scheduler.provider_snapshots import register_provider_snapshot_job
from sakuraplayer.scheduler.rankings import RankingSchedulerJob, register_ranking_job


def test_registers_shanghai_incremental_and_weekly_full_enqueue_jobs() -> None:
    enqueued: list[str] = []
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    register_avdb_jobs(scheduler, enqueued.append)
    register_avdb_jobs(scheduler, enqueued.append)

    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {"avdb_incremental_30d", "avdb_full_reconcile"}
    assert str(scheduler.timezone) == "Asia/Shanghai"
    assert str(jobs["avdb_incremental_30d"].trigger) == ("cron[hour='3', minute='0']")
    assert str(jobs["avdb_full_reconcile"].trigger) == (
        "cron[day_of_week='sun', hour='4', minute='0']"
    )

    jobs["avdb_incremental_30d"].func(*jobs["avdb_incremental_30d"].args)
    jobs["avdb_full_reconcile"].func(*jobs["avdb_full_reconcile"].args)
    assert enqueued == ["incremental_30d", "full_reconcile"]


def test_database_queue_coalesces_duplicate_scheduler_slot() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    queue = AvdbSyncQueue(
        factory,
        now=lambda: datetime(2026, 7, 25, 19, 0, 30, tzinfo=timezone.utc),
    )

    first = queue.enqueue("incremental_30d")
    repeated = queue.enqueue("incremental_30d")

    assert first.created is True
    assert repeated.created is False
    assert first.request_id == repeated.request_id
    with factory() as session:
        requests = session.scalars(select(AvdbSyncRequest)).all()
        assert len(requests) == 1
        assert requests[0].scheduled_for == datetime(
            2026,
            7,
            25,
            19,
            0,
            tzinfo=timezone.utc,
        ).replace(tzinfo=None)
        assert requests[0].status == "queued"
    engine.dispose()


def test_initial_full_is_enqueued_once_and_never_recreated_after_a_run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    current = datetime(2026, 7, 25, 19, 0, 30, tzinfo=timezone.utc)
    queue = AvdbSyncQueue(factory, now=lambda: current)

    first = queue.ensure_initial_full()
    repeated = queue.ensure_initial_full()

    assert first is not None and first.created is True
    assert repeated is None
    with factory.begin() as session:
        request = session.scalar(select(AvdbSyncRequest))
        assert request is not None
        session.delete(request)
        session.add(
            AvdbSyncRun(
                id=uuid.uuid4(),
                mode="full_reconcile",
                repository="fixture/repository",
                release_id="fixture-release",
                status="failed",
                cursor={},
                started_at=current,
                completed_at=current,
                failure_code="service_unavailable",
                failure_detail="service_unavailable",
                stats={"inserted": 0, "updated": 0, "skipped": 0, "pending": 0},
                claim_token=None,
                claim_expires_at=None,
                attempt_count=1,
            )
        )

    assert queue.ensure_initial_full() is None
    engine.dispose()


def test_queue_claim_and_failure_persist_safe_attempt_fact() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    current = datetime(2026, 7, 25, 19, 0, 30, tzinfo=timezone.utc)
    queue = AvdbSyncQueue(factory, now=lambda: current)
    enqueued = queue.enqueue("incremental_30d")

    claimed = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))
    assert claimed is not None and claimed.request_id == enqueued.request_id
    queue.fail(
        claimed,
        code="avdb_decryption_failed",
        detail="avdb_decryption_failed",
    )

    with factory() as session:
        request = session.get(AvdbSyncRequest, enqueued.request_id)
        assert request is not None and request.status == "failed"
        assert request.attempt_count == 1
        assert request.completed_at == current.replace(tzinfo=None)
        assert request.failure_code == "avdb_decryption_failed"
        assert request.failure_detail == "avdb_decryption_failed"
        assert request.claim_owner is None
        assert request.claim_expires_at is None
    engine.dispose()


def test_expired_reclaim_rejects_old_claim_from_same_worker() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    current = [datetime(2026, 7, 25, 19, 0, tzinfo=timezone.utc)]
    queue = AvdbSyncQueue(factory, now=lambda: current[0])
    queue.enqueue("incremental_30d")

    old_claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))
    current[0] += timedelta(minutes=6)
    new_claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))

    assert old_claim is not None and new_claim is not None
    assert old_claim.claim_token != new_claim.claim_token
    with pytest.raises(RuntimeError):
        queue.fail(old_claim, code="internal_error", detail="internal_error")
    queue.renew(new_claim, lease_duration=timedelta(minutes=5))
    queue.fail(new_claim, code="internal_error", detail="internal_error")
    engine.dispose()


def test_registers_weekly_provider_snapshot_enqueue_only_job() -> None:
    calls = 0

    def enqueue() -> None:
        nonlocal calls
        calls += 1

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    register_provider_snapshot_job(scheduler, enqueue)
    register_provider_snapshot_job(scheduler, enqueue)

    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert "provider_snapshots_weekly" in jobs
    assert str(jobs["provider_snapshots_weekly"].trigger) == (
        "cron[day_of_week='sun', hour='5', minute='0']"
    )
    jobs["provider_snapshots_weekly"].func()
    assert calls == 1


def test_provider_snapshot_job_rejects_non_shanghai_scheduler() -> None:
    scheduler = BackgroundScheduler(timezone="UTC")

    with pytest.raises(ValueError, match="Asia/Shanghai"):
        register_provider_snapshot_job(scheduler, lambda: None)


def test_scheduler_main_build_registers_persistent_provider_snapshot_job() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    scheduler = build_scheduler(factory)

    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {
        "avdb_incremental_30d",
        "avdb_full_reconcile",
        "provider_snapshots_weekly",
        "javdb_rankings_daily",
        "domain_events_daily_prune",
    }
    assert str(jobs["domain_events_daily_prune"].trigger) == (
        "cron[hour='2', minute='30']"
    )
    jobs["provider_snapshots_weekly"].func()
    jobs["provider_snapshots_weekly"].func()
    with factory.begin() as session:
        session.add(
            Notification(
                id=uuid.uuid4(),
                type="cache_ready",
                resource_id=uuid.uuid4(),
                error_code=None,
                dedupe_key="expired-scheduler-notification",
                created_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
                read_at=None,
            )
        )
    jobs["domain_events_daily_prune"].func()
    with factory() as session:
        initial_full = list(
            session.scalars(
                select(AvdbSyncRequest).where(AvdbSyncRequest.mode == "full_reconcile")
            )
        )
        assert len(initial_full) == 1
        requests = list(session.scalars(select(ProviderSnapshotRequest)))
        assert len(requests) == 1
        assert requests[0].status == "queued"
        assert session.scalar(select(Notification.id)) is None
    engine.dispose()


def test_event_prune_job_is_daily_and_single_instance() -> None:
    calls = 0

    def prune() -> None:
        nonlocal calls
        calls += 1

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    register_event_prune_job(scheduler, prune)
    register_event_prune_job(scheduler, prune)

    job = {item.id: item for item in scheduler.get_jobs()}["domain_events_daily_prune"]
    assert str(job.trigger) == "cron[hour='2', minute='30']"
    job.func()
    assert calls == 1


def test_registers_daily_ranking_enqueue_only_job_at_0145_shanghai() -> None:
    calls: list[tuple[datetime, int, bool]] = []

    class Queue:
        def enqueue_due_targets(
            self,
            *,
            scheduled_for: datetime,
            current_year: int,
            credentials_configured: bool,
        ) -> None:
            calls.append((scheduled_for, current_year, credentials_configured))

    current = datetime(2026, 7, 26, 1, 45, tzinfo=timezone(timedelta(hours=8)))
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    job = RankingSchedulerJob(
        Queue(),
        credentials_configured=lambda: True,
        now=lambda: current,
    )

    register_ranking_job(scheduler, job)
    register_ranking_job(scheduler, job)

    registered = {item.id: item for item in scheduler.get_jobs()}[
        "javdb_rankings_daily"
    ]
    assert str(registered.trigger) == "cron[hour='1', minute='45']"
    registered.func()
    assert calls == [(current, 2026, True)]
