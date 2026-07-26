from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from sakuraplayer.discovery.ranking_sync import RankingSyncQueue
from sakuraplayer.scheduler.jobs import SHANGHAI_TIMEZONE


class RankingSchedulerJob:
    def __init__(
        self,
        queue: RankingSyncQueue,
        *,
        credentials_configured: Callable[[], bool],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._queue = queue
        self._credentials_configured = credentials_configured
        self._now = now or (lambda: datetime.now(ZoneInfo(SHANGHAI_TIMEZONE)))

    def __call__(self) -> object:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("ranking scheduler clock must be timezone-aware")
        local = current.astimezone(ZoneInfo(SHANGHAI_TIMEZONE))
        return self._queue.enqueue_due_targets(
            scheduled_for=local,
            current_year=local.year,
            credentials_configured=self._credentials_configured(),
        )


def register_ranking_job(
    scheduler: BaseScheduler,
    enqueue: Callable[[], object],
) -> None:
    if str(scheduler.timezone) != SHANGHAI_TIMEZONE:
        raise ValueError("ranking scheduler timezone must be Asia/Shanghai")
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=1, minute=45, timezone=SHANGHAI_TIMEZONE),
        id="javdb_rankings_daily",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )


__all__ = ["RankingSchedulerJob", "register_ranking_job"]
