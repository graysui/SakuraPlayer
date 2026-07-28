from sakuraplayer.cloud_cache.recovery import CacheStartupRecovery


class PipelineStub:
    def __init__(self, outcomes: list[str]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def run_once(self, *, worker_id: str) -> str:
        self.calls.append(worker_id)
        return self.outcomes.pop(0)


def test_startup_recovery_stops_on_idle() -> None:
    pipeline = PipelineStub(["worked", "worked", "idle"])

    recovered = CacheStartupRecovery(pipeline, max_operations=100).run(
        worker_id="worker-1"
    )

    assert recovered == 2
    assert pipeline.calls == ["worker-1", "worker-1", "worker-1"]


def test_startup_recovery_is_bounded() -> None:
    pipeline = PipelineStub(["worked"] * 3)

    recovered = CacheStartupRecovery(pipeline, max_operations=3).run(
        worker_id="worker-1"
    )

    assert recovered == 3
    assert len(pipeline.calls) == 3
