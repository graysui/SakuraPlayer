from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.cloud_cache.cancellation import (
    CacheCancelProblem,
    CancellationService,
)
from sakuraplayer.cloud_cache.models import CacheJob, CachePlayRequest, Cloud115Binding
from sakuraplayer.cloud_cache.play_request import PlayRequestService
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    OfflineStatus,
    OfflineSubmission,
    OfflineTaskPage,
    OfflineTaskSnapshot,
    RemoteDirectory,
)
from sakuraplayer.cloud_cache.source_rejection_client import SourceRejectionClient
from sakuraplayer.cloud_cache.worker.claim import CacheJobClaimLost, CacheJobClaimQueue
from sakuraplayer.cloud_cache.worker.offline import CacheOfflineWorker
from sakuraplayer.events.models import DomainEvent
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import ResourceSource, SourceRejection
from sakuraplayer.resources.rejection import SourceRejectionService
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import SourceSubmissionService
from tests.fakes.cloud115 import FakeCloud115

NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)


@pytest.fixture
def context(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'offline.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"k" * 32},
        )
    )
    secrets = EncryptedSettingRepository(factory, cipher, now=lambda: NOW)
    version = secrets.create_secret("cloud115.cookie", b"UID=fixture").version
    with factory.begin() as session:
        session.add(
            Cloud115Binding(
                id=uuid.uuid4(),
                singleton_key=True,
                account_key="account-fixture",
                display_name=None,
                cookie_setting_key="cloud115.cookie",
                login_app="alipaymini",
                cache_root_cid="root-fixture",
                status="active",
                credential_version=version,
                last_verified_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    SourceImporter(factory, cipher=cipher, now=lambda: NOW).import_batch(
        "fixture.zip", (_row(1), _row(2), _row(3))
    )
    source_port = SourceSubmissionService(factory, cipher=cipher)
    play = PlayRequestService(factory, source_port, now=lambda: NOW)
    try:
        yield factory, source_port, play
    finally:
        engine.dispose()


def test_submit_success_is_single_dispatch_and_completed_poll_enters_resolving(
    context,
) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    remote_hash = "a" * 40
    fake = FakeCloud115(
        directories=[
            RemoteDirectory("task-cid", "root-fixture", _task_name(factory, job_id))
        ],
        offline_submissions=[OfflineSubmission(remote_hash)],
        offline_pages=[_page(_snapshot(remote_hash, OfflineStatus.COMPLETED, 100.0))],
    )
    worker = _worker(factory, source_port, fake)

    assert worker.run_once(worker_id="worker-a") == "worked"
    assert _job(factory, job_id).status == "offlining"
    assert worker.run_once(worker_id="worker-a") == "worked"
    job = _job(factory, job_id)
    assert (job.status, float(job.remote_percent)) == ("resolving", 100.0)
    assert [call.operation for call in fake.calls].count("submit_offline") == 1
    assert "magnet:?xt=urn:btih:fixture-1" not in repr(fake.calls)
    with factory() as session:
        assert session.scalar(select(func.count(CachePlayRequest.idempotency_key))) == 1


def test_offline_reported_total_is_quota_not_task_count(context) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    remote_hash = "9" * 40
    _mark_offlining(factory, job_id, remote_hash)
    fake = FakeCloud115(
        offline_pages=[
            OfflineTaskPage(
                page=1,
                page_count=1,
                page_size=1000,
                total_tasks=1500,
                tasks=(_snapshot(remote_hash, OfflineStatus.COMPLETED, 100.0),),
            )
        ]
    )

    assert (
        _worker(factory, source_port, fake).run_once(worker_id="worker-a") == "worked"
    )
    job = _job(factory, job_id)
    assert (job.status, float(job.remote_percent)) == ("resolving", 100.0)


def test_poll_scopes_by_task_directory_ignoring_same_hash_elsewhere(context) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    remote_hash = "d" * 40
    _mark_offlining(factory, job_id, remote_hash)
    fake = FakeCloud115(
        offline_submissions=[OfflineSubmission(remote_hash)],
        offline_pages=[
            _page(
                _snapshot(
                    remote_hash, OfflineStatus.RUNNING, 5.0, task_cid="other-dir"
                ),
                _snapshot(remote_hash, OfflineStatus.COMPLETED, 100.0),
            )
        ],
    )
    worker = _worker(factory, source_port, fake)

    assert worker.run_once(worker_id="worker-a") == "worked"
    job = _job(factory, job_id)
    assert (job.status, float(job.remote_percent)) == ("resolving", 100.0)


@pytest.mark.parametrize("matched", [True, False])
def test_submit_uncertain_reconciles_without_automatic_resubmit(
    context, matched
) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    task_cid = "task-cid"
    remote_hash = "b" * 40
    fake = FakeCloud115(
        directories=[
            RemoteDirectory(task_cid, "root-fixture", _task_name(factory, job_id))
        ],
        offline_submissions=[Cloud115Problem("cloud115_submit_uncertain")],
        offline_pages=[
            _page(
                _snapshot(remote_hash, OfflineStatus.RUNNING, 20.0, task_cid=task_cid)
                if matched
                else None
            )
        ],
    )
    worker = _worker(factory, source_port, fake)

    assert worker.run_once(worker_id="worker-a") == "worked"
    job = _job(factory, job_id)
    assert job.status == ("offlining" if matched else "submit_uncertain")
    assert job.remote_info_hash == (remote_hash if matched else None)
    assert job.submit_started_at.replace(tzinfo=timezone.utc) == NOW
    assert [call.operation for call in fake.calls].count("submit_offline") == 1
    if not matched:
        assert worker.run_once(worker_id="worker-a") == "idle"
        assert [call.operation for call in fake.calls].count("submit_offline") == 1
        with factory() as session:
            movie_id, source_id = session.execute(
                select(ResourceSource.movie_id, ResourceSource.id).order_by(
                    ResourceSource.external_post_id
                )
            ).first()
        reused = play.create(
            movie_id=movie_id,
            source_id=source_id,
            idempotency_key=f"uncertain-reuse-{source_id.hex}",
        )
        assert reused.disposition == "reused"
        assert reused.job.id == job_id


@pytest.mark.parametrize(
    "scenario", ["inconsistent", "ambiguous", "page_size_mismatch"]
)
def test_submit_reconcile_rejects_inconsistent_or_ambiguous_pages(
    context, scenario
) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    tasks = (_snapshot("d" * 40, OfflineStatus.RUNNING, 10.0),)
    if scenario == "ambiguous":
        tasks += (_snapshot("e" * 40, OfflineStatus.RUNNING, 20.0),)
    if scenario == "page_size_mismatch":
        pages = [
            OfflineTaskPage(1, 2, 1000, 0, ()),
            OfflineTaskPage(2, 2, 999, 0, ()),
        ]
    elif scenario == "inconsistent":
        pages = [
            OfflineTaskPage(1, 2, 1000, 1500, ()),
            OfflineTaskPage(2, 3, 1000, 1500, ()),
        ]
    else:
        pages = [
            OfflineTaskPage(
                page=1,
                page_count=1,
                page_size=1000,
                total_tasks=2,
                tasks=tasks,
            )
        ]
    fake = FakeCloud115(
        directories=[
            RemoteDirectory("task-cid", "root-fixture", _task_name(factory, job_id))
        ],
        offline_submissions=[Cloud115Problem("cloud115_submit_uncertain")],
        offline_pages=pages,
    )

    assert (
        _worker(factory, source_port, fake).run_once(worker_id="worker-a") == "worked"
    )
    job = _job(factory, job_id)
    assert (job.status, job.failure_code) == ("failed", "cloud115_protocol_error")


@pytest.mark.parametrize(
    ("remote_status", "failure_code"),
    [
        (None, "cloud115_offline_task_not_found"),
        (OfflineStatus.FAILED, "cloud115_offline_failed"),
    ],
)
def test_poll_missing_or_failed_remote_task_is_deterministic(
    context, remote_status, failure_code
) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    remote_hash = "f" * 40
    _mark_offlining(factory, job_id, remote_hash)
    snapshot = (
        _snapshot(remote_hash, remote_status, 30.0)
        if remote_status is not None
        else None
    )
    fake = FakeCloud115(offline_pages=[_page(snapshot)])

    assert (
        _worker(factory, source_port, fake).run_once(worker_id="worker-a") == "worked"
    )
    job = _job(factory, job_id)
    assert (job.status, job.failure_code) == ("failed", failure_code)
    with factory() as session:
        source = session.get(ResourceSource, job.source_id)
        assert source is not None and source.identification_status == "identified"
        assert source.magnet_envelope is not None
        assert session.scalar(select(func.count(SourceRejection.id))) == 0
        movie_id = source.movie_id
        assert movie_id is not None
    retried = play.create(
        movie_id=movie_id,
        source_id=job.source_id,
        idempotency_key=f"manual-retry-{job.source_id.hex}-{failure_code}",
    )
    assert retried.disposition == "started"
    assert retried.job.id != job_id


def test_precise_submit_failure_rejects_source_and_writes_one_safe_event(
    context,
) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    fake = FakeCloud115(
        directories=[
            RemoteDirectory("task-cid", "root-fixture", _task_name(factory, job_id))
        ],
        offline_submissions=[Cloud115Problem("cloud115_source_unavailable")],
    )

    assert (
        _worker(factory, source_port, fake).run_once(worker_id="worker-a") == "worked"
    )

    job = _job(factory, job_id)
    with factory() as session:
        source = session.get(ResourceSource, job.source_id)
        rejection = session.scalar(select(SourceRejection))
        events = tuple(session.scalars(select(DomainEvent)))
    assert (job.status, job.failure_code) == (
        "failed",
        "cloud115_source_unavailable",
    )
    assert source is not None and source.identification_status == "rejected"
    assert source.magnet_envelope is None
    assert rejection is not None
    assert rejection.reason_code == "cloud115_source_unavailable"
    assert len(events) == 1
    assert events[0].event_type == "cache.job.failed.v1"
    assert events[0].payload == {
        "id": str(job_id),
        "status": "failed",
        "error_code": "cloud115_source_unavailable",
        "rejected_source": True,
    }
    assert "magnet" not in repr(events[0].payload).lower()


def test_crash_after_rejection_reclaims_and_converges_without_cloud_replay(
    context,
) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    clock = {"now": NOW}
    fake = FakeCloud115(
        directories=[
            RemoteDirectory("task-cid", "root-fixture", _task_name(factory, job_id))
        ],
        offline_submissions=[Cloud115Problem("cloud115_source_unavailable")],
    )

    class CrashAfterRejectionQueue(CacheJobClaimQueue):
        def fail_rejected(self, claim, code) -> None:
            del claim, code
            raise RuntimeError("simulated process exit")

    def worker(queue, cloud):
        @asynccontextmanager
        async def cloud_scope(_claim):
            yield cloud

        return CacheOfflineWorker(
            queue,
            source_port,
            SourceRejectionClient(
                source_port,
                SourceRejectionService(factory, now=lambda: clock["now"]),
            ),
            cloud_scope,
            now=lambda: clock["now"],
        )

    with pytest.raises(RuntimeError, match="simulated process exit"):
        worker(
            CrashAfterRejectionQueue(factory, now=lambda: clock["now"]),
            fake,
        ).run_once(worker_id="crashing-worker")

    with factory() as session:
        job = session.get(CacheJob, job_id)
        source = session.get(ResourceSource, job.source_id if job is not None else None)
        assert job is not None and job.status == "submitting"
        assert job.claim_owner == "crashing-worker"
        assert source is not None and source.magnet_envelope is None
        assert session.scalar(select(func.count(SourceRejection.id))) == 1
        assert session.scalar(select(func.count(DomainEvent.event_id))) == 0

    clock["now"] += timedelta(seconds=91)
    replay_cloud = FakeCloud115()
    replay = worker(
        CacheJobClaimQueue(factory, now=lambda: clock["now"]),
        replay_cloud,
    )
    assert replay.run_once(worker_id="recovery-worker") == "worked"
    assert replay.run_once(worker_id="recovery-worker") == "idle"

    job = _job(factory, job_id)
    with factory() as session:
        assert session.scalar(select(func.count(SourceRejection.id))) == 1
        assert session.scalar(select(func.count(DomainEvent.event_id))) == 1
    assert (job.status, job.failure_code) == (
        "failed",
        "cloud115_source_unavailable",
    )
    assert replay_cloud.calls == []


def test_running_remote_task_uses_updated_at_as_poll_backoff(context) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    remote_hash = "9" * 40
    _mark_offlining(factory, job_id, remote_hash)
    fake = FakeCloud115(
        offline_pages=[
            _page(_snapshot(remote_hash, OfflineStatus.RUNNING, 45.0)),
            _page(_snapshot(remote_hash, OfflineStatus.RUNNING, 50.0)),
        ]
    )
    clock = {"now": NOW}
    worker = _worker(factory, source_port, fake, now=lambda: clock["now"])

    assert worker.run_once(worker_id="worker-a") == "worked"
    job = _job(factory, job_id)
    assert (job.status, float(job.remote_percent)) == ("offlining", 45.0)
    assert job.claim_expires_at.replace(tzinfo=timezone.utc) == NOW + timedelta(
        seconds=90
    )
    clock["now"] += timedelta(seconds=1)
    assert worker.run_once(worker_id="worker-b") == "idle"
    clock["now"] += timedelta(seconds=1)
    assert worker.run_once(worker_id="worker-b") == "worked"


@pytest.mark.parametrize(
    ("problem", "delay_seconds"),
    [
        (Cloud115Problem("cloud115_unavailable"), 5),
        (Cloud115Problem("cloud115_rate_limited", retry_after_seconds=17), 17),
    ],
)
def test_transient_cloud_problem_defers_without_state_change(
    context, problem, delay_seconds
) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    fake = FakeCloud115(directories=[problem])
    worker = _worker(factory, source_port, fake)

    assert worker.run_once(worker_id="worker-a") == "worked"
    job = _job(factory, job_id)
    assert (job.status, job.failure_code) == ("submitting", problem.code)
    assert job.claim_expires_at.replace(tzinfo=timezone.utc) == NOW + timedelta(
        seconds=delay_seconds
    )
    assert worker.run_once(worker_id="worker-b") == "idle"


def test_cancel_not_found_is_idempotent_and_enters_cleaning(context) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    _mark_offlining(factory, job_id, "a" * 40)
    CancellationService(factory, now=lambda: NOW).request(job_id, confirmed=True)
    fake = FakeCloud115(
        cancel_results=[Cloud115Problem("cloud115_offline_task_not_found")]
    )

    assert (
        _worker(factory, source_port, fake).run_once(worker_id="worker-a") == "worked"
    )
    assert _job(factory, job_id).status == "cleaning"


def test_cancel_during_claimed_mkdir_records_directory_before_cleaning(context) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    cancellation = CancellationService(factory, now=lambda: NOW)

    class CancelDuringMkdir(FakeCloud115):
        async def find_or_create_directory(self, parent_cid, name):
            result = cancellation.request(job_id, confirmed=True)
            assert result.status == "cancelling"
            return await super().find_or_create_directory(parent_cid, name)

    fake = CancelDuringMkdir(
        directories=[
            RemoteDirectory("task-cid", "root-fixture", _task_name(factory, job_id))
        ]
    )

    assert (
        _worker(factory, source_port, fake).run_once(worker_id="worker-a") == "worked"
    )
    job = _job(factory, job_id)
    assert (job.status, job.task_dir_cid) == ("cleaning", "task-cid")
    assert "submit_offline" not in [call.operation for call in fake.calls]


def test_uncertain_cancel_without_match_converges_to_cleaning(context) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    fake = FakeCloud115(
        directories=[
            RemoteDirectory("task-cid", "root-fixture", _task_name(factory, job_id))
        ],
        offline_submissions=[Cloud115Problem("cloud115_submit_uncertain")],
        offline_pages=[_page(None), _page(None)],
    )
    worker = _worker(factory, source_port, fake)
    assert worker.run_once(worker_id="worker-a") == "worked"
    CancellationService(factory, now=lambda: NOW).request(job_id, confirmed=True)

    assert worker.run_once(worker_id="worker-a") == "worked"
    job = _job(factory, job_id)
    # REQ-CHG-330: 确认取消后取消必须收敛，进入受管清理而非回到 submit_uncertain。
    assert (job.status, job.cleanup_reason) == ("cleaning", "cancelled")
    assert [call.operation for call in fake.calls].count("submit_offline") == 1
    assert "cancel_offline" not in [call.operation for call in fake.calls]
    # 收敛后任务不再被自动 worker 领取，运行名额释放。
    assert worker.run_once(worker_id="worker-a") == "idle"
    assert _job(factory, job_id).status == "cleaning"


def test_uncertain_cancel_with_match_cancels_remote_then_cleans(context) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    remote_hash = "c" * 40
    fake = FakeCloud115(
        directories=[
            RemoteDirectory("task-cid", "root-fixture", _task_name(factory, job_id))
        ],
        offline_submissions=[Cloud115Problem("cloud115_submit_uncertain")],
        offline_pages=[
            _page(None),
            _page(_snapshot(remote_hash, OfflineStatus.RUNNING, 10.0)),
        ],
        cancel_results=[None],
    )
    worker = _worker(factory, source_port, fake)
    assert worker.run_once(worker_id="worker-a") == "worked"
    CancellationService(factory, now=lambda: NOW).request(job_id, confirmed=True)

    assert worker.run_once(worker_id="worker-a") == "worked"
    job = _job(factory, job_id)
    assert (job.status, job.cleanup_reason) == ("cleaning", "cancelled")
    assert fake.calls[-1].operation == "cancel_offline"


def test_expired_claim_is_fenced_from_late_worker_write(context) -> None:
    factory, _, play = context
    _create_started(factory, play)
    clock = {"now": NOW}
    queue = CacheJobClaimQueue(
        factory, now=lambda: clock["now"], lease=timedelta(seconds=30)
    )
    old = queue.claim_next(worker_id="old-worker")
    assert old is not None
    clock["now"] += timedelta(seconds=31)
    replacement = queue.claim_next(worker_id="new-worker")
    assert replacement is not None and replacement.claim_token != old.claim_token

    with pytest.raises(CacheJobClaimLost):
        queue.save_task_directory(old, "late-directory")


def test_cancel_requires_confirmation_and_hands_remote_cleanup_to_task_107(
    context,
) -> None:
    factory, source_port, play = context
    job_id = _create_started(factory, play)
    with factory.begin() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        job.status = "offlining"
        job.task_dir_cid = "task-cid"
        job.submit_started_at = NOW
        job.remote_info_hash = "c" * 40
    cancellation = CancellationService(factory, now=lambda: NOW)
    with pytest.raises(CacheCancelProblem) as error:
        cancellation.request(job_id, confirmed=False)
    assert error.value.code == "cache_cancel_confirmation_required"

    assert cancellation.request(job_id, confirmed=True).status == "cancelling"
    fake = FakeCloud115(cancel_results=[None])
    worker = _worker(factory, source_port, fake)
    assert worker.run_once(worker_id="worker-a") == "worked"
    assert _job(factory, job_id).status == "cleaning"
    assert fake.calls[-1].operation == "cancel_offline"


def _worker(factory, source_port, fake, *, now=lambda: NOW):
    @asynccontextmanager
    async def cloud_scope(_claim):
        yield fake

    return CacheOfflineWorker(
        CacheJobClaimQueue(factory, now=now),
        source_port,
        SourceRejectionClient(
            source_port,
            SourceRejectionService(factory, now=lambda: NOW),
        ),
        cloud_scope,
        now=now,
    )


def _create_started(factory, play) -> uuid.UUID:
    with factory() as session:
        movie_id, source_id = session.execute(
            select(ResourceSource.movie_id, ResourceSource.id).order_by(
                ResourceSource.external_post_id
            )
        ).first()
    result = play.create(
        movie_id=movie_id,
        source_id=source_id,
        idempotency_key=f"offline-test-{source_id.hex}",
    )
    assert result.disposition == "started"
    return result.job.id


def _job(factory, job_id):
    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        session.expunge(job)
        return job


def _task_name(factory, job_id) -> str:
    return _job(factory, job_id).task_dir_name


def _mark_offlining(factory, job_id, remote_hash: str) -> None:
    with factory.begin() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        job.status = "offlining"
        job.task_dir_cid = "task-cid"
        job.submit_started_at = NOW
        job.remote_info_hash = remote_hash


def _snapshot(
    info_hash: str,
    status: OfflineStatus,
    percent: float,
    *,
    task_cid: str = "task-cid",
) -> OfflineTaskSnapshot:
    return OfflineTaskSnapshot(
        info_hash=info_hash,
        name="fixture",
        size_bytes=1,
        status=status,
        percent_done=percent,
        task_cid=task_cid,
    )


def _page(*snapshots: OfflineTaskSnapshot | None) -> OfflineTaskPage:
    tasks = tuple(snapshot for snapshot in snapshots if snapshot is not None)
    return OfflineTaskPage(
        page=1,
        page_count=1,
        page_size=1000,
        total_tasks=len(tasks),
        tasks=tasks,
    )


def _row(index: int) -> dict[str, object]:
    return {
        "tid": index,
        "number": f"IPX-{index:03d}",
        "title": f"Title {index}",
        "publish_date": date(2026, 7, 27),
        "magnet": f"magnet:?xt=urn:btih:fixture-{index}",
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/thread-fixture.htm",
        "size": 1024,
        "section": "亚洲有码",
        "category": None,
        "website": "sehuatang",
        "create_time": NOW,
        "update_time": NOW,
    }
