from __future__ import annotations

from collections import deque
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Generic, TypeVar

from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    CredentialProbe,
    DirectoryInfo,
    HlsInfo,
    OfflineSubmission,
    OfflineTaskPage,
    OriginalUrl,
    QrLoginResult,
    QrSession,
    QrStatus,
    QrToken,
    RemoteDirectory,
    RemoteFile,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class FakeCloud115Call:
    operation: str
    safe_arguments: tuple[str, ...] = ()


class _Script(Generic[T]):
    def __init__(self, values: Iterable[T | Cloud115Problem] = ()) -> None:
        self._values = deque(values)

    def take(self, operation: str) -> T:
        if not self._values:
            raise AssertionError(f"no scripted result for {operation}")
        value = self._values.popleft()
        if isinstance(value, Cloud115Problem):
            raise value
        return value


class FakeCloud115:
    def __init__(
        self,
        *,
        qr_sessions: Iterable[QrSession | Cloud115Problem] = (),
        qr_statuses: Iterable[QrStatus | Cloud115Problem] = (),
        qr_results: Iterable[QrLoginResult | Cloud115Problem] = (),
        credential_probes: Iterable[CredentialProbe | Cloud115Problem] = (),
        directories: Iterable[RemoteDirectory | Cloud115Problem] = (),
        directory_infos: Iterable[DirectoryInfo | Cloud115Problem] = (),
        offline_submissions: Iterable[OfflineSubmission | Cloud115Problem] = (),
        offline_pages: Iterable[OfflineTaskPage | Cloud115Problem] = (),
        cancel_results: Iterable[None | Cloud115Problem] = (),
        file_batches: Iterable[tuple[RemoteFile, ...] | Cloud115Problem] = (),
        original_urls: Iterable[OriginalUrl | Cloud115Problem] = (),
        hls_infos: Iterable[HlsInfo | Cloud115Problem] = (),
        small_files: Iterable[bytes | Cloud115Problem] = (),
        delete_results: Iterable[None | Cloud115Problem] = (),
        credential_snapshot: str | None = None,
    ) -> None:
        self.calls: list[FakeCloud115Call] = []
        self._credential_snapshot = credential_snapshot
        self._qr_sessions = _Script(qr_sessions)
        self._qr_statuses = _Script(qr_statuses)
        self._qr_results = _Script(qr_results)
        self._credential_probes = _Script(credential_probes)
        self._directories = _Script(directories)
        self._directory_infos = _Script(directory_infos)
        self._offline_submissions = _Script(offline_submissions)
        self._offline_pages = _Script(offline_pages)
        self._cancel_results = _Script(cancel_results)
        self._file_batches = _Script(file_batches)
        self._original_urls = _Script(original_urls)
        self._hls_infos = _Script(hls_infos)
        self._small_files = _Script(small_files)
        self._delete_results = _Script(delete_results)

    def _record(self, operation: str, *safe_arguments: str) -> None:
        self.calls.append(FakeCloud115Call(operation, tuple(safe_arguments)))

    async def create_qr_session(self) -> QrSession:
        self._record("create_qr_session")
        return self._qr_sessions.take("create_qr_session")

    async def poll_qr_session(self, token: QrToken) -> QrStatus:
        self._record("poll_qr_session", sha256(token.uid.encode()).hexdigest())
        return self._qr_statuses.take("poll_qr_session")

    async def finish_qr_session(self, token: QrToken) -> QrLoginResult:
        self._record("finish_qr_session", sha256(token.uid.encode()).hexdigest())
        return self._qr_results.take("finish_qr_session")

    async def probe_credentials(self) -> CredentialProbe:
        self._record("probe_credentials")
        return self._credential_probes.take("probe_credentials")

    def credential_snapshot(self) -> str | None:
        self._record("credential_snapshot")
        return self._credential_snapshot

    async def find_or_create_directory(
        self,
        parent_cid: str,
        name: str,
    ) -> RemoteDirectory:
        self._record("find_or_create_directory", parent_cid, name)
        return self._directories.take("find_or_create_directory")

    async def directory_info(self, cid: str) -> DirectoryInfo:
        self._record("directory_info", cid)
        return self._directory_infos.take("directory_info")

    async def submit_offline(
        self,
        magnet: str,
        task_cid: str,
    ) -> OfflineSubmission:
        self._record(
            "submit_offline",
            sha256(magnet.encode()).hexdigest(),
            task_cid,
        )
        return self._offline_submissions.take("submit_offline")

    async def list_offline_tasks(
        self,
        page: int = 1,
        page_size: int = 100,
    ) -> OfflineTaskPage:
        self._record("list_offline_tasks", str(page), str(page_size))
        return self._offline_pages.take("list_offline_tasks")

    async def cancel_offline(self, info_hash: str) -> None:
        self._record("cancel_offline", info_hash)
        self._cancel_results.take("cancel_offline")

    async def list_files_recursive(self, cid: str) -> AsyncIterator[RemoteFile]:
        self._record("list_files_recursive", cid)
        for file in self._file_batches.take("list_files_recursive"):
            yield file

    async def resolve_original(
        self,
        pickcode: str,
        user_agent: str,
    ) -> OriginalUrl:
        self._record("resolve_original", pickcode, user_agent)
        return self._original_urls.take("resolve_original")

    async def resolve_hls(self, pickcode: str, user_agent: str) -> HlsInfo:
        self._record("resolve_hls", pickcode, user_agent)
        return self._hls_infos.take("resolve_hls")

    async def download_small_file(
        self,
        pickcode: str,
        user_agent: str,
        max_bytes: int,
    ) -> bytes:
        self._record("download_small_file", pickcode, user_agent, str(max_bytes))
        return self._small_files.take("download_small_file")

    async def delete_managed_entries(
        self,
        file_ids: tuple[str, ...],
        verified_parent_cid: str,
    ) -> None:
        self._record("delete_managed_entries", *file_ids, verified_parent_cid)
        self._delete_results.take("delete_managed_entries")


__all__ = ["FakeCloud115", "FakeCloud115Call"]
