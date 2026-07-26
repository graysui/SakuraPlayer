from datetime import datetime, timedelta, timezone
import time
import uuid

from sakuraplayer.catalog.provider_snapshots import (
    ProviderSnapshotClaim,
    ProviderSnapshotRefreshOutcome,
)
from sakuraplayer.worker.provider_snapshots import ProviderSnapshotConsumer


class RecordingQueue:
    def __init__(self, claim: ProviderSnapshotClaim | None) -> None:
        self.claim = claim
        self.claim_calls: list[tuple[str, timedelta]] = []
        self.renew_calls = 0
        self.completed: list[ProviderSnapshotClaim] = []
        self.failed: list[tuple[ProviderSnapshotClaim, str]] = []

    def claim_next(self, worker_id: str, *, lease_duration: timedelta):
        self.claim_calls.append((worker_id, lease_duration))
        claim, self.claim = self.claim, None
        return claim

    def renew(self, claim: ProviderSnapshotClaim, *, lease_duration: timedelta) -> None:
        assert claim is not None and lease_duration > timedelta(0)
        self.renew_calls += 1

    def complete(self, claim: ProviderSnapshotClaim) -> None:
        self.completed.append(claim)

    def fail(self, claim: ProviderSnapshotClaim, *, code: str) -> None:
        self.failed.append((claim, code))


class RecordingService:
    def __init__(
        self,
        outcome: ProviderSnapshotRefreshOutcome | None = None,
        *,
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.outcome = outcome
        self.error = error
        self.delay = delay
        self.calls = 0

    def refresh_all(self) -> ProviderSnapshotRefreshOutcome:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        assert self.outcome is not None
        return self.outcome


def _claim() -> ProviderSnapshotClaim:
    return ProviderSnapshotClaim(
        request_id=uuid.uuid4(),
        claim_owner="worker-1",
        claim_token=uuid.uuid4(),
        claim_expires_at=datetime(2026, 7, 26, 22, 0, tzinfo=timezone.utc),
    )


def test_provider_snapshot_consumer_returns_idle_without_request() -> None:
    queue = RecordingQueue(None)
    service = RecordingService(
        ProviderSnapshotRefreshOutcome(snapshot_ids=(), failures=())
    )

    result = ProviderSnapshotConsumer(queue=queue, service=service).run_once(
        worker_id="worker-1"
    )

    assert result == "idle"
    assert service.calls == 0


def test_provider_snapshot_consumer_renews_and_completes_success() -> None:
    claim = _claim()
    queue = RecordingQueue(claim)
    service = RecordingService(
        ProviderSnapshotRefreshOutcome(
            snapshot_ids=(("actor_mapping", uuid.uuid4()),),
            failures=(),
        ),
        delay=0.04,
    )
    consumer = ProviderSnapshotConsumer(
        queue=queue,
        service=service,
        request_lease_duration=timedelta(milliseconds=100),
        heartbeat_interval=timedelta(milliseconds=10),
    )

    result = consumer.run_once(worker_id="worker-1")

    assert result == "completed"
    assert queue.renew_calls >= 1
    assert queue.completed == [claim]
    assert queue.failed == []


def test_provider_snapshot_consumer_persists_source_failure_without_retry() -> None:
    claim = _claim()
    queue = RecordingQueue(claim)
    service = RecordingService(
        ProviderSnapshotRefreshOutcome(
            snapshot_ids=(("gfriends", uuid.uuid4()),),
            failures=(("actor_mapping", "provider_snapshot_invalid"),),
        )
    )

    result = ProviderSnapshotConsumer(queue=queue, service=service).run_once(
        worker_id="worker-1"
    )

    assert result == "failed"
    assert queue.completed == []
    assert queue.failed == [(claim, "provider_snapshot_invalid")]
    assert queue.claim_calls == [("worker-1", timedelta(minutes=30))]


def test_provider_snapshot_consumer_redacts_unexpected_failure() -> None:
    claim = _claim()
    queue = RecordingQueue(claim)
    service = RecordingService(error=RuntimeError("secret https://x/?token=y"))

    result = ProviderSnapshotConsumer(queue=queue, service=service).run_once(
        worker_id="worker-1"
    )

    assert result == "failed"
    assert queue.failed == [(claim, "internal_error")]
