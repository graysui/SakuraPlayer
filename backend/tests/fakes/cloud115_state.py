from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import replace
from hashlib import sha256

from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    CloudCredentialStatus,
    CredentialProbe,
    DirectoryBreadcrumb,
    DirectoryInfo,
    HlsInfo,
    OfflineStatus,
    OfflineSubmission,
    OfflineTaskPage,
    OfflineTaskSnapshot,
    OriginalUrl,
    QrLoginResult,
    QrSession,
    QrStatus,
    QrToken,
    RemoteDirectory,
    RemoteFile,
)
from tests.fakes.cloud115 import FakeCloud115Call


class StatefulFakeCloud115:
    """Deterministic, queryable Cloud115Port model for cross-boundary E2E tests."""

    def __init__(self, *, cookie_snapshot: str | None = None) -> None:
        self.calls: list[FakeCloud115Call] = []
        self._cookie_snapshot = cookie_snapshot
        self._credential_probe = CredentialProbe(
            CloudCredentialStatus.ALIVE,
            cookie_snapshot,
        )
        self._faults: dict[str, deque[Cloud115Problem]] = defaultdict(deque)
        self._post_faults: dict[str, deque[Cloud115Problem]] = defaultdict(deque)
        self._qr_sessions: deque[QrSession] = deque()
        self._qr_statuses: deque[QrStatus] = deque()
        self._qr_results: deque[QrLoginResult] = deque()
        self._directories: dict[str, RemoteDirectory] = {}
        self._offline_tasks: dict[str, OfflineTaskSnapshot] = {}
        self._files_by_parent: dict[str, dict[str, RemoteFile]] = defaultdict(dict)
        self._originals: dict[str, OriginalUrl] = {}
        self._hls: dict[str, HlsInfo] = {}
        self._small_files: dict[str, bytes] = {}
        self._deleted_entries: set[str] = set()
        self._next_directory = 1

    def __repr__(self) -> str:
        return (
            "StatefulFakeCloud115("
            f"directories={len(self._directories)}, "
            f"offline_tasks={len(self._offline_tasks)}, "
            f"files={sum(len(items) for items in self._files_by_parent.values())}, "
            f"deleted_entries={len(self._deleted_entries)})"
        )

    def _record(self, operation: str, *safe_arguments: str) -> None:
        self.calls.append(FakeCloud115Call(operation, tuple(safe_arguments)))

    def _raise_fault(self, operation: str) -> None:
        faults = self._faults[operation]
        if faults:
            raise faults.popleft()

    def _raise_post_fault(self, operation: str) -> None:
        faults = self._post_faults[operation]
        if faults:
            raise faults.popleft()

    def inject_fault(self, operation: str, problem: Cloud115Problem) -> None:
        if not operation or not isinstance(problem, Cloud115Problem):
            raise ValueError("a stable Cloud115Problem is required")
        self._faults[operation].append(problem)

    def inject_post_fault(self, operation: str, problem: Cloud115Problem) -> None:
        if operation != "submit_offline" or not isinstance(problem, Cloud115Problem):
            raise ValueError("a supported stable Cloud115Problem is required")
        self._post_faults[operation].append(problem)

    def queue_qr_session(self, session: QrSession) -> None:
        self._qr_sessions.append(session)

    def queue_qr_status(self, status: QrStatus) -> None:
        self._qr_statuses.append(status)

    def queue_qr_result(self, result: QrLoginResult) -> None:
        self._qr_results.append(result)

    def set_credential_probe(self, probe: CredentialProbe) -> None:
        self._credential_probe = probe
        if probe.cookie_snapshot is not None:
            self._cookie_snapshot = probe.cookie_snapshot

    def seed_directory(self, cid: str, parent_cid: str, name: str) -> None:
        if not cid or not parent_cid or not name:
            raise ValueError("directory fields must be non-empty")
        self._directories[cid] = RemoteDirectory(cid, parent_cid, name)
        self._deleted_entries.discard(cid)

    def move_directory(self, cid: str, parent_cid: str) -> None:
        current = self._directory(cid)
        self._directories[cid] = replace(current, parent_cid=parent_cid)

    def directory_exists(self, cid: str) -> bool:
        return cid in self._directories

    def seed_files(self, parent_cid: str, files: tuple[RemoteFile, ...]) -> None:
        seeded: dict[str, RemoteFile] = {}
        for item in files:
            if item.parent_cid != parent_cid:
                raise ValueError("file parent must match seeded directory")
            seeded[item.file_id] = item
            self._deleted_entries.discard(item.file_id)
        self._files_by_parent[parent_cid] = seeded

    def file_exists(self, file_id: str) -> bool:
        return any(file_id in items for items in self._files_by_parent.values())

    def set_offline_status(
        self,
        info_hash: str,
        status: OfflineStatus,
        *,
        percent_done: float,
        failure_reason: str | None = None,
    ) -> None:
        task = self.offline_task(info_hash)
        self._offline_tasks[info_hash] = replace(
            task,
            status=status,
            percent_done=percent_done,
            failure_reason=failure_reason,
        )

    def offline_task(self, info_hash: str) -> OfflineTaskSnapshot:
        try:
            return self._offline_tasks[info_hash]
        except KeyError:
            raise LookupError("offline task does not exist") from None

    def seed_original(self, original: OriginalUrl) -> None:
        self._originals[original.pickcode] = original

    def seed_hls(self, hls: HlsInfo) -> None:
        self._hls[hls.pickcode] = hls

    def seed_small_file(self, pickcode: str, content: bytes) -> None:
        self._small_files[pickcode] = bytes(content)

    def was_deleted(self, entry_id: str) -> bool:
        return entry_id in self._deleted_entries

    async def create_qr_session(self) -> QrSession:
        operation = "create_qr_session"
        self._record(operation)
        self._raise_fault(operation)
        if not self._qr_sessions:
            raise AssertionError(f"no stateful result for {operation}")
        return self._qr_sessions.popleft()

    async def poll_qr_session(self, token: QrToken) -> QrStatus:
        operation = "poll_qr_session"
        self._record(operation, sha256(token.uid.encode()).hexdigest())
        self._raise_fault(operation)
        if not self._qr_statuses:
            raise AssertionError(f"no stateful result for {operation}")
        return self._qr_statuses.popleft()

    async def finish_qr_session(self, token: QrToken) -> QrLoginResult:
        operation = "finish_qr_session"
        self._record(operation, sha256(token.uid.encode()).hexdigest())
        self._raise_fault(operation)
        if not self._qr_results:
            raise AssertionError(f"no stateful result for {operation}")
        result = self._qr_results.popleft()
        self._cookie_snapshot = result.cookie_snapshot
        return result

    async def probe_credentials(self) -> CredentialProbe:
        operation = "probe_credentials"
        self._record(operation)
        self._raise_fault(operation)
        return self._credential_probe

    def credential_snapshot(self) -> str | None:
        self._record("credential_snapshot")
        return self._cookie_snapshot

    async def find_or_create_directory(
        self,
        parent_cid: str,
        name: str,
    ) -> RemoteDirectory:
        operation = "find_or_create_directory"
        self._record(operation, parent_cid, name)
        self._raise_fault(operation)
        matches = [
            item
            for item in self._directories.values()
            if item.parent_cid == parent_cid and item.name == name
        ]
        if len(matches) > 1:
            raise Cloud115Problem("cloud115_directory_ambiguous")
        if matches:
            return matches[0]
        cid = f"fake-dir-{self._next_directory:04d}"
        self._next_directory += 1
        created = RemoteDirectory(cid, parent_cid, name)
        self._directories[cid] = created
        return created

    async def directory_info(self, cid: str) -> DirectoryInfo:
        operation = "directory_info"
        self._record(operation, cid)
        self._raise_fault(operation)
        directory = self._directory(cid)
        return DirectoryInfo(
            cid=directory.cid,
            parent_cid=directory.parent_cid,
            name=directory.name,
            path=self._breadcrumbs(directory.parent_cid),
        )

    async def submit_offline(
        self,
        magnet: str,
        task_cid: str,
    ) -> OfflineSubmission:
        operation = "submit_offline"
        digest = sha256(magnet.encode()).hexdigest()
        self._record(operation, digest, task_cid)
        self._raise_fault(operation)
        self._directory(task_cid)
        info_hash = digest[:40]
        self._offline_tasks.setdefault(
            info_hash,
            OfflineTaskSnapshot(
                info_hash=info_hash,
                name=f"offline-{info_hash[:12]}",
                size_bytes=0,
                status=OfflineStatus.QUEUED,
                percent_done=0.0,
                task_cid=task_cid,
            ),
        )
        self._raise_post_fault(operation)
        return OfflineSubmission(info_hash)

    async def list_offline_tasks(
        self,
        page: int = 1,
        page_size: int = 100,
    ) -> OfflineTaskPage:
        operation = "list_offline_tasks"
        self._record(operation, str(page), str(page_size))
        self._raise_fault(operation)
        if page < 1 or page_size < 1:
            raise Cloud115Problem("cloud115_protocol_error")
        tasks = tuple(self._offline_tasks[key] for key in sorted(self._offline_tasks))
        total = len(tasks)
        page_count = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        return OfflineTaskPage(
            page=page,
            page_count=page_count,
            page_size=page_size,
            total_tasks=total,
            tasks=tasks[start : start + page_size],
        )

    async def cancel_offline(self, info_hash: str) -> None:
        operation = "cancel_offline"
        self._record(operation, info_hash)
        self._raise_fault(operation)
        if self._offline_tasks.pop(info_hash, None) is None:
            raise Cloud115Problem("cloud115_offline_task_not_found")

    async def list_files_recursive(self, cid: str) -> AsyncIterator[RemoteFile]:
        operation = "list_files_recursive"
        self._record(operation, cid)
        self._raise_fault(operation)
        self._directory(cid)
        pending = [cid]
        while pending:
            parent = pending.pop(0)
            for item in sorted(
                self._files_by_parent.get(parent, {}).values(),
                key=lambda value: (value.name, value.file_id),
            ):
                if item.is_directory:
                    pending.append(item.file_id)
                else:
                    yield item
            pending.extend(
                sorted(
                    directory.cid
                    for directory in self._directories.values()
                    if directory.parent_cid == parent
                )
            )

    async def resolve_original(
        self,
        pickcode: str,
        user_agent: str,
    ) -> OriginalUrl:
        operation = "resolve_original"
        self._record(operation, pickcode, user_agent)
        self._raise_fault(operation)
        try:
            result = self._originals[pickcode]
        except KeyError:
            raise Cloud115Problem("cloud115_original_unavailable") from None
        if result.user_agent != user_agent:
            raise Cloud115Problem("cloud115_protocol_error")
        return result

    async def resolve_hls(self, pickcode: str, user_agent: str) -> HlsInfo:
        operation = "resolve_hls"
        self._record(operation, pickcode, user_agent)
        self._raise_fault(operation)
        try:
            result = self._hls[pickcode]
        except KeyError:
            raise Cloud115Problem("cloud115_hls_unavailable") from None
        if any(variant.user_agent != user_agent for variant in result.variants):
            raise Cloud115Problem("cloud115_protocol_error")
        return result

    async def download_small_file(
        self,
        pickcode: str,
        user_agent: str,
        max_bytes: int,
    ) -> bytes:
        operation = "download_small_file"
        self._record(operation, pickcode, user_agent, str(max_bytes))
        self._raise_fault(operation)
        try:
            content = self._small_files[pickcode]
        except KeyError:
            raise Cloud115Problem("cloud115_file_not_found") from None
        if len(content) > max_bytes:
            raise Cloud115Problem("cloud115_small_file_too_large")
        return content

    async def delete_managed_entries(
        self,
        file_ids: tuple[str, ...],
        verified_parent_cid: str,
    ) -> None:
        operation = "delete_managed_entries"
        self._record(operation, *file_ids, verified_parent_cid)
        self._raise_fault(operation)
        for entry_id in file_ids:
            directory = self._directories.get(entry_id)
            if directory is not None:
                if directory.parent_cid != verified_parent_cid:
                    raise Cloud115Problem("cache_ownership_mismatch")
                self._delete_directory_tree(entry_id)
                continue
            parent = self._file_parent(entry_id)
            if parent is None:
                raise Cloud115Problem("cloud115_file_not_found")
            if parent != verified_parent_cid:
                raise Cloud115Problem("cache_ownership_mismatch")
            del self._files_by_parent[parent][entry_id]
            self._deleted_entries.add(entry_id)

    def _directory(self, cid: str) -> RemoteDirectory:
        try:
            return self._directories[cid]
        except KeyError:
            raise Cloud115Problem("cloud115_directory_not_found") from None

    def _breadcrumbs(self, parent_cid: str) -> tuple[DirectoryBreadcrumb, ...]:
        breadcrumbs: list[DirectoryBreadcrumb] = []
        seen: set[str] = set()
        current = parent_cid
        while current in self._directories and current not in seen:
            seen.add(current)
            directory = self._directories[current]
            breadcrumbs.append(DirectoryBreadcrumb(directory.cid, directory.name))
            current = directory.parent_cid
        breadcrumbs.reverse()
        return tuple(breadcrumbs)

    def _file_parent(self, file_id: str) -> str | None:
        return next(
            (
                parent
                for parent, items in self._files_by_parent.items()
                if file_id in items
            ),
            None,
        )

    def _delete_directory_tree(self, cid: str) -> None:
        children = [
            item.cid for item in self._directories.values() if item.parent_cid == cid
        ]
        for child in children:
            self._delete_directory_tree(child)
        self._deleted_entries.update(self._files_by_parent.pop(cid, {}))
        self._directories.pop(cid, None)
        self._deleted_entries.add(cid)


__all__ = ["StatefulFakeCloud115"]
