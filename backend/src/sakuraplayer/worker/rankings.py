from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
import threading
from typing import Protocol

from sakuraplayer.discovery.ranking_sync import (
    RankingClaim,
    RankingSnapshotSynchronizer,
    RankingSyncQueue,
)
from sakuraplayer.shared.redaction import stable_error_code


_LOGGER = logging.getLogger(__name__)


class RankingSynchronizerPort(Protocol):
    def synchronize(
        self,
        claim: RankingClaim,
        *,
        before_activate: Callable[[], None],
    ) -> object: ...


class _RankingLeaseKeeper:
    def __init__(
        self,
        *,
        queue: RankingSyncQueue,
        claim: RankingClaim,
        lease_duration: timedelta,
        heartbeat_interval: timedelta,
    ) -> None:
        self._queue = queue
        self._claim = claim
        self._lease_duration = lease_duration
        self._interval_seconds = heartbeat_interval.total_seconds()
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="ranking-request-heartbeat",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def assert_owned(self) -> None:
        if self._lost.is_set():
            raise RuntimeError("ranking request claim was lost")

    def renew_now(self) -> None:
        self.assert_owned()
        self._queue.renew(self._claim, lease_duration=self._lease_duration)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._queue.renew(
                    self._claim,
                    lease_duration=self._lease_duration,
                )
            except Exception:
                self._lost.set()
                _LOGGER.error("ranking_request_heartbeat_failed")
                return


class RankingConsumer:
    def __init__(
        self,
        *,
        queue: RankingSyncQueue,
        synchronizer: RankingSynchronizerPort,
        request_lease_duration: timedelta = timedelta(minutes=30),
        heartbeat_interval: timedelta = timedelta(minutes=2),
    ) -> None:
        if (
            request_lease_duration <= timedelta(0)
            or heartbeat_interval <= timedelta(0)
            or heartbeat_interval >= request_lease_duration
        ):
            raise ValueError("invalid ranking request heartbeat")
        self._queue = queue
        self._synchronizer = synchronizer
        self._request_lease_duration = request_lease_duration
        self._heartbeat_interval = heartbeat_interval

    def run_once(self, *, worker_id: str) -> str:
        claim = self._queue.claim_next(
            worker_id,
            lease_duration=self._request_lease_duration,
        )
        if claim is None:
            return "idle"
        lease_keeper = _RankingLeaseKeeper(
            queue=self._queue,
            claim=claim,
            lease_duration=self._request_lease_duration,
            heartbeat_interval=self._heartbeat_interval,
        )
        lease_keeper.start()
        prepared = False

        def before_activate() -> None:
            nonlocal prepared
            lease_keeper.stop()
            lease_keeper.assert_owned()
            lease_keeper.renew_now()
            prepared = True

        try:
            self._synchronizer.synchronize(
                claim,
                before_activate=before_activate,
            )
            if not prepared:
                raise RuntimeError("ranking activation was not fenced")
            return "completed"
        except Exception as error:
            lease_keeper.stop()
            code = stable_error_code(getattr(error, "code", None))
            try:
                lease_keeper.assert_owned()
                if not prepared:
                    lease_keeper.renew_now()
                self._queue.fail(claim, code=code)
            except RuntimeError:
                _LOGGER.error("ranking_request_claim_lost")
            return "failed"


__all__ = ["RankingConsumer", "RankingSynchronizerPort"]
