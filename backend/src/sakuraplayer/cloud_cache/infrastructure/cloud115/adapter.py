from __future__ import annotations

import re
from collections import deque
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.cookies import CookieError, SimpleCookie
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx

from sakuraplayer.cloud_cache.infrastructure.cloud115.cipher import (
    decrypt_response,
    encrypt_payload,
)
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Problem,
    CloudCredentialStatus,
    CredentialProbe,
    DirectoryBreadcrumb,
    DirectoryInfo,
    HlsInfo,
    HlsVariant,
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

_AUTH_ERRNOS = frozenset({99, 911, 50003, 50004, 99999, 990009, 990017, 20130827})
_NOT_FOUND_ERRNOS = frozenset({20121, 20125, 990002, 4100003, 4100008})
_MEMBERSHIP_ERRNOS = frozenset({406})
_OFFLINE_QUOTA_ERRNOS = frozenset({10004, 10008})
_REQUEST_ERRNOS = frozenset({990005})
_PROTOCOL_HOSTS = frozenset(
    {
        "115.com",
        "my.115.com",
        "passportapi.115.com",
        "proapi.115.com",
        "qrcodeapi.115.com",
        "v.anxia.com",
        "webapi.115.com",
    }
)
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_QR_STATUS = {
    -2: QrStatus.CANCELED,
    -1: QrStatus.EXPIRED,
    0: QrStatus.WAITING,
    1: QrStatus.SCANNED,
    2: QrStatus.CONFIRMED,
}
_OFFLINE_STATUS = {
    -1: OfflineStatus.FAILED,
    0: OfflineStatus.QUEUED,
    1: OfflineStatus.RUNNING,
    2: OfflineStatus.COMPLETED,
}
_OFFLINE_STATUS_NAMES = {
    "queued": OfflineStatus.QUEUED,
    "waiting": OfflineStatus.QUEUED,
    "pending": OfflineStatus.QUEUED,
    "running": OfflineStatus.RUNNING,
    "downloading": OfflineStatus.RUNNING,
    "completed": OfflineStatus.COMPLETED,
    "complete": OfflineStatus.COMPLETED,
    "success": OfflineStatus.COMPLETED,
    "failed": OfflineStatus.FAILED,
    "failure": OfflineStatus.FAILED,
    "error": OfflineStatus.FAILED,
}
_UID_PATTERN = re.compile(r"^(\d+)_")
_M3U8_ATTRIBUTE = re.compile(r'([A-Z0-9-]+)=(?:"([^"]*)"|([^,]*))')
_DEFAULT_USER_AGENT = "SakuraPlayer-Cloud115/1.0"
_MAX_REDIRECTS = 3
_MAX_DIRECTORY_PAGE_SIZE = 1150
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_PLAYLIST_BYTES = 1024 * 1024
_MAX_QR_IMAGE_BYTES = 2 * 1024 * 1024
_RECURSIVE_PAGE_SIZE = 1000
_MAX_RECURSIVE_DEPTH = 16
_MAX_RECURSIVE_DIRECTORIES = 1024
_MAX_RECURSIVE_FILES = 100_000


class _LongPollTimeout(Exception):
    pass


