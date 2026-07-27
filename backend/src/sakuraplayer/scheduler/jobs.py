from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

SHANGHAI_TIMEZONE = "Asia/Shanghai"


def register_avdb_jobs(
    scheduler: BaseScheduler,
    enqueue: Callable[[str], object],
) -> None:
    if str(scheduler.timezone) != SHANGHAI_TIMEZONE:
        raise ValueError("AVdb scheduler timezone must be Asia/Shanghai")
    shared = {
        "replace_existing": True,
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 3600,
    }
    scheduler.add_job(
        enqueue,
        CronTrigger(hour=3, minute=0, timezone=SHANGHAI_TIMEZONE),
        id="avdb_incremental_30d",
        args=("incremental_30d",),
        **shared,
    )
    scheduler.add_job(
        enqueue,
        CronTrigger(
            day_of_week="sun",
            hour=4,
            minute=0,
            timezone=SHANGHAI_TIMEZONE,
        ),
        id="avdb_full_reconcile",
        args=("full_reconcile",),
        **shared,
    )
