from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog import models as _catalog_models  # noqa: F401
from sakuraplayer.cloud_cache.cleanup import CleanupQueue, CleanupWorker
from sakuraplayer.cloud_cache.models import CacheCleanupAttempt, CacheJob
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    DirectoryBreadcrumb,
    DirectoryInfo,
)
from sakuraplayer.identity.models import Base
from sakuraplayer.resources import models as _resource_models  # noqa: F401
from tests.fakes.cloud115 import FakeCloud115

NOW = datetime(2026, 7, 28, 11, 0, tzinfo=timezone.utc)


def test_safe_cleanup_deletes_only_verified_task_directory() -> None:
    factory, job_id = _context()
    fake = FakeCloud115(
        directory_infos=[_root(), _task()],
        delete_results=[None],
    )

    assert _worker(factory, fake).run_once(worker_id="cleanup-1") == "worked"

    assert [call.operation for call in fake.calls] == [
        "directory_info",
        "directory_info",
        "delete_managed_entries",
    ]
    assert fake.calls[-1].safe_arguments == ("task-cid", "root-cid")
    assert _status(factory, job_id) == "cleaned"


def test_missing_task_directory_is_confirmed_cleaned_without_delete() -> None:
    factory, job_id = _context()
    fake = FakeCloud115(
        directory_infos=[
            _root(),
            Cloud115Problem("cloud115_directory_not_found"),
        ]
    )

    _worker(factory, fake).run_once(worker_id="cleanup-1")

    assert [call.operation for call in fake.calls] == [
        "directory_info",
        "directory_info",
    ]
    assert _status(factory, job_id) == "cleaned"


def test_moved_task_is_detached_and_never_deleted() -> None:
    factory, job_id = _context()
    fake = FakeCloud115(
        directory_infos=[
            _root(),
            DirectoryInfo(
                cid="task-cid",
                parent_cid="outside-root",
                name="cache-task",
                path=(DirectoryBreadcrumb("outside-root", "User Files"),),
            ),
        ]
    )

    _worker(factory, fake).run_once(worker_id="cleanup-1")

    assert all(call.operation != "delete_managed_entries" for call in fake.calls)
    assert _status(factory, job_id) == "detached"


def test_changed_root_is_detached_before_task_lookup_or_delete() -> None:
    factory, job_id = _context()
    fake = FakeCloud115(
        directory_infos=[
            DirectoryInfo(
                cid="root-cid",
                parent_cid="outside-root",
                name="SakuraPlayer-Cache",
                path=(DirectoryBreadcrumb("outside-root", "User Files"),),
            )
        ]
    )

    _worker(factory, fake).run_once(worker_id="cleanup-1")

    assert [call.operation for call in fake.calls] == ["directory_info"]
    assert _status(factory, job_id) == "detached"


def test_failed_delete_keeps_capacity_and_manual_retry_uses_next_attempt() -> None:
    factory, job_id = _context()
    failed = FakeCloud115(
        directory_infos=[_root(), _task()],
        delete_results=[Cloud115Problem("cloud115_unavailable")],
    )
    _worker(factory, failed).run_once(worker_id="cleanup-1")
    assert _status(factory, job_id) == "cleanup_failed"

    queue = CleanupQueue(factory, now=lambda: NOW + timedelta(minutes=1))
    assert queue.request(job_id).status == "cleaning"
    succeeded = FakeCloud115(
        directory_infos=[_root(), _task()],
        delete_results=[None],
    )
    CleanupWorker(queue, _scope(succeeded)).run_once(worker_id="cleanup-2")

    with factory() as session:
        attempts = tuple(
            session.scalars(
                select(CacheCleanupAttempt)
                .where(CacheCleanupAttempt.cache_job_id == job_id)
                .order_by(CacheCleanupAttempt.attempt_no)
            )
        )
        assert [(item.attempt_no, item.status) for item in attempts] == [
            (1, "failed"),
            (2, "succeeded"),
        ]
    assert _status(factory, job_id) == "cleaned"


