from __future__ import annotations

import time
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from sakuraplayer.resources.sync_service import BatchStats
from sakuraplayer.worker.__main__ import (
    CACHE_IDLE_WAIT_SECONDS,
    consume_avdb_requests,
    consume_cache_requests,
    consume_provider_snapshot_requests,
    run_worker,
)


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


class RecordingSnapshotConsumer:
    def __init__(self) -> None:
        self.worker_ids: list[str] = []
        self.results = ["completed", "idle"]

    def run_once(self, *, worker_id: str) -> str:
        self.worker_ids.append(worker_id)
        return self.results.pop(0)


def test_snapshot_consumer_loop_waits_only_when_idle() -> None:
    consumer = RecordingSnapshotConsumer()
    stop_event = StopAfterIdleWait()

    consume_provider_snapshot_requests(
        consumer=consumer,
        stop_event=stop_event,
        worker_id="worker-fixture",
        idle_wait_seconds=2.5,
    )

    assert consumer.worker_ids == ["worker-fixture", "worker-fixture"]
    assert stop_event.waits == [2.5]


def test_cache_consumer_loop_waits_only_when_idle() -> None:
    consumer = RecordingSnapshotConsumer()
    stop_event = StopAfterIdleWait()

    consume_cache_requests(
        consumer=consumer,
        stop_event=stop_event,
        worker_id="cache-worker",
    )

    assert consumer.worker_ids == ["cache-worker", "cache-worker"]
    assert stop_event.waits == [CACHE_IDLE_WAIT_SECONDS]


class RuntimeSeeder:
    def __init__(self) -> None:
        self.calls = 0

    def seed_once(self) -> None:
        self.calls += 1


class RuntimeSnapshotConsumer:
    def __init__(self) -> None:
        self.calls = 0

    def run_once(self, *, worker_id: str) -> str:
        assert worker_id == "worker-runtime"
        self.calls += 1
        return "idle"


class BlockingSeeder(RuntimeSeeder):
    def __init__(self) -> None:
        super().__init__()
        self.entered = Event()
        self.release = Event()

    def seed_once(self) -> None:
        super().seed_once()
        self.entered.set()
        self.release.wait(2)


class RuntimeSupervisor:
    def __init__(self, stop_event: Event) -> None:
        self.stop_event = stop_event
        self.ticks: list[str] = []
        self.shutdown_called = False

    def tick(self, *, worker_id: str) -> None:
        self.ticks.append(worker_id)
        self.stop_event.set()

    def shutdown(self) -> None:
        self.shutdown_called = True


class SignallingSupervisor(RuntimeSupervisor):
    def __init__(self, stop_event: Event) -> None:
        super().__init__(stop_event)
        self.ticked = Event()

    def tick(self, *, worker_id: str) -> None:
        self.ticks.append(worker_id)
        self.ticked.set()
        self.stop_event.set()


class RepeatingSupervisor(RuntimeSupervisor):
    def __init__(self, stop_event: Event, *, target_ticks: int) -> None:
        super().__init__(stop_event)
        self.target_ticks = target_ticks
        self.reached_target = Event()

    def tick(self, *, worker_id: str) -> None:
        self.ticks.append(worker_id)
        if len(self.ticks) >= self.target_ticks:
            self.reached_target.set()
            self.stop_event.set()


class FailingShutdownSupervisor(RuntimeSupervisor):
    def shutdown(self) -> None:
        self.shutdown_called = True
        raise RuntimeError("fixture shutdown failure")


class IdleConsumer:
    def run_once(self, *, worker_id: str, importer) -> str:
        del worker_id, importer
        return "idle"


class FailingConsumer:
    def run_once(self, *, worker_id: str, importer) -> str:
        del worker_id, importer
        raise RuntimeError("fixture consumer failure")


class DelayedStopConsumer:
    def __init__(self, stop_event: Event, delay: float) -> None:
        self.stop_event = stop_event
        self.delay = delay
        self.exited = Event()

    def run_once(self, *, worker_id: str, importer) -> str:
        del worker_id, importer
        self.stop_event.wait()
        time.sleep(self.delay)
        self.exited.set()
        return "idle"


class CoordinatedFailingConsumer:
    def __init__(self) -> None:
        self.release = Event()
        self.about_to_fail = Event()

    def run_once(self, *, worker_id: str, importer) -> str:
        del worker_id, importer
        self.release.wait(1)
        self.about_to_fail.set()
        raise RuntimeError("fixture background failure")


class CombinedFailureSupervisor(RuntimeSupervisor):
    def __init__(self, stop_event: Event, consumer: CoordinatedFailingConsumer) -> None:
        super().__init__(stop_event)
        self.consumer = consumer

    def tick(self, *, worker_id: str) -> None:
        self.ticks.append(worker_id)
        self.consumer.release.set()
        assert self.consumer.about_to_fail.wait(1)
        raise RuntimeError("fixture loop failure")

    def shutdown(self) -> None:
        self.shutdown_called = True
        raise RuntimeError("fixture shutdown failure")


class SlowStopSeeder(RuntimeSeeder):
    def __init__(self, stop_event: Event) -> None:
        super().__init__()
        self.stop_event = stop_event
        self.exited = Event()

    def seed_once(self) -> None:
        super().seed_once()
        self.stop_event.wait()
        time.sleep(0.1)
        self.exited.set()


