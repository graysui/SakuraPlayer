from __future__ import annotations

import signal
from threading import Event

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.resources.sync_service import AvdbSyncQueue
from sakuraplayer.scheduler.jobs import SHANGHAI_TIMEZONE, register_avdb_jobs
from sakuraplayer.shared.config import load_settings
from sakuraplayer.shared.runtime import (
    configure_component_logging,
    guarded_main,
    require_ready,
)


def main() -> None:
    settings = load_settings()
    require_ready(settings)
    logger = configure_component_logging("scheduler", settings.log_level)
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )
    queue = AvdbSyncQueue(sessionmaker(engine, expire_on_commit=False))
    scheduler = BackgroundScheduler(timezone=SHANGHAI_TIMEZONE)
    register_avdb_jobs(scheduler, queue.enqueue)
    stop_event = Event()

    def request_stop(signum, frame) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    scheduler.start()
    logger.info("component_started")
    try:
        while not stop_event.wait(30):
            require_ready(settings)
    finally:
        scheduler.shutdown(wait=False)
        engine.dispose()
        logger.info("component_stopped")


if __name__ == "__main__":
    guarded_main("scheduler", main)