def test_expired_claim_recovery_confirms_prior_delete_by_task_not_found() -> None:
    factory, job_id = _context()
    first_queue = CleanupQueue(factory, now=lambda: NOW)
    assert first_queue.claim_next(worker_id="cleanup-crashed") is not None
    recovery_queue = CleanupQueue(factory, now=lambda: NOW + timedelta(minutes=3))
    missing = FakeCloud115(
        directory_infos=[
            _root(),
            Cloud115Problem("cloud115_directory_not_found"),
        ]
    )

    CleanupWorker(recovery_queue, _scope(missing)).run_once(
        worker_id="cleanup-recovery"
    )

    with factory() as session:
        attempts = tuple(
            session.scalars(
                select(CacheCleanupAttempt)
                .where(CacheCleanupAttempt.cache_job_id == job_id)
                .order_by(CacheCleanupAttempt.attempt_no)
            )
        )
        assert [(item.attempt_no, item.status) for item in attempts] == [
            (1, "failed"),
            (2, "succeeded"),
        ]
    assert _status(factory, job_id) == "cleaned"


def test_busy_delete_is_retried_with_backoff_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(
        "sakuraplayer.cloud_cache.cleanup._BUSY_RETRY_DELAY",
        timedelta(seconds=0),
    )
    factory, job_id = _context()
    fake = FakeCloud115(
        directory_infos=[_root(), _task()],
        delete_results=[
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
            None,
        ],
    )

    assert _worker(factory, fake).run_once(worker_id="cleanup-1") == "worked"

    assert [call.operation for call in fake.calls].count("delete_managed_entries") == 3
    assert _status(factory, job_id) == "cleaned"


def test_persistent_busy_delete_releases_claim_and_retries_until_success(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "sakuraplayer.cloud_cache.cleanup._BUSY_RETRY_DELAY",
        timedelta(seconds=0),
    )
    factory, job_id = _context()
    busy = FakeCloud115(
        directory_infos=[_root(), _task()],
        delete_results=[
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
        ],
    )

    # 第一轮：3 次短退避耗尽后释放 claim，任务保持 cleaning（不转 cleanup_failed）。
    _worker(factory, busy).run_once(worker_id="cleanup-1")
    assert _status(factory, job_id) == "cleaning"
    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job.claim_owner is None

    # 115 删除队列恢复：重新 claim 后删除成功，任务证明式终结。
    recovered = FakeCloud115(
        directory_infos=[_root(), _task()],
        delete_results=[None],
    )
    _worker(factory, recovered).run_once(worker_id="cleanup-1")
    assert _status(factory, job_id) == "cleaned"

    with factory() as session:
        attempts = tuple(
            session.scalars(
                select(CacheCleanupAttempt)
                .where(CacheCleanupAttempt.cache_job_id == job_id)
                .order_by(CacheCleanupAttempt.attempt_no)
            )
        )
        assert [(item.attempt_no, item.status) for item in attempts] == [
            (1, "failed"),
            (2, "succeeded"),
        ]


def test_delete_missing_target_is_idempotent_success() -> None:
    factory, job_id = _context()
    fake = FakeCloud115(
        directory_infos=[_root(), _task()],
        delete_results=[Cloud115Problem("cloud115_file_not_found")],
    )

    _worker(factory, fake).run_once(worker_id="cleanup-1")

    assert _status(factory, job_id) == "cleaned"


