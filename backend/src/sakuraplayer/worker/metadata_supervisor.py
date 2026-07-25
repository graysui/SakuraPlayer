from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import os
import signal
import subprocess
from time import monotonic
from typing import Callable, Mapping, Protocol, Sequence
import uuid

from sakuraplayer.catalog.metadata_queue import MetadataClaim, MetadataQueueProblem


MAX_METADATA_CHILDREN = 3
HARD_TIMEOUT_SECONDS = 600
CLAIM_LEASE = timedelta(seconds=30)


class MetadataQueuePort(Protocol):
    def claim_next(
        self,
        worker_id: str,
        *,
        lease_duration: timedelta,
    ) -> MetadataClaim | None: ...

    def renew(
        self,
        claim: MetadataClaim,
        *,
        lease_duration: timedelta,
    ) -> None: ...

    def is_claim_active(self, claim: MetadataClaim) -> bool: ...

    def fail(
        self,
        claim: MetadataClaim,
        *,
        code: str,
        detail: str,
    ) -> None: ...

    def fail_after_termination(
        self,
        claim: MetadataClaim,
        *,
        code: str,
        detail: str,
    ) -> None: ...

    def expire(self, claim: MetadataClaim) -> None: ...


class ChildProcess(Protocol):
    @property
    def pid(self) -> int: ...

    def poll(self) -> int | None: ...

    def terminate_group(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class ChildLauncher(Protocol):
    def is_available(self) -> bool: ...

    def start(self, claim: MetadataClaim) -> ChildProcess: ...


@dataclass(frozen=True)
class SupervisorSnapshot:
    running: int


@dataclass
class _RunningChild:
    claim: MetadataClaim
    process: ChildProcess
    started_at: float
    renewed_at: float


class SubprocessGroupProcess:
    def __init__(
        self,
        process: subprocess.Popen[bytes],
        *,
        parent_watch_fd: int | None = None,
    ) -> None:
        self._process = process
        self._parent_watch_fd = parent_watch_fd

    @property
    def pid(self) -> int:
        return self._process.pid

    def poll(self) -> int | None:
        return self._process.poll()

    def terminate_group(self) -> None:
        if os.name == "nt":
            if self._process.poll() is not None:
                return
            completed = subprocess.run(
                ["taskkill", "/PID", str(self.pid), "/T", "/F"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode not in {0, 128} and self._process.poll() is None:
                self._process.kill()
            return
        try:
            os.killpg(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            return

    def wait(self, timeout: float | None = None) -> int:
        result = self._process.wait(timeout=timeout)
        self._close_parent_watch()
        return result

    def _close_parent_watch(self) -> None:
        if self._parent_watch_fd is None:
            return
        os.close(self._parent_watch_fd)
        self._parent_watch_fd = None


class SubprocessGroupLauncher:
    def __init__(
        self,
        *,
        command_factory: Callable[[MetadataClaim], Sequence[str]],
        environment: Mapping[str, str] | None = None,
        availability: Callable[[], bool] | None = None,
    ) -> None:
        self._command_factory = command_factory
        self._environment = dict(environment) if environment is not None else None
        self._availability = availability or (lambda: True)

    def is_available(self) -> bool:
        return self._availability()

    def start(self, claim: MetadataClaim) -> SubprocessGroupProcess:
        command = tuple(self._command_factory(claim))
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("invalid metadata child command")
        environment = os.environ.copy()
        if self._environment is not None:
            environment.update(self._environment)
        kwargs: dict[str, object] = {
            "close_fds": True,
            "env": environment,
            "stdin": subprocess.DEVNULL,
        }
        parent_watch_read: int | None = None
        parent_watch_write: int | None = None
        if os.name == "nt":
            raise RuntimeError("metadata child launcher requires the Linux container runtime")
        else:
            parent_watch_read, parent_watch_write = os.pipe()
            os.set_inheritable(parent_watch_read, True)
            environment["SAKURAPLAYER_PARENT_WATCH_FD"] = str(parent_watch_read)
            kwargs["pass_fds"] = (parent_watch_read,)
            kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(command, **kwargs)
        except Exception:
            if parent_watch_read is not None:
                os.close(parent_watch_read)
            if parent_watch_write is not None:
                os.close(parent_watch_write)
            raise
        if parent_watch_read is not None:
            os.close(parent_watch_read)
        return SubprocessGroupProcess(
            process,
            parent_watch_fd=parent_watch_write,
        )


class MetadataSupervisor:
    def __init__(
        self,
        *,
        queue: MetadataQueuePort,
        launcher: ChildLauncher,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._queue = queue
        self._launcher = launcher
        self._clock = clock
        self._children: dict[uuid.UUID, _RunningChild] = {}

    def tick(self, *, worker_id: str) -> SupervisorSnapshot:
        current = self._clock()
        self._reap_finished()
        self._terminate_timed_out(current)
        self._renew_claims(current)
        self._fill_slots(worker_id, current)
        return SupervisorSnapshot(running=len(self._children))

    def shutdown(self) -> None:
        for job_id, child in tuple(self._children.items()):
            child.process.terminate_group()
            child.process.wait(timeout=5)
            try:
                self._queue.expire(child.claim)
            except MetadataQueueProblem as error:
                if error.code != "metadata_claim_lost":
                    raise
            del self._children[job_id]

    def _reap_finished(self) -> None:
        for job_id, child in tuple(self._children.items()):
            exit_code = child.process.poll()
            if exit_code is None:
                continue
            child.process.terminate_group()
            child.process.wait(timeout=0)
            code = (
                "metadata_child_incomplete"
                if exit_code == 0
                else "metadata_child_failed"
            )
            try:
                self._queue.fail(child.claim, code=code, detail=code)
            except MetadataQueueProblem as error:
                if error.code != "metadata_claim_lost":
                    raise
            del self._children[job_id]

    def _terminate_timed_out(self, current: float) -> None:
        for job_id, child in tuple(self._children.items()):
            if current - child.started_at < HARD_TIMEOUT_SECONDS:
                continue
            child.process.terminate_group()
            child.process.wait(timeout=5)
            try:
                self._queue.fail_after_termination(
                    child.claim,
                    code="metadata_timeout",
                    detail="metadata_timeout",
                )
            except MetadataQueueProblem as error:
                if error.code != "metadata_claim_lost":
                    raise
            del self._children[job_id]

    def _renew_claims(self, current: float) -> None:
        renew_interval = CLAIM_LEASE.total_seconds() / 2
        for job_id, child in tuple(self._children.items()):
            if current - child.renewed_at < renew_interval:
                continue
            try:
                self._queue.renew(child.claim, lease_duration=CLAIM_LEASE)
            except MetadataQueueProblem as error:
                if error.code != "metadata_claim_lost":
                    raise
                child.process.terminate_group()
                child.process.wait(timeout=5)
                del self._children[job_id]
                continue
            child.renewed_at = current

    def _fill_slots(self, worker_id: str, current: float) -> None:
        if not self._launcher.is_available():
            return
        while len(self._children) < MAX_METADATA_CHILDREN:
            claim = self._queue.claim_next(
                worker_id,
                lease_duration=CLAIM_LEASE,
            )
            if claim is None:
                return
            if claim.elapsed_ms >= HARD_TIMEOUT_SECONDS * 1000:
                self._queue.fail(
                    claim,
                    code="metadata_timeout",
                    detail="metadata_timeout",
                )
                continue
            try:
                process = self._launcher.start(claim)
            except Exception:
                self._queue.fail(
                    claim,
                    code="metadata_child_start_failed",
                    detail="metadata_child_start_failed",
                )
                continue
            consumed_seconds = claim.elapsed_ms / 1000
            self._children[claim.job_id] = _RunningChild(
                claim=claim,
                process=process,
                started_at=current - consumed_seconds,
                renewed_at=current,
            )


__all__ = [
    "HARD_TIMEOUT_SECONDS",
    "MAX_METADATA_CHILDREN",
    "MetadataSupervisor",
    "SubprocessGroupLauncher",
    "SubprocessGroupProcess",
    "SupervisorSnapshot",
]
