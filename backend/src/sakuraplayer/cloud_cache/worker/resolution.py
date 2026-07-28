from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sakuraplayer.cloud_cache.failure_classifier import classify_remote_files
from sakuraplayer.cloud_cache.file_scanner import scan_remote_files
from sakuraplayer.cloud_cache.media_selection import plan_media_selection
from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Port, Cloud115Problem
from sakuraplayer.cloud_cache.source_rejection_client import SourceRejectionClientPort
from sakuraplayer.cloud_cache.subtitle_locator import locate_subtitles
from sakuraplayer.cloud_cache.worker.claim import (
    CacheJobClaim,
    CacheJobClaimLost,
    CacheJobClaimQueue,
)

CloudScopeFactory = Callable[[CacheJobClaim], AbstractAsyncContextManager[Cloud115Port]]


class CacheConsumer(Protocol):
    def run_once(self, *, worker_id: str) -> str: ...


class CacheMediaResolver:
    def __init__(
        self,
        queue: CacheJobClaimQueue,
        rejection_client: SourceRejectionClientPort,
        cloud_factory: CloudScopeFactory,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._queue = queue
        self._rejection_client = rejection_client
        self._cloud_factory = cloud_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def run_once(self, *, worker_id: str) -> str:
        claim = self._queue.claim_resolving(worker_id=worker_id)
        if claim is None:
            return "idle"
        try:
            asyncio.run(self._process(claim))
        except CacheJobClaimLost:
            return "worked"
        return "worked"

    async def _process(self, claim: CacheJobClaim) -> None:
        try:
            existing = self._rejection_client.existing_failure(claim)
            if existing is not None:
                self._queue.fail_rejected(claim, existing.failure_code)
                return
            movie_number = self._queue.resolution_movie_number(claim)
            async with self._cloud_factory(claim) as cloud:
                before = await cloud.directory_info(self._task_cid(claim))
                if not self._owned(claim, before.cid, before.parent_cid, before.name):
                    self._queue.detach(claim)
                    return
                files = [
                    item
                    async for item in cloud.list_files_recursive(self._task_cid(claim))
                ]
                after = await cloud.directory_info(self._task_cid(claim))
                if not self._owned(claim, after.cid, after.parent_cid, after.name):
                    self._queue.detach(claim)
                    return
            deterministic = classify_remote_files(files)
            if deterministic is not None:
                rejected = self._rejection_client.reject(claim, deterministic)
                self._queue.fail_rejected(claim, rejected.failure_code)
                return
            scanned = scan_remote_files(files)
            if not scanned.videos:
                self._queue.fail(claim, "cache_no_valid_media")
                return
            plan = plan_media_selection(scanned.videos, movie_number=movie_number)
            subtitles = locate_subtitles(scanned.subtitles, plan.media)
            self._queue.complete_resolution(claim, plan, subtitles)
        except Cloud115Problem as error:
            if error.code == "cloud115_directory_not_found":
                self._queue.detach(claim)
            elif error.code in {
                "cloud115_unavailable",
                "cloud115_rate_limited",
                "cloud115_credentials_expired",
            }:
                delay = timedelta(seconds=error.retry_after_seconds or 5)
                self._queue.defer(claim, error.code, delay=delay)
            else:
                self._queue.fail(claim, error.code)

    @staticmethod
    def _task_cid(claim: CacheJobClaim) -> str:
        if claim.task_dir_cid is None:
            raise CacheJobClaimLost
        return claim.task_dir_cid

    @staticmethod
    def _owned(
        claim: CacheJobClaim,
        cid: str,
        parent_cid: str,
        name: str,
    ) -> bool:
        return (
            cid == claim.task_dir_cid
            and parent_cid == claim.cache_root_cid
            and name == claim.task_dir_name
        )


class CacheWorkerPipeline:
    def __init__(self, *consumers: CacheConsumer) -> None:
        self._consumers = consumers

    def run_once(self, *, worker_id: str) -> str:
        outcomes = [
            consumer.run_once(worker_id=worker_id) for consumer in self._consumers
        ]
        return "worked" if "worked" in outcomes else "idle"


__all__ = ["CacheMediaResolver", "CacheWorkerPipeline"]
