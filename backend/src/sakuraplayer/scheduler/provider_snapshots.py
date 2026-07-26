from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from sakuraplayer.scheduler.jobs import SHANGHAI_TIMEZONE


def register_provider_snapshot_job(
    scheduler: BaseScheduler,
    enqueue: Callable[[], object],
) -> None:
    if str(scheduler.timezone) != SHANGHAI_TIMEZONE:
        raise ValueError("provider snapshot scheduler timezone must be Asia/Shanghai")
    scheduler.add_job(
        enqueue,
        CronTrigger(
            day_of_week="sun",
            hour=5,
            minute=0,
            timezone=SHANGHAI_TIMEZONE,
        ),
        id="provider_snapshots_weekly",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )


__all__ = ["register_provider_snapshot_job"]