def test_busy_release_rotates_across_multiple_jobs(monkeypatch) -> None:
    monkeypatch.setattr(
        "sakuraplayer.cloud_cache.cleanup._BUSY_RETRY_DELAY",
        timedelta(seconds=0),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    job_a = _job_with(factory, "task-a", "cache-a")
    job_b = _job_with(factory, "task-b", "cache-b")
    clock = {"now": NOW}
    queue = CleanupQueue(factory, now=lambda: clock["now"])
    assert queue.request(job_a).status == "cleaning"
    clock["now"] += timedelta(seconds=1)
    assert queue.request(job_b).status == "cleaning"
    fake = FakeCloud115(
        directory_infos=[
            _root(),
            _task("task-a", "cache-a"),
            _root(),
            _task("task-b", "cache-b"),
        ],
        delete_results=[
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
        ],
    )
    worker = CleanupWorker(queue, _scope(fake))

    # 第一轮 claim job_a（updated_at 最早），busy 重试耗尽后 release 排到队尾。
    clock["now"] += timedelta(seconds=2)
    assert worker.run_once(worker_id="cleanup-1") == "worked"
    # 第二轮 claim job_b（updated_at 早于刚释放的 job_a）。
    clock["now"] += timedelta(seconds=2)
    assert worker.run_once(worker_id="cleanup-1") == "worked"

    # 两个 busy 任务都保持 cleaning 且释放 claim，attempt 记录 busy 码以区分真实失败。
    with factory() as session:
        for job_id in (job_a, job_b):
            job = session.get(CacheJob, job_id)
            assert job.status == "cleaning"
            assert job.claim_owner is None
        attempts = tuple(session.scalars(select(CacheCleanupAttempt)))
        assert sorted(
            (a.cache_job_id, a.status, a.failure_code) for a in attempts
        ) == sorted(
            [
                (job_a, "failed", "cloud115_operation_busy"),
                (job_b, "failed", "cloud115_operation_busy"),
            ]
        )


def test_busy_over_max_attempts_fails_after_rotation(monkeypatch) -> None:
    monkeypatch.setattr(
        "sakuraplayer.cloud_cache.cleanup._BUSY_RETRY_DELAY",
        timedelta(seconds=0),
    )
    monkeypatch.setattr(
        "sakuraplayer.cloud_cache.cleanup._BUSY_MAX_ATTEMPTS",
        1,
    )
    factory, job_id = _context()
    fake = FakeCloud115(
        directory_infos=[_root(), _task()],
        delete_results=[
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
            Cloud115Problem("cloud115_operation_busy"),
        ],
    )

    _worker(factory, fake).run_once(worker_id="cleanup-1")

    assert _status(factory, job_id) == "cleanup_failed"


def _worker(factory, fake: FakeCloud115) -> CleanupWorker:
    return CleanupWorker(CleanupQueue(factory, now=lambda: NOW), _scope(fake))


def _scope(fake: FakeCloud115):
    @asynccontextmanager
    async def cloud_scope(_claim):
        yield fake

    return cloud_scope


def _context() -> tuple[sessionmaker, uuid.UUID]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    job_id = _job_with(factory, "task-cid", "cache-task")
    return factory, job_id


def _job_with(factory: sessionmaker, task_cid: str, task_name: str) -> uuid.UUID:
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
                cache_root_cid="root-cid",
                task_dir_cid=task_cid,
                task_dir_name=task_name,
                remote_percent=100,
                ready_at=NOW - timedelta(days=2),
                last_accessed_at=NOW - timedelta(days=2),
                expires_at=NOW - timedelta(days=1),
                created_at=NOW - timedelta(days=3),
                updated_at=NOW - timedelta(days=2),
            )
        )
    return job_id


def _root() -> DirectoryInfo:
    return DirectoryInfo(
        cid="root-cid",
        parent_cid="0",
        name="SakuraPlayer-Cache",
        path=(DirectoryBreadcrumb("0", "root"),),
    )


def _task(
    cid: str = "task-cid",
    name: str = "cache-task",
) -> DirectoryInfo:
    return DirectoryInfo(
        cid=cid,
        parent_cid="root-cid",
        name=name,
        path=(DirectoryBreadcrumb("root-cid", "SakuraPlayer-Cache"),),
    )


def _status(factory, job_id: uuid.UUID) -> str:
    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        return job.status
