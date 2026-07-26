from __future__ import annotations

import argparse
from importlib import import_module
from importlib.util import find_spec
import os
import signal
from threading import Thread
from typing import Protocol
import uuid

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataClaim, MetadataQueue
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.catalog.metadata_state import (
    ALL_STAGES,
    MetadataStageExecutionError,
    validate_enrichment_stages,
)
from sakuraplayer.shared.redaction import stable_error_code
from sakuraplayer.shared.config import Settings, load_settings
from sakuraplayer.shared.runtime import guarded_main, require_ready


class StageExecutionFailure(MetadataStageExecutionError):
    def __init__(self, code: str) -> None:
        self.code = stable_error_code(code)
        super().__init__(self.code)


class MetadataStageExecutor(Protocol):
    def execute(self, stage: str, claim: MetadataClaim) -> None: ...


class MetadataChildQueue(Protocol):
    def start_stage(self, claim: MetadataClaim, stage_name: str) -> None: ...

    def finish_stage(
        self,
        claim: MetadataClaim,
        stage_name: str,
        *,
        status: str,
        failure_code: str | None = None,
    ) -> None: ...

    def is_core_ready(self, claim: MetadataClaim) -> bool: ...

    def complete(self, claim: MetadataClaim, *, with_warnings: bool) -> None: ...

    def fail(
        self,
        claim: MetadataClaim,
        *,
        code: str,
        detail: str,
    ) -> None: ...


class MetadataChildRunner:
    def __init__(
        self,
        *,
        queue: MetadataChildQueue,
        executor: MetadataStageExecutor,
    ) -> None:
        self._queue = queue
        self._executor = executor

    def run(self, claim: MetadataClaim) -> str:
        stages = self._stages_for(claim)
        if claim.retry_mode == "missing_enrichment" and not self._queue.is_core_ready(
            claim
        ):
            self._queue.fail(
                claim,
                code="metadata_core_not_committed",
                detail="metadata_core_not_committed",
            )
            return "failed"
        has_warnings = claim.has_warnings
        for stage in stages:
            self._queue.start_stage(claim, stage)
            try:
                self._executor.execute(stage, claim)
            except MetadataStageExecutionError as error:
                terminal_status = "failed" if stage == "javdb_core" else "warning"
                self._queue.finish_stage(
                    claim,
                    stage,
                    status=terminal_status,
                    failure_code=error.code,
                )
                if stage == "javdb_core":
                    self._queue.fail(
                        claim,
                        code=error.code,
                        detail=error.code,
                    )
                    return "failed"
                has_warnings = True
                continue
            except Exception:
                if stage != "javdb_core":
                    self._queue.finish_stage(
                        claim,
                        stage,
                        status="warning",
                        failure_code="metadata_optional_stage_failed",
                    )
                    has_warnings = True
                    continue
                self._queue.finish_stage(
                    claim,
                    stage,
                    status="failed",
                    failure_code="metadata_child_failed",
                )
                self._queue.fail(
                    claim,
                    code="metadata_child_failed",
                    detail="metadata_child_failed",
                )
                return "failed"
            if stage == "javdb_core" and not self._queue.is_core_ready(claim):
                self._queue.finish_stage(
                    claim,
                    stage,
                    status="failed",
                    failure_code="metadata_core_not_committed",
                )
                self._queue.fail(
                    claim,
                    code="metadata_core_not_committed",
                    detail="metadata_core_not_committed",
                )
                return "failed"
            self._queue.finish_stage(claim, stage, status="succeeded")
        self._queue.complete(claim, with_warnings=has_warnings)
        return "completed_with_warnings" if has_warnings else "completed"

    @staticmethod
    def _stages_for(claim: MetadataClaim) -> tuple[str, ...]:
        if claim.retry_mode == "full":
            if claim.requested_stages:
                raise ValueError("full metadata child cannot select stages")
            allowed = set(ALL_STAGES)
            if len(set(claim.pending_stages)) != len(claim.pending_stages) or any(
                stage not in allowed for stage in claim.pending_stages
            ):
                raise ValueError("invalid pending metadata stages")
            pending = set(claim.pending_stages)
            return tuple(stage for stage in ALL_STAGES if stage in pending)
        if claim.retry_mode == "missing_enrichment":
            requested = validate_enrichment_stages(claim.requested_stages)
            if any(stage not in requested for stage in claim.pending_stages):
                raise ValueError("invalid pending metadata stages")
            pending = set(claim.pending_stages)
            return tuple(stage for stage in requested if stage in pending)
        raise ValueError("invalid metadata child retry mode")


def metadata_executor_available() -> bool:
    try:
        return find_spec("sakuraplayer.catalog.providers.runtime") is not None
    except ModuleNotFoundError:
        return False


def start_parent_watchdog_from_environment() -> None:
    value = os.environ.pop("SAKURAPLAYER_PARENT_WATCH_FD", None)
    if value is None or os.name == "nt":
        return
    watch_fd = int(value)

    def watch() -> None:
        try:
            while os.read(watch_fd, 1):
                pass
        finally:
            os.close(watch_fd)
        os.killpg(os.getpgrp(), signal.SIGKILL)

    Thread(target=watch, name="metadata-parent-watch", daemon=True).start()


def run_child_process(
    *,
    settings: Settings,
    job_id: uuid.UUID,
    claim_owner: str,
) -> str:
    require_ready(settings)
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )
    http_client = httpx.Client(headers={"User-Agent": "SakuraPlayer/0.1"})
    try:
        factory = sessionmaker(engine, expire_on_commit=False)
        queue = MetadataQueue(factory, event_writer=DomainEventWriter())
        claim = queue.load_claim(job_id=job_id, claim_owner=claim_owner)
        runtime = import_module("sakuraplayer.catalog.providers.runtime")
        executor = runtime.build_metadata_stage_executor(
            settings=settings,
            session_factory=factory,
            http_client=http_client,
        )
        return MetadataChildRunner(queue=queue, executor=executor).run(claim)
    finally:
        http_client.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--job-id", required=True, type=uuid.UUID)
    parser.add_argument("--claim-owner", required=True)
    arguments = parser.parse_args()
    start_parent_watchdog_from_environment()
    run_child_process(
        settings=load_settings(),
        job_id=arguments.job_id,
        claim_owner=arguments.claim_owner,
    )


__all__ = [
    "MetadataChildRunner",
    "MetadataStageExecutor",
    "StageExecutionFailure",
    "metadata_executor_available",
    "run_child_process",
    "start_parent_watchdog_from_environment",
]


if __name__ == "__main__":
    guarded_main("metadata-child", main)
