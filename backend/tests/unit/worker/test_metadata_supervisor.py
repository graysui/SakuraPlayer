from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sakuraplayer.catalog.metadata_queue import MetadataClaim, MetadataQueueProblem
from sakuraplayer.worker.metadata_supervisor import (
    HARD_TIMEOUT_SECONDS,
    MAX_METADATA_CHILDREN,
    MetadataSupervisor,
    SubprocessGroupLauncher,
)

NOW = datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc)


@dataclass
class FakeClock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value


class FakeProcess:
    def __init__(self) -> None:
        self.exit_code: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate_group(self) -> None:
        self.terminated = True
        self.exit_code = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        assert self.exit_code is not None
        return self.exit_code


class FakeLauncher:
    def __init__(self) -> None:
        self.processes: dict[uuid.UUID, FakeProcess] = {}
        self.available = True

    def is_available(self) -> bool:
        return self.available

    def start(self, claim: MetadataClaim) -> FakeProcess:
        process = FakeProcess()
        self.processes[claim.job_id] = process
        return process


class FailingLauncher(FakeLauncher):
    def __init__(self) -> None:
        super().__init__()
        self.failed_once = False

    def start(self, item: MetadataClaim) -> FakeProcess:
        if not self.failed_once:
            self.failed_once = True
            raise OSError("fixture start failure")
        return super().start(item)


class FakeQueue:
    def __init__(self, count: int) -> None:
        self.claims = [claim(index) for index in range(count)]
        self.active: set[uuid.UUID] = set()
        self.failed: list[tuple[uuid.UUID, str]] = []
        self.renewed: list[uuid.UUID] = []
        self.expired: list[uuid.UUID] = []
        self.lose_on_renew = False
        self.lose_on_expire = False
        self.lose_on_fail = False

    def claim_next(
        self,
        worker_id: str,
        *,
        lease_duration: timedelta,
    ) -> MetadataClaim | None:
        assert worker_id == "worker-fixture"
        assert lease_duration > timedelta(0)
        if not self.claims:
            return None
        item = self.claims.pop(0)
        self.active.add(item.job_id)
        return item

    def renew(self, item: MetadataClaim, *, lease_duration: timedelta) -> None:
        assert item.job_id in self.active
        assert lease_duration > timedelta(0)
        if self.lose_on_renew:
            self.active.discard(item.job_id)
            raise MetadataQueueProblem(status_code=409, code="metadata_claim_lost")
        self.renewed.append(item.job_id)

    def is_claim_active(self, item: MetadataClaim) -> bool:
        return item.job_id in self.active

    def fail(self, item: MetadataClaim, *, code: str, detail: str) -> None:
        assert detail == code
        if self.lose_on_fail or item.job_id not in self.active:
            self.active.discard(item.job_id)
            raise MetadataQueueProblem(status_code=409, code="metadata_claim_lost")
        self.active.discard(item.job_id)
        self.failed.append((item.job_id, code))

    def fail_after_termination(
        self,
        item: MetadataClaim,
        *,
        code: str,
        detail: str,
    ) -> None:
        self.fail(item, code=code, detail=detail)

    def expire(self, item: MetadataClaim) -> None:
        if self.lose_on_expire:
            self.active.discard(item.job_id)
            raise MetadataQueueProblem(status_code=409, code="metadata_claim_lost")
        self.active.discard(item.job_id)
        self.expired.append(item.job_id)


def claim(index: int) -> MetadataClaim:
    job_id = uuid.UUID(int=index + 1)
    return MetadataClaim(
        job_id=job_id,
        movie_id=uuid.UUID(int=100 + index),
        normalized_number=f"ABP-{index:03d}",
        retry_mode="full",
        requested_stages=(),
        claim_owner=f"worker-fixture:{job_id}",
        claim_expires_at=NOW + timedelta(minutes=1),
        elapsed_ms=0,
        pending_stages=(
            "javdb_core",
            "images",
            "dmm",
            "actor_map",
            "gfriends",
            "translation",
        ),
        has_warnings=False,
    )


def elapsed_claim(index: int, *, elapsed_ms: int) -> MetadataClaim:
    item = claim(index)
    return MetadataClaim(
        job_id=item.job_id,
        movie_id=item.movie_id,
        normalized_number=item.normalized_number,
        retry_mode=item.retry_mode,
        requested_stages=item.requested_stages,
        claim_owner=item.claim_owner,
        claim_expires_at=item.claim_expires_at,
        elapsed_ms=elapsed_ms,
        pending_stages=item.pending_stages,
        has_warnings=item.has_warnings,
    )


def test_supervisor_never_starts_more_than_three_children() -> None:
    queue = FakeQueue(5)
    launcher = FakeLauncher()
    clock = FakeClock()
    supervisor = MetadataSupervisor(queue=queue, launcher=launcher, clock=clock)

    snapshot = supervisor.tick(worker_id="worker-fixture")

    assert MAX_METADATA_CHILDREN == 3
    assert snapshot.running == 3
    assert len(launcher.processes) == 3
    assert len(queue.claims) == 2


