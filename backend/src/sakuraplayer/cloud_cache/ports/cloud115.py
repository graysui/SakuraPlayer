from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

_STABLE_CODE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class Cloud115Problem(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        if not _STABLE_CODE.fullmatch(code):
            raise ValueError("code must be a stable lowercase identifier")
        if retry_after_seconds is not None and not 0 <= retry_after_seconds <= 86_400:
            raise ValueError("retry_after_seconds must be between 0 and 86400")
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(code)


class QrStatus(str, Enum):
    WAITING = "waiting"
    SCANNED = "scanned"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELED = "canceled"


class CloudCredentialStatus(str, Enum):
    ALIVE = "alive"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


class OfflineStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class QrToken:
    uid: str
    time: int
    sign: str


@dataclass(frozen=True, slots=True)
class QrSession:
    token: QrToken
    image_png: bytes


@dataclass(frozen=True, slots=True)
class QrLoginResult:
    account_key: str
    cookie_snapshot: str


@dataclass(frozen=True, slots=True)
class CredentialProbe:
    status: CloudCredentialStatus
    cookie_snapshot: str | None = None


@dataclass(frozen=True, slots=True)
class RemoteDirectory:
    cid: str
    parent_cid: str
    name: str


@dataclass(frozen=True, slots=True)
class DirectoryBreadcrumb:
    cid: str
    name: str


@dataclass(frozen=True, slots=True)
class DirectoryInfo:
    cid: str
    parent_cid: str
    name: str
    path: tuple[DirectoryBreadcrumb, ...]


@dataclass(frozen=True, slots=True)
class OfflineSubmission:
    info_hash: str


@dataclass(frozen=True, slots=True)
class OfflineTaskSnapshot:
    info_hash: str
    name: str
    size_bytes: int
    status: OfflineStatus
    percent_done: float
    file_id: str | None = None
    pickcode: str | None = None
    task_cid: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class OfflineTaskPage:
    page: int
    page_count: int
    page_size: int
    total_tasks: int
    tasks: tuple[OfflineTaskSnapshot, ...]


@dataclass(frozen=True, slots=True)
class RemoteFile:
    file_id: str
    parent_cid: str
    name: str
    size_bytes: int
    pickcode: str
    sha1: str | None
    is_directory: bool
    is_video: bool | None
    duration_seconds: int | None = None
    blocked: bool | None = None


@dataclass(frozen=True, slots=True)
class OriginalUrl:
    url: str
    expires_at: datetime | None
    file_id: str
    file_name: str
    file_size_bytes: int
    sha1: str
    pickcode: str
    user_agent: str


@dataclass(frozen=True, slots=True)
class HlsVariant:
    url: str
    bandwidth: int
    resolution: str
    label: str
    user_agent: str


@dataclass(frozen=True, slots=True)
class HlsInfo:
    pickcode: str
    variants: tuple[HlsVariant, ...]


@runtime_checkable
class Cloud115Port(Protocol):
    async def create_qr_session(self) -> QrSession: ...

    async def poll_qr_session(self, token: QrToken) -> QrStatus: ...

    async def finish_qr_session(self, token: QrToken) -> QrLoginResult: ...

    async def probe_credentials(self) -> CredentialProbe: ...

    def credential_snapshot(self) -> str | None: ...

    async def find_or_create_directory(
        self,
        parent_cid: str,
        name: str,
    ) -> RemoteDirectory: ...

    async def directory_info(self, cid: str) -> DirectoryInfo: ...

    async def submit_offline(
        self,
        magnet: str,
        task_cid: str,
    ) -> OfflineSubmission: ...

    async def list_offline_tasks(
        self,
        page: int = 1,
        page_size: int = 100,
    ) -> OfflineTaskPage: ...

    async def cancel_offline(self, info_hash: str) -> None: ...

    def list_files_recursive(self, cid: str) -> AsyncIterator[RemoteFile]: ...

    async def resolve_original(
        self,
        pickcode: str,
        user_agent: str,
    ) -> OriginalUrl: ...

    async def resolve_hls(self, pickcode: str, user_agent: str) -> HlsInfo: ...

    async def download_small_file(
        self,
        pickcode: str,
        user_agent: str,
        max_bytes: int,
    ) -> bytes: ...

    async def delete_managed_entries(
        self,
        file_ids: tuple[str, ...],
        verified_parent_cid: str,
    ) -> None: ...


__all__ = [
    "Cloud115Port",
    "Cloud115Problem",
    "CloudCredentialStatus",
    "CredentialProbe",
    "DirectoryBreadcrumb",
    "DirectoryInfo",
    "HlsInfo",
    "HlsVariant",
    "OfflineStatus",
    "OfflineSubmission",
    "OfflineTaskPage",
    "OfflineTaskSnapshot",
    "OriginalUrl",
    "QrLoginResult",
    "QrSession",
    "QrStatus",
    "QrToken",
    "RemoteDirectory",
    "RemoteFile",
]
