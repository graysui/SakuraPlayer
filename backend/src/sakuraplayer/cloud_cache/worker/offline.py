from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sakuraplayer.cloud_cache.domain.cache_job import CacheJobStatus
from sakuraplayer.cloud_cache.failure_classifier import classify_cloud_problem
from sakuraplayer.cloud_cache.ports.cloud115 import (
    Cloud115Port,
    Cloud115Problem,
    OfflineTaskPage,
    OfflineTaskSnapshot,
)
from sakuraplayer.cloud_cache.source_rejection_client import SourceRejectionClientPort
from sakuraplayer.cloud_cache.worker.claim import (
    CacheJobClaim,
    CacheJobClaimLost,
    CacheJobClaimQueue,
)
from sakuraplayer.resources.source_submission import (
    SourceSubmissionPort,
    SourceSubmissionProblem,
)

OFFLINE_PAGE_SIZE = 1000
MAX_OFFLINE_PAGES = 1000

CloudScopeFactory = Callable[[CacheJobClaim], AbstractAsyncContextManager[Cloud115Port]]


class OfflineWorker(Protocol):
    def run_once(self, *, worker_id: str) -> str: ...


class CacheOfflineWorker:
    def __init__(
        self,
        queue: CacheJobClaimQueue,
        source_port: SourceSubmissionPort,
        rejection_client: SourceRejectionClientPort,
        cloud_factory: CloudScopeFactory,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._queue = queue
        self._source_port = source_port
        self._rejection_client = rejection_client
        self._cloud_factory = cloud_factory
        self._now = now or (lambda: datetime.now(timezone.utc))

    def run_once(self, *, worker_id: str) -> str:
        claim = self._queue.claim_next(worker_id=worker_id)
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
            async with self._cloud_factory(claim) as cloud:
                if claim.status.value == "submitting":
                    await self._submit(claim, cloud)
                elif claim.status.value == "offlining":
                    await self._poll(claim, cloud)
                elif claim.status.value == "cancelling":
                    await self._cancel(claim, cloud)
                else:
                    raise CacheJobClaimLost
        except SourceSubmissionProblem as error:
            self._queue.fail(claim, error.code)
        except Cloud115Problem as error:
            self._handle_cloud_problem(claim, error)

    async def _submit(self, claim: CacheJobClaim, cloud: Cloud115Port) -> None:
        current = claim
        if current.task_dir_cid is None:
            directory = await cloud.find_or_create_directory(
                current.cache_root_cid,
                current.task_dir_name,
            )
            if (
                directory.parent_cid != current.cache_root_cid
                or directory.name != current.task_dir_name
            ):
                raise Cloud115Problem("cloud115_protocol_error")
            current = self._queue.save_task_directory(current, directory.cid)
            if current.status is CacheJobStatus.CANCELLING:
                self._queue.complete_cancel(current)
                return

        if current.submit_started_at is not None:
            matched = await self._find_by_task_directory(cloud, current.task_dir_cid)
            if matched is None:
                self._queue.mark_submit_uncertain(current)
            else:
                self._queue.save_submission(current, matched.info_hash)
            return

        payload = self._source_port.load_submission_payload(
            movie_id=current.movie_id,
            source_id=current.source_id,
        )
        current = self._queue.mark_submit_started(current)
        assert current.task_dir_cid is not None
        try:
            submission = await cloud.submit_offline(
                payload.magnet, current.task_dir_cid
            )
        except Cloud115Problem as error:
            if error.code not in {
                "cloud115_submit_uncertain",
                "cloud115_protocol_error",
            }:
                deterministic = classify_cloud_problem(error.code)
                if deterministic is not None:
                    rejected = self._rejection_client.reject(current, deterministic)
                    self._queue.fail_rejected(current, rejected.failure_code)
                    return
                raise
            matched = await self._find_by_task_directory(cloud, current.task_dir_cid)
            if matched is None:
                self._queue.mark_submit_uncertain(current)
            else:
                self._queue.save_submission(current, matched.info_hash)
            return
        self._queue.save_submission(current, submission.info_hash)

    async def _poll(self, claim: CacheJobClaim, cloud: Cloud115Port) -> None:
        if claim.remote_info_hash is None:
            raise Cloud115Problem("cloud115_protocol_error")
        matched = await self._find_unique(
            cloud,
            lambda task: task.info_hash == claim.remote_info_hash,
        )
        if matched is None:
            raise Cloud115Problem("cloud115_offline_task_not_found")
        self._queue.record_offline_snapshot(claim, matched)

    async def _cancel(self, claim: CacheJobClaim, cloud: Cloud115Port) -> None:
        current = claim
        if current.task_dir_cid is None:
            directory = await cloud.find_or_create_directory(
                current.cache_root_cid,
                current.task_dir_name,
            )
            if (
                directory.parent_cid != current.cache_root_cid
                or directory.name != current.task_dir_name
            ):
                raise Cloud115Problem("cloud115_protocol_error")
            current = self._queue.save_task_directory(current, directory.cid)
        if current.remote_info_hash is None:
            if current.submit_started_at is None:
                self._queue.complete_cancel(current)
                return
            matched = await self._find_by_task_directory(cloud, current.task_dir_cid)
            if matched is None:
                self._queue.restore_submit_uncertain(current)
                return
            current = self._queue.save_cancel_target(current, matched.info_hash)
        assert current.remote_info_hash is not None
        try:
            await cloud.cancel_offline(current.remote_info_hash)
        except Cloud115Problem as error:
            if error.code != "cloud115_offline_task_not_found":
                raise
        self._queue.complete_cancel(current)

    async def _find_by_task_directory(
        self,
        cloud: Cloud115Port,
        task_dir_cid: str | None,
    ) -> OfflineTaskSnapshot | None:
        if task_dir_cid is None:
            raise Cloud115Problem("cloud115_protocol_error")
        return await self._find_unique(
            cloud,
            lambda task: task.task_cid == task_dir_cid,
        )

    async def _find_unique(
        self,
        cloud: Cloud115Port,
        predicate: Callable[[OfflineTaskSnapshot], bool],
    ) -> OfflineTaskSnapshot | None:
        matches: list[OfflineTaskSnapshot] = []
        expected_pages: int | None = None
        expected_total: int | None = None
        expected_page_size: int | None = None
        page_number = 1
        while expected_pages is None or page_number <= expected_pages:
            page = await cloud.list_offline_tasks(page_number, OFFLINE_PAGE_SIZE)
            self._validate_page(
                page,
                expected_page=page_number,
                expected_pages=expected_pages,
                expected_total=expected_total,
                expected_page_size=expected_page_size,
            )
            expected_pages = page.page_count
            expected_total = page.total_tasks
            expected_page_size = page.page_size
            matches.extend(task for task in page.tasks if predicate(task))
            if len(matches) > 1:
                raise Cloud115Problem("cloud115_protocol_error")
            page_number += 1
        # 115 reports the monthly quota as total; page_count owns traversal.
        return matches[0] if matches else None

    @staticmethod
    def _validate_page(
        page: OfflineTaskPage,
        *,
        expected_page: int,
        expected_pages: int | None,
        expected_total: int | None,
        expected_page_size: int | None,
    ) -> None:
        if (
            page.page != expected_page
            or not 1 <= page.page_count <= MAX_OFFLINE_PAGES
            or not 1 <= page.page_size <= OFFLINE_PAGE_SIZE
            or page.total_tasks < 0
            or len(page.tasks) > page.page_size
            or (expected_pages is not None and page.page_count != expected_pages)
            or (expected_total is not None and page.total_tasks != expected_total)
            or (expected_page_size is not None and page.page_size != expected_page_size)
        ):
            raise Cloud115Problem("cloud115_protocol_error")

    def _handle_cloud_problem(
        self,
        claim: CacheJobClaim,
        error: Cloud115Problem,
    ) -> None:
        if error.code in {
            "cloud115_unavailable",
            "cloud115_rate_limited",
            "cloud115_credentials_expired",
        }:
            seconds = error.retry_after_seconds or 5
            self._queue.defer(claim, error.code, delay=timedelta(seconds=seconds))
            return
        self._queue.fail(claim, error.code)


__all__ = [
    "CacheOfflineWorker",
    "CloudScopeFactory",
    "MAX_OFFLINE_PAGES",
    "OFFLINE_PAGE_SIZE",
    "OfflineWorker",
]