def test_unavailable_executor_keeps_persistent_jobs_queued() -> None:
    queue = FakeQueue(2)
    launcher = FakeLauncher()
    launcher.available = False
    supervisor = MetadataSupervisor(queue=queue, launcher=launcher, clock=FakeClock())

    snapshot = supervisor.tick(worker_id="worker-fixture")

    assert snapshot.running == 0
    assert len(queue.claims) == 2


def test_exact_600_second_boundary_terminates_groups_and_persists_failure() -> None:
    queue = FakeQueue(3)
    launcher = FakeLauncher()
    clock = FakeClock()
    supervisor = MetadataSupervisor(queue=queue, launcher=launcher, clock=clock)
    supervisor.tick(worker_id="worker-fixture")

    clock.value = HARD_TIMEOUT_SECONDS - 0.001
    before = supervisor.tick(worker_id="worker-fixture")
    assert before.running == 3
    assert not queue.failed

    clock.value = HARD_TIMEOUT_SECONDS
    after = supervisor.tick(worker_id="worker-fixture")

    assert HARD_TIMEOUT_SECONDS == 600
    assert after.running == 0
    assert all(process.terminated for process in launcher.processes.values())
    assert [code for _, code in queue.failed] == ["metadata_timeout"] * 3


def test_child_exit_cannot_silently_leave_a_running_job() -> None:
    queue = FakeQueue(1)
    launcher = FakeLauncher()
    supervisor = MetadataSupervisor(
        queue=queue,
        launcher=launcher,
        clock=FakeClock(),
    )
    supervisor.tick(worker_id="worker-fixture")
    process = next(iter(launcher.processes.values()))
    process.exit_code = 0

    snapshot = supervisor.tick(worker_id="worker-fixture")

    assert snapshot.running == 0
    assert queue.failed == [
        (next(iter(launcher.processes)), "metadata_child_incomplete")
    ]


def test_completed_child_is_reaped_without_creating_an_attempt() -> None:
    queue = FakeQueue(1)
    launcher = FakeLauncher()
    supervisor = MetadataSupervisor(
        queue=queue,
        launcher=launcher,
        clock=FakeClock(),
    )
    supervisor.tick(worker_id="worker-fixture")
    job_id, process = next(iter(launcher.processes.items()))
    queue.active.remove(job_id)
    process.exit_code = 0

    snapshot = supervisor.tick(worker_id="worker-fixture")

    assert snapshot.running == 0
    assert queue.failed == []
    assert queue.claims == []


def test_claim_lost_while_reaping_does_not_stop_the_supervisor() -> None:
    queue = FakeQueue(1)
    launcher = FakeLauncher()
    supervisor = MetadataSupervisor(
        queue=queue,
        launcher=launcher,
        clock=FakeClock(),
    )
    supervisor.tick(worker_id="worker-fixture")
    queue.lose_on_fail = True
    process = next(iter(launcher.processes.values()))
    process.exit_code = 0

    snapshot = supervisor.tick(worker_id="worker-fixture")

    assert snapshot.running == 0
    assert queue.failed == []


def test_shutdown_terminates_groups_and_expires_same_attempt_for_restart() -> None:
    queue = FakeQueue(2)
    launcher = FakeLauncher()
    supervisor = MetadataSupervisor(
        queue=queue,
        launcher=launcher,
        clock=FakeClock(),
    )
    supervisor.tick(worker_id="worker-fixture")

    supervisor.shutdown()

    assert all(process.terminated for process in launcher.processes.values())
    assert set(queue.expired) == set(launcher.processes)
    assert queue.failed == []


def test_recovered_attempt_at_600_seconds_fails_without_starting_a_child() -> None:
    queue = FakeQueue(0)
    queue.claims = [elapsed_claim(0, elapsed_ms=600_000)]
    launcher = FakeLauncher()
    supervisor = MetadataSupervisor(
        queue=queue,
        launcher=launcher,
        clock=FakeClock(),
    )

    snapshot = supervisor.tick(worker_id="worker-fixture")

    assert snapshot.running == 0
    assert launcher.processes == {}
    assert queue.failed == [(uuid.UUID(int=1), "metadata_timeout")]


def test_launcher_failure_persists_failure_and_fills_the_remaining_slots() -> None:
    queue = FakeQueue(4)
    launcher = FailingLauncher()
    supervisor = MetadataSupervisor(
        queue=queue,
        launcher=launcher,
        clock=FakeClock(),
    )

    snapshot = supervisor.tick(worker_id="worker-fixture")

    assert snapshot.running == 3
    assert queue.failed == [(uuid.UUID(int=1), "metadata_child_start_failed")]
    assert set(launcher.processes) == {uuid.UUID(int=value) for value in (2, 3, 4)}


