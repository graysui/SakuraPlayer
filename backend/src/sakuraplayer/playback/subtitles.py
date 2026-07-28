from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.cloud_cache.binding_service import BindingService
from sakuraplayer.cloud_cache.models import CacheJob, RemoteSubtitle
from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Problem
from sakuraplayer.cloud_cache.root_directory import (
    CACHE_ROOT_NAME,
    CACHE_ROOT_PARENT_CID,
)
from sakuraplayer.identity.domain import CurrentAdmin
from sakuraplayer.playback.models import PlaybackSession
from sakuraplayer.playback.user_agents import user_agent_for

MAX_SUBTITLE_BYTES = 8 * 1024 * 1024
SUBTITLE_MEDIA_TYPES = {
    "srt": "application/x-subrip",
    "ass": "text/x-ssa",
    "ssa": "text/x-ssa",
    "vtt": "text/vtt",
}


class SubtitleProblem(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        retry_after_seconds: int | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SubtitleDownload:
    content: bytes
    media_type: str
    filename: str


@dataclass(frozen=True, slots=True)
class _SubtitleContext:
    binding_id: uuid.UUID
    account_key: str
    cache_root_cid: str
    task_dir_cid: str
    task_dir_name: str
    file_id: str
    pickcode: str
    extension: str
    subtitle_id: uuid.UUID
    user_agent: str


class SubtitleDownloadService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        binding_service: BindingService,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._binding_service = binding_service
        self._now = now or (lambda: datetime.now(timezone.utc))

    async def download(
        self,
        *,
        admin: CurrentAdmin,
        playback_session_id: uuid.UUID,
        subtitle_id: uuid.UUID,
    ) -> SubtitleDownload:
        context = self._authorize(
            admin=admin,
            playback_session_id=playback_session_id,
            subtitle_id=subtitle_id,
        )
        try:
            async with self._binding_service.cache_operation_scope(
                binding_id=context.binding_id,
                account_key=context.account_key,
                cache_root_cid=context.cache_root_cid,
            ) as cloud:
                root = await cloud.directory_info(context.cache_root_cid)
                if (
                    root.cid != context.cache_root_cid
                    or root.parent_cid != CACHE_ROOT_PARENT_CID
                    or root.name != CACHE_ROOT_NAME
                ):
                    raise SubtitleProblem(status_code=404, code="subtitle_not_found")
                task = await cloud.directory_info(context.task_dir_cid)
                if (
                    task.cid != context.task_dir_cid
                    or task.parent_cid != context.cache_root_cid
                    or task.name != context.task_dir_name
                ):
                    raise SubtitleProblem(status_code=404, code="subtitle_not_found")
                found = False
                async for item in cloud.list_files_recursive(context.task_dir_cid):
                    if item.file_id == context.file_id:
                        if item.is_directory or item.pickcode != context.pickcode:
                            break
                        if item.size_bytes > MAX_SUBTITLE_BYTES:
                            raise SubtitleProblem(
                                status_code=413, code="subtitle_too_large"
                            )
                        found = item.size_bytes > 0
                        break
                if not found:
                    raise SubtitleProblem(status_code=404, code="subtitle_not_found")
                content = await cloud.download_small_file(
                    context.pickcode, context.user_agent, MAX_SUBTITLE_BYTES
                )
        except Cloud115Problem as error:
            raise _map_cloud_problem(error) from None
        if len(content) > MAX_SUBTITLE_BYTES:
            raise SubtitleProblem(status_code=413, code="subtitle_too_large")
        return SubtitleDownload(
            content=content,
            media_type=subtitle_media_type(context.extension),
            filename=subtitle_download_filename(context.subtitle_id, context.extension),
        )

    def _authorize(
        self,
        *,
        admin: CurrentAdmin,
        playback_session_id: uuid.UUID,
        subtitle_id: uuid.UUID,
    ) -> _SubtitleContext:
        current = _as_utc(self._now())
        with self._session_factory() as session:
            playback = session.get(PlaybackSession, playback_session_id)
            if (
                playback is None
                or playback.admin_id != admin.admin_id
                or playback.session_epoch != admin.session_epoch
                or playback.revoked_at is not None
                or _as_utc(playback.expires_at) <= current
            ):
                raise SubtitleProblem(status_code=404, code="subtitle_not_found")
            subtitle = session.get(RemoteSubtitle, subtitle_id)
            if (
                subtitle is None
                or subtitle.cache_job_id != playback.cache_job_id
                or (
                    subtitle.media_id is not None
                    and subtitle.media_id != playback.media_id
                )
            ):
                raise SubtitleProblem(status_code=404, code="subtitle_not_found")
            subtitle_media_type(subtitle.extension)
            if subtitle.size_bytes > MAX_SUBTITLE_BYTES:
                raise SubtitleProblem(status_code=413, code="subtitle_too_large")
            job = session.get(CacheJob, playback.cache_job_id)
            if (
                job is None
                or job.status != "ready"
                or job.binding_id is None
                or job.account_key is None
                or job.cache_root_cid is None
                or job.task_dir_cid is None
                or job.task_dir_name is None
            ):
                raise SubtitleProblem(status_code=404, code="subtitle_not_found")
            try:
                user_agent = user_agent_for(playback.platform)  # type: ignore[arg-type]
            except ValueError:
                raise SubtitleProblem(
                    status_code=404, code="subtitle_not_found"
                ) from None
            return _SubtitleContext(
                binding_id=job.binding_id,
                account_key=job.account_key,
                cache_root_cid=job.cache_root_cid,
                task_dir_cid=job.task_dir_cid,
                task_dir_name=job.task_dir_name,
                file_id=subtitle.file_id,
                pickcode=subtitle.pickcode,
                extension=subtitle.extension,
                subtitle_id=subtitle.id,
                user_agent=user_agent,
            )


def _map_cloud_problem(error: Cloud115Problem) -> SubtitleProblem:
    if error.code in {
        "cloud115_file_not_found",
        "cloud115_directory_not_found",
        "cloud115_original_unavailable",
    }:
        return SubtitleProblem(status_code=404, code="subtitle_not_found")
    if error.code == "cloud115_small_file_too_large":
        return SubtitleProblem(status_code=413, code="subtitle_too_large")
    statuses = {
        "cloud115_credentials_expired": 422,
        "cloud115_rate_limited": 429,
        "cloud115_unavailable": 503,
        "cloud115_protocol_error": 502,
    }
    return SubtitleProblem(
        status_code=statuses.get(error.code, 502),
        code=error.code if error.code in statuses else "cloud115_protocol_error",
        retry_after_seconds=error.retry_after_seconds,
    )


def subtitle_media_type(extension: str) -> str:
    try:
        return SUBTITLE_MEDIA_TYPES[extension]
    except KeyError:
        raise SubtitleProblem(
            status_code=422, code="subtitle_format_unsupported"
        ) from None


def subtitle_download_filename(subtitle_id: uuid.UUID, extension: str) -> str:
    subtitle_media_type(extension)
    return f"{subtitle_id}.{extension}"


def _as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


__all__ = [
    "MAX_SUBTITLE_BYTES",
    "SUBTITLE_MEDIA_TYPES",
    "SubtitleDownload",
    "SubtitleDownloadService",
    "SubtitleProblem",
    "subtitle_download_filename",
    "subtitle_media_type",
]
