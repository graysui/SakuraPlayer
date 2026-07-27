from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sakuraplayer.catalog.metadata_queue import MetadataClaim
from sakuraplayer.worker.metadata_child import (
    MetadataChildRunner,
    StageExecutionFailure,
)


class FakeQueue:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.finished: list[tuple[str, str, str | None]] = []
        self.completed: list[bool] = []
        self.failed: list[tuple[str, str]] = []
        self.core_ready = False

    def start_stage(self, claim: MetadataClaim, stage: str) -> None:
        del claim
        self.started.append(stage)

    def finish_stage(
        self,
        claim: MetadataClaim,
        stage: str,
        *,
        status: str,
        failure_code: str | None = None,
    ) -> None:
        del claim
        self.finished.append((stage, status, failure_code))

    def is_core_ready(self, claim: MetadataClaim) -> bool:
        del claim
        return self.core_ready

    def complete(self, claim: MetadataClaim, *, with_warnings: bool) -> None:
        del claim
        self.completed.append(with_warnings)

    def fail(
        self,
        claim: MetadataClaim,
        *,
        code: str,
        detail: str,
    ) -> None:
        del claim
        self.failed.append((code, detail))


class RecordingExecutor:
    def __init__(
        self,
        queue: FakeQueue,
        *,
        failures: dict[str, str] | None = None,
    ) -> None:
        self.queue = queue
        self.failures = failures or {}
        self.calls: list[str] = []

    def execute(self, stage: str, claim: MetadataClaim) -> None:
        del claim
        self.calls.append(stage)
        if stage == "javdb_core":
            self.queue.core_ready = True
        if stage in self.failures:
            raise StageExecutionFailure(self.failures[stage])


class UnexpectedOptionalFailureExecutor(RecordingExecutor):
    def execute(self, stage: str, claim: MetadataClaim) -> None:
        if stage == "gfriends":
            self.calls.append(stage)
            raise RuntimeError("fixture provider payload must not escape")
        super().execute(stage, claim)


def make_claim(
    *,
    retry_mode: str = "full",
    requested_stages: tuple[str, ...] = (),
    pending_stages: tuple[str, ...] | None = None,
    has_warnings: bool = False,
) -> MetadataClaim:
    if pending_stages is None:
        pending_stages = (
            ("javdb_core", "images", "dmm", "actor_map", "gfriends", "translation")
            if retry_mode == "full"
            else requested_stages
        )
    return MetadataClaim(
        job_id=uuid.uuid4(),
        movie_id=uuid.uuid4(),
        normalized_number="ABP-001",
        retry_mode=retry_mode,
        requested_stages=requested_stages,
        claim_owner="worker:claim",
        claim_expires_at=datetime(2026, 7, 25, 10, 1, tzinfo=timezone.utc),
        elapsed_ms=0,
        pending_stages=pending_stages,
        has_warnings=has_warnings,
    )


def test_full_attempt_commits_core_then_runs_all_optional_stages() -> None:
    queue = FakeQueue()
    executor = RecordingExecutor(queue)

    outcome = MetadataChildRunner(queue=queue, executor=executor).run(make_claim())

    assert outcome == "completed"
    assert executor.calls == [
        "javdb_core",
        "images",
        "dmm",
        "actor_map",
        "gfriends",
        "translation",
    ]
    assert queue.completed == [False]
    assert queue.failed == []


def test_optional_failures_become_warnings_without_rolling_back_core() -> None:
    queue = FakeQueue()
    executor = RecordingExecutor(
        queue,
        failures={"images": "image_download_failed", "dmm": "dmm_upstream_error"},
    )

    outcome = MetadataChildRunner(queue=queue, executor=executor).run(make_claim())

    assert outcome == "completed_with_warnings"
    assert queue.core_ready is True
    assert queue.completed == [True]
    assert ("images", "warning", "image_download_failed") in queue.finished
    assert ("dmm", "warning", "dmm_upstream_error") in queue.finished
    assert executor.calls[-1] == "translation"


def test_core_failure_stops_optional_work_and_persists_failed_job() -> None:
    queue = FakeQueue()
    executor = RecordingExecutor(
        queue,
        failures={"javdb_core": "javdb_upstream_error"},
    )

    outcome = MetadataChildRunner(queue=queue, executor=executor).run(make_claim())

    assert outcome == "failed"
    assert executor.calls == ["javdb_core"]
    assert queue.completed == []
    assert queue.failed == [("javdb_upstream_error", "javdb_upstream_error")]


def test_core_success_without_atomic_core_ready_is_rejected() -> None:
    queue = FakeQueue()
    executor = RecordingExecutor(queue)

    def execute_without_commit(stage: str, claim: MetadataClaim) -> None:
        del claim
        executor.calls.append(stage)

    executor.execute = execute_without_commit  # type: ignore[method-assign]

    outcome = MetadataChildRunner(queue=queue, executor=executor).run(make_claim())

    assert outcome == "failed"
    assert executor.calls == ["javdb_core"]
    assert queue.failed == [
        ("metadata_core_not_committed", "metadata_core_not_committed")
    ]


def test_enrichment_retry_runs_only_selected_stages_and_omits_paid_ai() -> None:
    queue = FakeQueue()
    queue.core_ready = True
    executor = RecordingExecutor(queue, failures={"images": "image_download_failed"})
    claim = make_claim(
        retry_mode="missing_enrichment",
        requested_stages=("images", "dmm"),
    )

    outcome = MetadataChildRunner(queue=queue, executor=executor).run(claim)

    assert outcome == "completed_with_warnings"
    assert executor.calls == ["images", "dmm"]
    assert "translation" not in executor.calls


def test_unexpected_optional_exception_is_a_redacted_warning() -> None:
    queue = FakeQueue()
    executor = UnexpectedOptionalFailureExecutor(queue)

    outcome = MetadataChildRunner(queue=queue, executor=executor).run(make_claim())

    assert outcome == "completed_with_warnings"
    assert ("gfriends", "warning", "metadata_optional_stage_failed") in queue.finished
    assert queue.failed == []


def test_recovered_attempt_skips_succeeded_stages_and_preserves_warnings() -> None:
    queue = FakeQueue()
    queue.core_ready = True
    executor = RecordingExecutor(queue)
    recovered = make_claim(
        pending_stages=("gfriends", "translation"),
        has_warnings=True,
    )

    outcome = MetadataChildRunner(queue=queue, executor=executor).run(recovered)

    assert executor.calls == ["gfriends", "translation"]
    assert outcome == "completed_with_warnings"
    assert queue.completed == [True]