def test_lost_claim_during_renewal_terminates_the_old_child() -> None:
    queue = FakeQueue(1)
    launcher = FakeLauncher()
    clock = FakeClock()
    supervisor = MetadataSupervisor(queue=queue, launcher=launcher, clock=clock)
    supervisor.tick(worker_id="worker-fixture")
    queue.lose_on_renew = True
    clock.value = 15

    snapshot = supervisor.tick(worker_id="worker-fixture")

    assert snapshot.running == 0
    assert next(iter(launcher.processes.values())).terminated is True
    assert queue.failed == []


def test_shutdown_ignores_only_claim_lost_after_terminating_child() -> None:
    queue = FakeQueue(1)
    launcher = FakeLauncher()
    supervisor = MetadataSupervisor(
        queue=queue,
        launcher=launcher,
        clock=FakeClock(),
    )
    supervisor.tick(worker_id="worker-fixture")
    queue.lose_on_expire = True

    supervisor.shutdown()

    assert next(iter(launcher.processes.values())).terminated is True


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group assertion")
def test_subprocess_launcher_kills_the_complete_child_process_group(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "pids.txt"
    script = (
        "import os,subprocess,sys,time;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        f"open({str(pid_file)!r},'w').write(str(os.getpid())+' '+str(child.pid));"
        "time.sleep(60)"
    )
    launcher = SubprocessGroupLauncher(
        command_factory=lambda _: (sys.executable, "-c", script),
    )
    process = launcher.start(claim(99))
    deadline = time.monotonic() + 5
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert pid_file.exists()
    parent_pid, grandchild_pid = [
        int(value) for value in pid_file.read_text(encoding="utf-8").split()
    ]

    process.terminate_group()
    process.wait(timeout=5)

    assert parent_pid == process.pid
    deadline = time.monotonic() + 5
    while _pid_exists(grandchild_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _pid_exists(grandchild_pid)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group assertion")
def test_supervisor_reaps_descendants_when_the_group_leader_exits(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "orphan-pids.txt"
    script = (
        "import os,subprocess,sys;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        f"open({str(pid_file)!r},'w').write(str(os.getpid())+' '+str(child.pid))"
    )
    queue = FakeQueue(1)
    launcher = SubprocessGroupLauncher(
        command_factory=lambda _: (sys.executable, "-c", script),
    )
    supervisor = MetadataSupervisor(queue=queue, launcher=launcher, clock=FakeClock())
    supervisor.tick(worker_id="worker-fixture")
    deadline = time.monotonic() + 5
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert pid_file.exists()
    group_pid, grandchild_pid = [
        int(value) for value in pid_file.read_text(encoding="utf-8").split()
    ]
    deadline = time.monotonic() + 5
    while _pid_exists(group_pid) and time.monotonic() < deadline:
        time.sleep(0.02)

    supervisor.tick(worker_id="worker-fixture")

    deadline = time.monotonic() + 5
    while _pid_exists(grandchild_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _pid_exists(grandchild_pid)


@pytest.mark.skipif(os.name == "nt", reason="Linux container parent-death assertion")
def test_parent_process_crash_kills_the_owned_child_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "crash-pids.txt"
    child_script = (
        "import os,subprocess,sys,time;"
        "from sakuraplayer.worker.metadata_child import start_parent_watchdog_from_environment;"
        "start_parent_watchdog_from_environment();"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        f"open({str(pid_file)!r},'w').write(str(os.getpid())+' '+str(child.pid));"
        "time.sleep(60)"
    )
    outer_script = (
        "import time,uuid;"
        "from datetime import datetime,timezone;"
        "from sakuraplayer.catalog.metadata_queue import MetadataClaim;"
        "from sakuraplayer.worker.metadata_supervisor import SubprocessGroupLauncher;"
        "claim=MetadataClaim(job_id=uuid.uuid4(),movie_id=uuid.uuid4(),"
        "normalized_number='ABP-001',retry_mode='full',requested_stages=(),"
        "claim_owner='outer:claim',claim_expires_at=datetime.now(timezone.utc),"
        "elapsed_ms=0,pending_stages=('javdb_core',),has_warnings=False);"
        f"SubprocessGroupLauncher(command_factory=lambda _:({sys.executable!r},'-c',{child_script!r})).start(claim);"
        "time.sleep(60)"
    )
    outer = subprocess.Popen((sys.executable, "-c", outer_script))
    try:
        deadline = time.monotonic() + 5
        pid_values: list[str] = []
        while time.monotonic() < deadline:
            if pid_file.exists():
                pid_values = pid_file.read_text(encoding="utf-8").split()
                if len(pid_values) == 2:
                    break
            time.sleep(0.02)
        assert len(pid_values) == 2
        group_pid, grandchild_pid = [int(value) for value in pid_values]
        outer.kill()
        outer.wait(timeout=5)
        deadline = time.monotonic() + 5
        while (
            _pid_exists(group_pid) or _pid_exists(grandchild_pid)
        ) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _pid_exists(group_pid)
        assert not _pid_exists(grandchild_pid)
    finally:
        if outer.poll() is None:
            outer.kill()


def _pid_exists(pid: int) -> bool:
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.exists():
        fields = stat_path.read_text(encoding="utf-8").split()
        if len(fields) > 2 and fields[2] == "Z":
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