class Cloud115Adapter:
    _TOKEN_URL = "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
    _IMAGE_URL = "https://qrcodeapi.115.com/api/1.0/mac/1.0/qrcode"
    _STATUS_URL = "https://qrcodeapi.115.com/get/status/"
    _RESULT_URL = "https://passportapi.115.com/app/1.0/alipaymini/1.0/login/qrcode/"
    _PROBE_URL = "https://my.115.com/"
    _FILES_URL = "https://webapi.115.com/files"
    _DIRECTORY_URL = "https://webapi.115.com/category/get"
    _MKDIR_URL = "https://webapi.115.com/files/add"
    _DELETE_URL = "https://webapi.115.com/rb/delete"
    _OFFLINE_URL = "https://115.com/web/lixian/"
    _DOWNURL_URL = "https://proapi.115.com/app/chrome/downurl"
    _VIDEO_URL = "https://webapi.115.com/files/video"

    def __init__(
        self,
        cookies: str | None = None,
        *,
        user_agent: str = _DEFAULT_USER_AGENT,
        timeout_seconds: float = 35.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._cookies = self._parse_cookies(cookies or "")
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._client = http_client
        self._owns_client = False

    async def __aenter__(self) -> Cloud115Adapter:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
        self._owns_client = False

    async def create_qr_session(self) -> QrSession:
        payload = await self._json_request("GET", self._TOKEN_URL, operation="qr")
        data = self._data_object(payload)
        try:
            token = QrToken(
                uid=self._required_text(data, "uid"),
                time=int(data["time"]),
                sign=self._required_text(data, "sign"),
            )
        except (KeyError, TypeError, ValueError):
            raise Cloud115Problem("cloud115_protocol_error") from None
        response = await self._request(
            "GET",
            self._IMAGE_URL,
            params={"uid": token.uid},
            operation="qr",
        )
        if len(
            response.content
        ) > _MAX_QR_IMAGE_BYTES or not response.content.startswith(
            b"\x89PNG\r\n\x1a\n"
        ):
            raise Cloud115Problem("cloud115_protocol_error")
        return QrSession(token=token, image_png=response.content)

    async def poll_qr_session(self, token: QrToken) -> QrStatus:
        self._validate_qr_token(token)
        try:
            payload = await self._json_request(
                "GET",
                self._STATUS_URL,
                params={"uid": token.uid, "time": token.time, "sign": token.sign},
                operation="qr",
                long_poll=True,
            )
        except _LongPollTimeout:
            return QrStatus.WAITING
        data = self._data_object(payload)
        raw_status = data.get("status")
        if raw_status is None:
            return QrStatus.WAITING
        try:
            return _QR_STATUS[int(raw_status)]
        except (KeyError, TypeError, ValueError):
            raise Cloud115Problem("cloud115_protocol_error") from None

    async def finish_qr_session(self, token: QrToken) -> QrLoginResult:
        self._validate_qr_token(token)
        payload = await self._json_request(
            "POST",
            self._RESULT_URL,
            data={"account": token.uid},
            operation="qr",
        )
        data = self._data_object(payload)
        cookies = data.get("cookie")
        if not isinstance(cookies, dict) or not cookies:
            raise Cloud115Problem("cloud115_credentials_expired")
        snapshot_parts: list[str] = []
        for key, value in cookies.items():
            if not isinstance(key, str) or not key or not isinstance(value, (str, int)):
                raise Cloud115Problem("cloud115_protocol_error")
            snapshot_parts.append(f"{key}={value}")
        account_key = str(data.get("user_id") or "")
        if not account_key:
            uid_cookie = str(cookies.get("UID") or "")
            match = _UID_PATTERN.match(uid_cookie)
            account_key = match.group(1) if match else ""
        if not account_key:
            raise Cloud115Problem("cloud115_protocol_error")
        return QrLoginResult(
            account_key=account_key,
            cookie_snapshot="; ".join(snapshot_parts),
        )

    async def probe_credentials(self) -> CredentialProbe:
        self._require_credentials()
        client = self._get_client()
        try:
            response = await client.get(
                self._PROBE_URL,
                params={"ct": "guide", "ac": "status"},
                headers=self._credential_headers(),
                follow_redirects=False,
            )
        except httpx.RequestError:
            return CredentialProbe(CloudCredentialStatus.UNAVAILABLE, self._snapshot())
        self._merge_set_cookies(response)
        snapshot = self._snapshot()
        if response.status_code in {302, 401, 403}:
            return CredentialProbe(CloudCredentialStatus.EXPIRED, snapshot)
        if response.status_code != 200:
            return CredentialProbe(CloudCredentialStatus.UNAVAILABLE, snapshot)
        try:
            payload = response.json()
        except (ValueError, UnicodeDecodeError):
            raise Cloud115Problem("cloud115_protocol_error") from None
        if not isinstance(payload, dict) or type(payload.get("state")) is not bool:
            raise Cloud115Problem("cloud115_protocol_error")
        status = (
            CloudCredentialStatus.ALIVE
            if payload["state"]
            else CloudCredentialStatus.EXPIRED
        )
        return CredentialProbe(status, snapshot)

    def credential_snapshot(self) -> str | None:
        snapshot = self._snapshot()
        return snapshot or None

    async def find_or_create_directory(
        self,
        parent_cid: str,
        name: str,
    ) -> RemoteDirectory:
        self._require_nonempty(parent_cid, "parent_cid")
        self._require_nonempty(name, "name")
        matches: list[RemoteDirectory] = []
        offset = 0
        while True:
            payload = await self._json_request(
                "GET",
                self._FILES_URL,
                params={
                    "aid": 1,
                    "cid": parent_cid,
                    "offset": offset,
                    "limit": _MAX_DIRECTORY_PAGE_SIZE,
                    "show_dir": 1,
                },
                operation="directory",
            )
            self._require_state(payload, "directory")
            batch = self._data_list(payload)
            for raw in batch:
                entry = self.parse_remote_file(raw)
                if entry.is_directory and entry.name == name:
                    matches.append(RemoteDirectory(entry.file_id, parent_cid, name))
            total = self._integer(payload.get("count", len(batch)))
            offset += len(batch)
            if not batch and offset < total:
                raise Cloud115Problem("cloud115_protocol_error")
            if offset >= total:
                break
        if len(matches) > 1:
            raise Cloud115Problem("cloud115_directory_ambiguous")
        if matches:
            return matches[0]
        payload = await self._json_request(
            "POST",
            self._MKDIR_URL,
            data={"pid": parent_cid, "cname": name},
            operation="directory",
        )
        self._require_state(payload, "directory")
        cid = str(
            payload.get("category_id")
            or payload.get("cid")
            or payload.get("file_id")
            or ""
        )
        if not cid:
            raise Cloud115Problem("cloud115_protocol_error")
        return RemoteDirectory(cid=cid, parent_cid=parent_cid, name=name)

    async def directory_info(self, cid: str) -> DirectoryInfo:
        self._require_nonempty(cid, "cid")
        if cid == "0":
            return DirectoryInfo(cid="0", parent_cid="", name="root", path=())
        payload = await self._json_request(
            "GET",
            self._DIRECTORY_URL,
            params={"cid": cid},
            operation="directory",
        )
        self._require_state(payload, "directory")
        raw_path = payload.get("paths") or []
        if not isinstance(raw_path, list):
            raise Cloud115Problem("cloud115_protocol_error")
        path: list[DirectoryBreadcrumb] = []
        for raw in raw_path:
            if not isinstance(raw, dict):
                raise Cloud115Problem("cloud115_protocol_error")
            raw_cid = raw.get("file_id") if "file_id" in raw else raw.get("cid")
            raw_name = raw.get("file_name") if "file_name" in raw else raw.get("name")
            path.append(DirectoryBreadcrumb(str(raw_cid), str(raw_name or "")))
        return DirectoryInfo(
            cid=cid,
            parent_cid=path[-1].cid if path else "",
            name=str(payload.get("file_name") or ""),
            path=tuple(path),
        )

    async def submit_offline(
        self,
        magnet: str,
        task_cid: str,
    ) -> OfflineSubmission:
        self._require_nonempty(magnet, "magnet")
        self._require_nonempty(task_cid, "task_cid")
        payload = await self._json_request(
            "POST",
            self._OFFLINE_URL,
            params={"ct": "lixian", "ac": "add_task_urls"},
            data={"wp_path_id": task_cid, "url[0]": magnet},
            operation="offline_submit",
            uncertain=True,
        )
        self._require_state(payload, "offline_submit")
        results = payload.get("result")
        if (
            not isinstance(results, list)
            or len(results) != 1
            or not isinstance(results[0], dict)
        ):
            raise Cloud115Problem("cloud115_protocol_error")
        info_hash = str(results[0].get("info_hash") or "")
        if not info_hash:
            raise Cloud115Problem("cloud115_protocol_error")
        return OfflineSubmission(info_hash=info_hash)

    async def list_offline_tasks(
        self,
        page: int = 1,
        page_size: int = 100,
    ) -> OfflineTaskPage:
        if page < 1 or not 1 <= page_size <= 1000:
            raise ValueError("invalid offline pagination")
        payload = await self._json_request(
            "GET",
            self._OFFLINE_URL,
            params={
                "ct": "lixian",
                "ac": "task_lists",
                "page": page,
                "page_size": page_size,
            },
            operation="offline_list",
        )
        if payload.get("state") is False:
            raise self._payload_problem(payload, "offline_list")
        raw_tasks = payload.get("tasks") or []
        if not isinstance(raw_tasks, list):
            raise Cloud115Problem("cloud115_protocol_error")
        return OfflineTaskPage(
            page=self._integer(payload.get("page", page)),
            page_count=self._integer(payload.get("page_count", 1)),
            page_size=self._integer(payload.get("page_size", page_size)),
            total_tasks=self._integer(payload.get("total", len(raw_tasks))),
            tasks=tuple(self.parse_offline_task(raw) for raw in raw_tasks),
        )

    async def cancel_offline(self, info_hash: str) -> None:
        self._require_nonempty(info_hash, "info_hash")
        payload = await self._json_request(
            "POST",
            self._OFFLINE_URL,
            params={"ct": "lixian", "ac": "task_del"},
            data={"flag": "0", "hash[0]": info_hash},
            operation="offline_cancel",
        )
        self._require_state(payload, "offline_cancel")

    async def list_files_recursive(self, cid: str) -> AsyncIterator[RemoteFile]:
        self._require_nonempty(cid, "cid")
        pending: deque[tuple[str, int]] = deque([(cid, 0)])
        directory_ids = {cid}
        file_ids: set[str] = set()
        files: list[RemoteFile] = []
        while pending:
            directory_cid, depth = pending.popleft()
            entries = await self._list_directory_entries(
                directory_cid,
                max_entries=(
                    _MAX_RECURSIVE_FILES
                    - len(files)
                    + _MAX_RECURSIVE_DIRECTORIES
                    - len(directory_ids)
                ),
            )
            for entry in entries:
                if entry.parent_cid != directory_cid:
                    raise Cloud115Problem("cloud115_protocol_error")
                if entry.is_directory:
                    if (
                        entry.file_id in directory_ids
                        or depth >= _MAX_RECURSIVE_DEPTH
                        or len(directory_ids) >= _MAX_RECURSIVE_DIRECTORIES
                    ):
                        raise Cloud115Problem("cloud115_protocol_error")
                    directory_ids.add(entry.file_id)
                    pending.append((entry.file_id, depth + 1))
                    continue
                if entry.file_id in file_ids or len(files) >= _MAX_RECURSIVE_FILES:
                    raise Cloud115Problem("cloud115_protocol_error")
                file_ids.add(entry.file_id)
                files.append(entry)
        for entry in files:
            yield entry

    async def _list_directory_entries(
        self,
        cid: str,
        *,
        max_entries: int,
    ) -> list[RemoteFile]:
        offset = 0
        expected_total: int | None = None
        entries: list[RemoteFile] = []
        while True:
            payload = await self._json_request(
                "GET",
                self._FILES_URL,
                params={
                    "aid": 1,
                    "cid": cid,
                    "offset": offset,
                    "limit": _RECURSIVE_PAGE_SIZE,
                    "show_dir": 1,
                    "cur": 0,
                    "o": "file_name",
                    "asc": 1,
                },
                operation="file_list",
            )
            self._require_state(payload, "file_list")
            batch = self._data_list(payload)
            if len(batch) > _RECURSIVE_PAGE_SIZE:
                raise Cloud115Problem("cloud115_protocol_error")
            total = self._integer(payload.get("count", len(batch)))
            if (
                total < 0
                or total > max_entries
                or (expected_total is not None and total != expected_total)
            ):
                raise Cloud115Problem("cloud115_protocol_error")
            expected_total = total
            entries.extend(self.parse_remote_file(raw) for raw in batch)
            offset += len(batch)
            if not batch and offset < total:
                raise Cloud115Problem("cloud115_protocol_error")
            if offset >= total:
                if offset != total:
                    raise Cloud115Problem("cloud115_protocol_error")
                return entries

    async def resolve_original(
        self,
        pickcode: str,
        user_agent: str,
    ) -> OriginalUrl:
        self._require_nonempty(pickcode, "pickcode")
        self._require_nonempty(user_agent, "user_agent")
        user_id = self._account_key()
        payload = await self._json_request(
            "POST",
            self._DOWNURL_URL,
            data={
                "data": encrypt_payload(
                    {"pickcode": pickcode, "user_id": user_id}
                ).decode("ascii")
            },
            headers={"User-Agent": user_agent, "Referer": "https://115.com/"},
            operation="original",
        )
        self._require_state(payload, "original")
        ciphertext = payload.get("data")
        if not isinstance(ciphertext, str) or not ciphertext:
            raise Cloud115Problem("cloud115_original_unavailable")
        return self.parse_original_payload(
            decrypt_response(ciphertext),
            pickcode=pickcode,
            user_agent=user_agent,
        )

    async def resolve_hls(self, pickcode: str, user_agent: str) -> HlsInfo:
        self._require_nonempty(pickcode, "pickcode")
        self._require_nonempty(user_agent, "user_agent")
        headers = {"User-Agent": user_agent}
        payload = await self._json_request(
            "GET",
            self._VIDEO_URL,
            params={"pickcode": pickcode},
            headers=headers,
            operation="hls",
        )
        self._require_state(payload, "hls")
        raw_status = payload.get("file_status")
        if raw_status is not None:
            try:
                if int(raw_status) != 1:
                    raise Cloud115Problem("cloud115_hls_not_ready")
            except (TypeError, ValueError):
                raise Cloud115Problem("cloud115_protocol_error") from None
        master_url = str(payload.get("video_url") or "")
        if not master_url:
            raise Cloud115Problem("cloud115_hls_unavailable")
        self.validate_capability_url(master_url)
        response = await self._request(
            "GET",
            master_url,
            headers=headers,
            capability=True,
            operation="hls",
        )
        if len(response.content) > _MAX_PLAYLIST_BYTES:
            raise Cloud115Problem("cloud115_protocol_error")
        variants = self.parse_hls_master(
            response.text,
            base_url=master_url,
            user_agent=user_agent,
        )
        if not variants:
            raise Cloud115Problem("cloud115_hls_unavailable")
        return HlsInfo(pickcode=pickcode, variants=variants)

    async def download_small_file(
        self,
        pickcode: str,
        user_agent: str,
        max_bytes: int,
    ) -> bytes:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        original = await self.resolve_original(pickcode, user_agent)
        return await self._download_capability(
            original.url,
            user_agent=user_agent,
            max_bytes=max_bytes,
        )

    async def delete_managed_entries(
        self,
        file_ids: tuple[str, ...],
        verified_parent_cid: str,
    ) -> None:
        if not file_ids or any(not value for value in file_ids):
            raise ValueError("file_ids must not be empty")
        self._require_nonempty(verified_parent_cid, "verified_parent_cid")
        data = {"pid": verified_parent_cid}
        data.update({f"fid[{index}]": value for index, value in enumerate(file_ids)})
        payload = await self._json_request(
            "POST",
            self._DELETE_URL,
            data=data,
            operation="delete",
        )
        self._require_state(payload, "delete")

    @classmethod
    def parse_remote_file(cls, raw: dict[str, Any]) -> RemoteFile:
        if not isinstance(raw, dict):
            raise Cloud115Problem("cloud115_protocol_error")
        is_directory = "fid" not in raw
        file_id = str(raw.get("cid" if is_directory else "fid") or "")
        parent_cid = str(raw.get("pid" if is_directory else "cid") or "")
        name = str(raw.get("n") or "")
        if not file_id or not name:
            raise Cloud115Problem("cloud115_protocol_error")
        try:
            duration = raw.get("play_long")
            blocked = raw.get("ic")
            return RemoteFile(
                file_id=file_id,
                parent_cid=parent_cid,
                name=name,
                size_bytes=int(raw.get("s") or 0),
                pickcode=str(raw.get("pc") or ""),
                sha1=str(raw["sha"]) if raw.get("sha") else None,
                is_directory=is_directory,
                is_video=False if is_directory else bool(raw.get("iv")),
                duration_seconds=(
                    int(float(duration)) if duration not in (None, "") else None
                ),
                blocked=(bool(int(blocked)) if blocked not in (None, "") else None),
            )
        except (TypeError, ValueError):
            raise Cloud115Problem("cloud115_protocol_error") from None

    @classmethod
    def parse_offline_task(cls, raw: dict[str, Any]) -> OfflineTaskSnapshot:
        if not isinstance(raw, dict):
            raise Cloud115Problem("cloud115_protocol_error")
        try:
            status = cls._offline_status(raw.get("status"))
            info_hash = cls._required_text(raw, "info_hash")
            name = cls._required_alias_text(raw, ("name", "title"))
            failure_reason = (
                "offline_failed" if status is OfflineStatus.FAILED else None
            )
            return OfflineTaskSnapshot(
                info_hash=info_hash,
                name=name,
                size_bytes=int(raw.get("size") or 0),
                status=status,
                percent_done=float(
                    raw.get("percentDone") or raw.get("display_percent") or 0
                ),
                file_id=str(raw.get("file_id") or "") or None,
                pickcode=str(raw.get("pick_code") or "") or None,
                task_cid=cls._optional_alias_text(
                    raw, ("wp_path_id", "task_cid", "path_id")
                ),
                failure_reason=failure_reason,
            )
        except (KeyError, TypeError, ValueError):
            raise Cloud115Problem("cloud115_protocol_error") from None

    @staticmethod
    def _offline_status(value: Any) -> OfflineStatus:
        if isinstance(value, bool):
            raise Cloud115Problem("cloud115_protocol_error")
        if isinstance(value, int):
            status = _OFFLINE_STATUS.get(value)
        elif isinstance(value, str):
            normalized = value.strip().lower()
            status = _OFFLINE_STATUS_NAMES.get(normalized)
            if status is None:
                try:
                    status = _OFFLINE_STATUS.get(int(normalized))
                except ValueError:
                    status = None
        else:
            status = None
        if status is None:
            raise Cloud115Problem("cloud115_protocol_error")
        return status

    @classmethod
    def parse_original_payload(
        cls,
        payload: dict[str, Any],
        *,
        pickcode: str,
        user_agent: str,
    ) -> OriginalUrl:
        if not payload:
            raise Cloud115Problem("cloud115_original_unavailable")
        file_id, raw = next(iter(payload.items()))
        if not isinstance(raw, dict) or not isinstance(raw.get("url"), dict):
            raise Cloud115Problem("cloud115_original_unavailable")
        url = str(raw["url"].get("url") or "")
        if not url:
            raise Cloud115Problem("cloud115_original_unavailable")
        cls.validate_capability_url(url)
        expires_at = cls._expires_at(url)
        try:
            return OriginalUrl(
                url=url,
                expires_at=expires_at,
                file_id=str(file_id),
                file_name=str(raw.get("file_name") or ""),
                file_size_bytes=int(raw.get("file_size") or 0),
                sha1=str(raw.get("sha1") or ""),
                pickcode=str(raw.get("pick_code") or pickcode),
                user_agent=user_agent,
            )
        except (TypeError, ValueError):
            raise Cloud115Problem("cloud115_protocol_error") from None

    @classmethod
    def parse_hls_master(
        cls,
        text: str,
        *,
        base_url: str,
        user_agent: str,
    ) -> tuple[HlsVariant, ...]:
        variants: list[HlsVariant] = []
        pending: dict[str, str] | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("#EXT-X-STREAM-INF:"):
                pending = {}
                for match in _M3U8_ATTRIBUTE.finditer(line.split(":", 1)[1]):
                    pending[match.group(1)] = match.group(2) or match.group(3) or ""
                continue
            if not line or line.startswith("#"):
                continue
            if pending is None:
                raise Cloud115Problem("cloud115_protocol_error")
            url = urljoin(base_url, line)
            cls.validate_capability_url(url)
            try:
                bandwidth = int(pending.get("BANDWIDTH") or 0)
            except ValueError:
                raise Cloud115Problem("cloud115_protocol_error") from None
            variants.append(
                HlsVariant(
                    url=url,
                    bandwidth=bandwidth,
                    resolution=pending.get("RESOLUTION", ""),
                    label=pending.get("NAME", ""),
                    user_agent=user_agent,
                )
            )
            pending = None
        return tuple(variants)

    @staticmethod
    def validate_capability_url(url: str) -> None:
        Cloud115Adapter._validate_url(url, capability=True)

    async def _download_capability(
        self,
        url: str,
        *,
        user_agent: str,
        max_bytes: int,
    ) -> bytes:
        current = url
        for redirect_count in range(_MAX_REDIRECTS + 1):
            self.validate_capability_url(current)
            try:
                async with self._get_client().stream(
                    "GET",
                    current,
                    headers={"User-Agent": user_agent},
                    follow_redirects=False,
                ) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location or redirect_count == _MAX_REDIRECTS:
                            raise Cloud115Problem("cloud115_protocol_error")
                        current = urljoin(current, location)
                        continue
                    self._raise_http_problem(response, "small_file")
                    length = response.headers.get("Content-Length")
                    if length and length.isdigit() and int(length) > max_bytes:
                        raise Cloud115Problem("cloud115_small_file_too_large")
                    output = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(output) + len(chunk) > max_bytes:
                            raise Cloud115Problem("cloud115_small_file_too_large")
                        output.extend(chunk)
                    return bytes(output)
            except Cloud115Problem:
                raise
            except httpx.RequestError:
                raise Cloud115Problem("cloud115_unavailable") from None
        raise Cloud115Problem("cloud115_protocol_error")

    async def _json_request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        operation: str = "protocol",
        uncertain: bool = False,
        long_poll: bool = False,
    ) -> dict[str, Any]:
        response = await self._request(
            method,
            url,
            params=params,
            data=data,
            headers=headers,
            operation=operation,
            uncertain=uncertain,
            long_poll=long_poll,
        )
        if len(response.content) > _MAX_JSON_BYTES:
            raise Cloud115Problem("cloud115_protocol_error")
        try:
            payload = response.json()
        except (ValueError, UnicodeDecodeError):
            raise Cloud115Problem("cloud115_protocol_error") from None
        if not isinstance(payload, dict):
            raise Cloud115Problem("cloud115_protocol_error")
        return payload

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        operation: str = "protocol",
        uncertain: bool = False,
        long_poll: bool = False,
        capability: bool = False,
    ) -> httpx.Response:
        current = url
        current_method = method
        current_data = data
        for redirect_count in range(_MAX_REDIRECTS + 1):
            self._validate_url(current, capability=capability)
            request_headers = (
                self._credential_headers()
                if self._cookies
                else {"User-Agent": self._user_agent}
            )
            if headers:
                request_headers.update(headers)
            try:
                response = await self._get_client().request(
                    current_method,
                    current,
                    params=params if redirect_count == 0 else None,
                    data=current_data,
                    headers=request_headers,
                    follow_redirects=False,
                )
            except httpx.ReadTimeout:
                if long_poll:
                    raise _LongPollTimeout from None
                code = (
                    "cloud115_submit_uncertain" if uncertain else "cloud115_unavailable"
                )
                raise Cloud115Problem(code) from None
            except httpx.RequestError:
                code = (
                    "cloud115_submit_uncertain" if uncertain else "cloud115_unavailable"
                )
                raise Cloud115Problem(code) from None
            self._merge_set_cookies(response)
            if response.status_code in _REDIRECT_STATUSES:
                location = response.headers.get("Location")
                if not location or redirect_count == _MAX_REDIRECTS:
                    raise Cloud115Problem("cloud115_protocol_error")
                current = urljoin(current, location)
                if response.status_code == 303:
                    current_method = "GET"
                    current_data = None
                continue
            self._raise_http_problem(response, operation)
            return response
        raise Cloud115Problem("cloud115_protocol_error")

    @staticmethod
    def _raise_http_problem(response: httpx.Response, operation: str) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        if status == 429:
            raw = response.headers.get("Retry-After", "")
            retry_after = min(int(raw), 86_400) if raw.isdigit() else None
            raise Cloud115Problem(
                "cloud115_rate_limited",
                retry_after_seconds=retry_after,
            )
        if status in {401, 403}:
            raise Cloud115Problem("cloud115_credentials_expired")
        if status == 404:
            codes = {
                "directory": "cloud115_directory_not_found",
                "file_list": "cloud115_directory_not_found",
                "offline_cancel": "cloud115_offline_task_not_found",
                "original": "cloud115_file_not_found",
                "hls": "cloud115_file_not_found",
                "small_file": "cloud115_file_not_found",
                "delete": "cloud115_file_not_found",
            }
            raise Cloud115Problem(codes.get(operation, "cloud115_protocol_error"))
        if status >= 500:
            raise Cloud115Problem("cloud115_unavailable")
        raise Cloud115Problem("cloud115_protocol_error")

    def _require_state(self, payload: dict[str, Any], operation: str) -> None:
        if payload.get("state") is not True:
            raise self._payload_problem(payload, operation)

    @staticmethod
    def _payload_problem(payload: dict[str, Any], operation: str) -> Cloud115Problem:
        raw_errno = payload.get("errno") or payload.get("errNo") or payload.get("code")
        if raw_errno is None:
            return Cloud115Problem("cloud115_protocol_error")
        try:
            errno = int(raw_errno)
        except (TypeError, ValueError):
            return Cloud115Problem("cloud115_protocol_error")
        if errno in _AUTH_ERRNOS:
            return Cloud115Problem("cloud115_credentials_expired")
        if errno in _MEMBERSHIP_ERRNOS:
            return Cloud115Problem("cloud115_hls_membership_required")
        if errno in _OFFLINE_QUOTA_ERRNOS:
            return Cloud115Problem("cloud115_offline_quota_exceeded")
        if errno in _NOT_FOUND_ERRNOS:
            codes = {
                "directory": "cloud115_directory_not_found",
                "file_list": "cloud115_directory_not_found",
                "offline_cancel": "cloud115_offline_task_not_found",
                "offline_submit": "cloud115_source_unavailable",
                "original": "cloud115_file_not_found",
                "hls": "cloud115_file_not_found",
                "small_file": "cloud115_file_not_found",
                "delete": "cloud115_file_not_found",
            }
            return Cloud115Problem(codes.get(operation, "cloud115_protocol_error"))
        if errno in _REQUEST_ERRNOS and operation == "offline_submit":
            return Cloud115Problem("cloud115_protocol_error")
        return Cloud115Problem("cloud115_protocol_error")

    @staticmethod
    def _validate_url(url: str, *, capability: bool) -> None:
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower()
            port = parsed.port
        except ValueError:
            raise Cloud115Problem("cloud115_protocol_error") from None
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or port not in (None, 443)
        ):
            raise Cloud115Problem("cloud115_protocol_error")
        allowed = host in _PROTOCOL_HOSTS
        if capability:
            allowed = (
                allowed
                or host.endswith(".115.com")
                or host.endswith(".115cdn.com")
                or host.endswith(".115cdn.net")
            )
        if not allowed:
            raise Cloud115Problem("cloud115_protocol_error")

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout_seconds,
                trust_env=False,
                follow_redirects=False,
            )
            self._owns_client = True
        return self._client

    def _credential_headers(self) -> dict[str, str]:
        return {"Cookie": self._snapshot(), "User-Agent": self._user_agent}

    def _require_credentials(self) -> None:
        if not self._cookies or "UID" not in self._cookies:
            raise Cloud115Problem("cloud115_credentials_expired")

    def _account_key(self) -> str:
        self._require_credentials()
        match = _UID_PATTERN.match(self._cookies.get("UID", ""))
        if not match:
            raise Cloud115Problem("cloud115_credentials_expired")
        return match.group(1)

    @staticmethod
    def _parse_cookies(snapshot: str) -> dict[str, str]:
        cookies: dict[str, str] = {}
        for part in snapshot.split(";"):
            head = part.strip()
            if not head or "=" not in head:
                continue
            key, value = head.split("=", 1)
            if key.strip():
                cookies[key.strip()] = value.strip()
        return cookies

    def _snapshot(self) -> str:
        return "; ".join(f"{key}={value}" for key, value in self._cookies.items())

    def _merge_set_cookies(self, response: httpx.Response) -> None:
        for line in response.headers.get_list("set-cookie"):
            parsed = SimpleCookie()
            try:
                parsed.load(line)
            except CookieError:
                parsed.clear()
            if parsed:
                for key, morsel in parsed.items():
                    max_age = morsel["max-age"].strip()
                    expires = morsel["expires"].strip()
                    expired = max_age.startswith("-") or max_age == "0"
                    if expires:
                        try:
                            expiry = parsedate_to_datetime(expires)
                            if expiry.tzinfo is None:
                                expiry = expiry.replace(tzinfo=timezone.utc)
                            expired = expired or expiry <= datetime.now(timezone.utc)
                        except (TypeError, ValueError, OverflowError):
                            pass
                    if expired or morsel.value in {"", '""'}:
                        self._cookies.pop(key, None)
                    else:
                        self._cookies[key] = morsel.value
                continue
            head = line.split(";", 1)[0].strip()
            if "=" not in head:
                continue
            key, value = head.split("=", 1)
            key = key.strip()
            if not key:
                continue
            attributes = {part.strip().lower() for part in line.split(";")[1:]}
            if not value or value == '""' or "max-age=0" in attributes:
                self._cookies.pop(key, None)
            else:
                self._cookies[key] = value.strip()

    @staticmethod
    def _data_object(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            raise Cloud115Problem("cloud115_protocol_error")
        return data

    @staticmethod
    def _data_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data") or []
        if not isinstance(data, list) or any(
            not isinstance(item, dict) for item in data
        ):
            raise Cloud115Problem("cloud115_protocol_error")
        return data

    @staticmethod
    def _required_text(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (str, int))
            or not str(value)
        ):
            raise Cloud115Problem("cloud115_protocol_error")
        return str(value)

    @classmethod
    def _required_alias_text(
        cls, payload: dict[str, Any], keys: tuple[str, ...]
    ) -> str:
        value = cls._optional_alias_text(payload, keys)
        if value is None:
            raise Cloud115Problem("cloud115_protocol_error")
        return value

    @staticmethod
    def _optional_alias_text(
        payload: dict[str, Any], keys: tuple[str, ...]
    ) -> str | None:
        for key in keys:
            value = payload.get(key)
            if (
                not isinstance(value, bool)
                and isinstance(value, (str, int))
                and str(value)
            ):
                return str(value)
        return None

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            raise Cloud115Problem("cloud115_protocol_error") from None

    @staticmethod
    def _require_nonempty(value: str, name: str) -> None:
        if not value:
            raise ValueError(f"{name} is required")

    @staticmethod
    def _validate_qr_token(token: QrToken) -> None:
        if not token.uid or not token.sign or token.time <= 0:
            raise ValueError("invalid QR token")

    @staticmethod
    def _expires_at(url: str) -> datetime | None:
        try:
            for key, value in parse_qsl(urlsplit(url).query):
                if key == "t" and value.isdigit():
                    return datetime.fromtimestamp(int(value), timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return None


__all__ = ["Cloud115Adapter"]