def test_worker_runtime_polls_seeder_and_metadata_supervisor() -> None:
    stop_event = Event()
    seeder = RuntimeSeeder()
    snapshot_consumer = RuntimeSnapshotConsumer()
    cache_consumer = RuntimeSnapshotConsumer()
    supervisor = RuntimeSupervisor(stop_event)
    runtime = SimpleNamespace(
        consumer=IdleConsumer(),
        importer=RecordingImporter(),
        provider_snapshot_consumer=snapshot_consumer,
        metadata_seeder=seeder,
        metadata_supervisor=supervisor,
        cache_consumer=cache_consumer,
    )

    run_worker(
        runtime=runtime,  # type: ignore[arg-type]
        stop_event=stop_event,
        worker_id="worker-runtime",
    )

    assert seeder.calls == 1
    assert snapshot_consumer.calls == 1
    assert cache_consumer.calls == 1
    assert supervisor.ticks == ["worker-runtime"]
    assert supervisor.shutdown_called is True


def test_worker_propagates_avdb_thread_failure_after_supervisor_cleanup() -> None:
    stop_event = Event()
    seeder = RuntimeSeeder()
    supervisor = RuntimeSupervisor(stop_event)
    supervisor.tick = lambda *, worker_id: None  # type: ignore[method-assign]
    runtime = SimpleNamespace(
        consumer=FailingConsumer(),
        importer=RecordingImporter(),
        provider_snapshot_consumer=RuntimeSnapshotConsumer(),
        metadata_seeder=seeder,
        metadata_supervisor=supervisor,
    )

    with pytest.raises(RuntimeError, match="fixture consumer failure"):
        run_worker(
            runtime=runtime,  # type: ignore[arg-type]
            stop_event=stop_event,
            worker_id="worker-runtime",
        )

    assert supervisor.shutdown_called is True


def test_blocking_seeder_does_not_delay_supervisor_tick() -> None:
    stop_event = Event()
    seeder = BlockingSeeder()
    supervisor = RepeatingSupervisor(stop_event, target_ticks=3)
    runtime = SimpleNamespace(
        consumer=IdleConsumer(),
        importer=RecordingImporter(),
        provider_snapshot_consumer=RuntimeSnapshotConsumer(),
        metadata_seeder=seeder,
        metadata_supervisor=supervisor,
    )
    errors: list[BaseException] = []
    worker = Thread(
        target=lambda: _capture_worker_error(
            errors,
            runtime=runtime,
            stop_event=stop_event,
            supervisor_tick_seconds=0.01,
        )
    )
    worker.start()
    try:
        assert seeder.entered.wait(1)
        assert supervisor.reached_target.wait(0.25)
    finally:
        seeder.release.set()
        worker.join(2)

    assert not worker.is_alive()
    assert errors == []
    assert supervisor.ticks == ["worker-runtime"] * 3


def test_shutdown_failure_still_joins_the_avdb_thread() -> None:
    stop_event = Event()
    consumer = DelayedStopConsumer(stop_event, delay=0.05)
    supervisor = FailingShutdownSupervisor(stop_event)
    runtime = SimpleNamespace(
        consumer=consumer,
        importer=RecordingImporter(),
        provider_snapshot_consumer=RuntimeSnapshotConsumer(),
        metadata_seeder=RuntimeSeeder(),
        metadata_supervisor=supervisor,
    )

    with pytest.raises(RuntimeError, match="fixture shutdown failure"):
        run_worker(
            runtime=runtime,  # type: ignore[arg-type]
            stop_event=stop_event,
            worker_id="worker-runtime",
            thread_join_seconds=0.5,
        )

    assert consumer.exited.is_set()


def test_blocked_avdb_thread_has_a_bounded_shutdown() -> None:
    stop_event = Event()
    consumer = DelayedStopConsumer(stop_event, delay=0.1)
    supervisor = RuntimeSupervisor(stop_event)
    runtime = SimpleNamespace(
        consumer=consumer,
        importer=RecordingImporter(),
        provider_snapshot_consumer=RuntimeSnapshotConsumer(),
        metadata_seeder=RuntimeSeeder(),
        metadata_supervisor=supervisor,
    )

    with pytest.raises(RuntimeError, match="worker_thread_shutdown_timeout"):
        run_worker(
            runtime=runtime,  # type: ignore[arg-type]
            stop_event=stop_event,
            worker_id="worker-runtime",
            thread_join_seconds=0.01,
        )

    assert consumer.exited.wait(1)


def test_loop_error_wins_over_background_shutdown_and_join_timeout() -> None:
    stop_event = Event()
    consumer = CoordinatedFailingConsumer()
    seeder = SlowStopSeeder(stop_event)
    supervisor = CombinedFailureSupervisor(stop_event, consumer)
    runtime = SimpleNamespace(
        consumer=consumer,
        importer=RecordingImporter(),
        provider_snapshot_consumer=RuntimeSnapshotConsumer(),
        metadata_seeder=seeder,
        metadata_supervisor=supervisor,
    )

    with pytest.raises(RuntimeError, match="fixture loop failure"):
        run_worker(
            runtime=runtime,  # type: ignore[arg-type]
            stop_event=stop_event,
            worker_id="worker-runtime",
            thread_join_seconds=0.01,
            supervisor_tick_seconds=0.01,
        )

    assert supervisor.shutdown_called is True
    assert seeder.exited.wait(1)


def _capture_worker_error(
    errors,
    *,
    runtime,
    stop_event,
    supervisor_tick_seconds=1.0,
) -> None:
    try:
        run_worker(
            runtime=runtime,
            stop_event=stop_event,
            worker_id="worker-runtime",
            supervisor_tick_seconds=supervisor_tick_seconds,
        )
    except BaseException as error:
        errors.append(error)
