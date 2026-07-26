from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from sakuraplayer.scheduler.jobs import SHANGHAI_TIMEZONE


def register_event_prune_job(
    scheduler: BaseScheduler,
    prune: Callable[[], object],
) -> None:
    if str(scheduler.timezone) != SHANGHAI_TIMEZONE:
        raise ValueError("event scheduler timezone must be Asia/Shanghai")
    scheduler.add_job(
        prune,
        CronTrigger(hour=2, minute=30, timezone=SHANGHAI_TIMEZONE),
        id="domain_events_daily_prune",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )


__all__ = ["register_event_prune_job"]
