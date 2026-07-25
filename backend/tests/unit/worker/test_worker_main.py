from __future__ import annotations

from sakuraplayer.resources.sync_service import BatchStats
from sakuraplayer.worker.__main__ import consume_avdb_requests


class StopAfterIdleWait:
    def __init__(self) -> None:
        self.stopped = False
        self.waits: list[float] = []

    def is_set(self) -> bool:
        return self.stopped

    def wait(self, timeout: float) -> bool:
        self.waits.append(timeout)
        self.stopped = True
        return True


class RecordingImporter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[dict[str, object], ...]]] = []

    def import_batch(
        self,
        asset_name: str,
        rows: tuple[dict[str, object], ...],
    ) -> BatchStats:
        self.calls.append((asset_name, rows))
        return BatchStats(inserted=len(rows))


class RecordingConsumer:
    def __init__(self) -> None:
        self.worker_ids: list[str] = []
        self.results = ["completed", "idle"]

    def run_once(self, *, worker_id: str, importer) -> str:
        self.worker_ids.append(worker_id)
        result = importer("fixture.zip", ({"tid": len(self.worker_ids)},))
        assert result == BatchStats(inserted=1)
        return self.results.pop(0)


def test_consumer_loop_injects_importer_and_waits_only_when_idle() -> None:
    consumer = RecordingConsumer()
    importer = RecordingImporter()
    stop_event = StopAfterIdleWait()

    consume_avdb_requests(
        consumer=consumer,
        importer=importer,
        stop_event=stop_event,
        worker_id="worker-fixture",
        idle_wait_seconds=2.5,
    )

    assert consumer.worker_ids == ["worker-fixture", "worker-fixture"]
    assert [call[0] for call in importer.calls] == ["fixture.zip", "fixture.zip"]
    assert stop_event.waits == [2.5]
