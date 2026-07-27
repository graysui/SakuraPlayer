import time
import uuid
from datetime import datetime, timedelta, timezone

from sakuraplayer.discovery.ranking_sync import RankingClaim
from sakuraplayer.worker.rankings import RankingConsumer


class RecordingQueue:
    def __init__(self, claim: RankingClaim | None) -> None:
        self.claim = claim
        self.renew_calls = 0
        self.failed: list[tuple[RankingClaim, str]] = []

    def claim_next(self, worker_id: str, *, lease_duration: timedelta):
        del worker_id, lease_duration
        claim, self.claim = self.claim, None
        return claim

    def renew(self, claim: RankingClaim, *, lease_duration: timedelta) -> None:
        assert claim is not None and lease_duration > timedelta(0)
        self.renew_calls += 1

    def fail(self, claim: RankingClaim, *, code: str) -> None:
        self.failed.append((claim, code))


class RecordingSynchronizer:
    def __init__(self, *, error: Exception | None = None, delay: float = 0) -> None:
        self.error = error
        self.delay = delay
        self.calls = 0

    def synchronize(self, claim: RankingClaim, *, before_activate) -> uuid.UUID:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        before_activate()
        assert claim.board == "daily"
        return uuid.uuid4()


def _claim() -> RankingClaim:
    return RankingClaim(
        request_id=uuid.uuid4(),
        board="daily",
        year=None,
        claim_owner="worker-1",
        claim_token=uuid.uuid4(),
        claim_expires_at=datetime(2026, 7, 26, 22, 0, tzinfo=timezone.utc),
    )


def test_ranking_consumer_is_idle_without_request() -> None:
    sync = RecordingSynchronizer()

    result = RankingConsumer(
        queue=RecordingQueue(None),
        synchronizer=sync,
    ).run_once(worker_id="worker-1")

    assert result == "idle"
    assert sync.calls == 0


def test_ranking_consumer_renews_then_activates_snapshot() -> None:
    claim = _claim()
    queue = RecordingQueue(claim)
    consumer = RankingConsumer(
        queue=queue,
        synchronizer=RecordingSynchronizer(delay=0.04),
        request_lease_duration=timedelta(milliseconds=100),
        heartbeat_interval=timedelta(milliseconds=10),
    )

    result = consumer.run_once(worker_id="worker-1")

    assert result == "completed"
    assert queue.renew_calls >= 1
    assert queue.failed == []


def test_ranking_consumer_persists_only_stable_failure_code() -> None:
    claim = _claim()
    queue = RecordingQueue(claim)
    consumer = RankingConsumer(
        queue=queue,
        synchronizer=RecordingSynchronizer(
            error=RuntimeError("secret https://x/?token=y")
        ),
    )

    result = consumer.run_once(worker_id="worker-1")

    assert result == "failed"
    assert queue.failed == [(claim, "internal_error")]
