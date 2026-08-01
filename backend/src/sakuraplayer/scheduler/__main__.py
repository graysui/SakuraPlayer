from __future__ import annotations

import signal
from collections.abc import Callable
from threading import Event

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.provider_snapshots import ProviderSnapshotQueue
from sakuraplayer.catalog.providers.javdb import (
    EncryptedJavdbCredentialStore,
    MetadataProviderProblem,
)
from sakuraplayer.cloud_cache.notifications import NotificationService
from sakuraplayer.discovery.ranking_sync import RankingSyncQueue
from sakuraplayer.events.outbox import DomainEventWriter, EventLog
from sakuraplayer.identity.crypto import SecretCipher, SettingsSecretKeyProvider
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.sync_service import AvdbSyncQueue
from sakuraplayer.scheduler.events import register_event_prune_job
from sakuraplayer.scheduler.jobs import SHANGHAI_TIMEZONE, register_avdb_jobs
from sakuraplayer.scheduler.provider_snapshots import register_provider_snapshot_job
from sakuraplayer.scheduler.rankings import RankingSchedulerJob, register_ranking_job
from sakuraplayer.shared.config import load_settings
from sakuraplayer.shared.runtime import (
    configure_component_logging,
    guarded_main,
    require_ready,
)


def build_scheduler(
    session_factory: sessionmaker[Session],
    *,
    credentials_configured: Callable[[], bool] | None = None,
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=SHANGHAI_TIMEZONE)
    avdb_queue = AvdbSyncQueue(session_factory)
    avdb_queue.ensure_initial_full()
    register_avdb_jobs(scheduler, avdb_queue.enqueue)
    event_log = EventLog(session_factory)
    notifications = NotificationService(
        session_factory,
        event_writer=DomainEventWriter(),
    )

    def prune_realtime_history() -> None:
        event_log.prune_expired()
        notifications.prune_expired()

    register_event_prune_job(scheduler, prune_realtime_history)
    provider_snapshot_queue = ProviderSnapshotQueue(session_factory)
    provider_snapshot_queue.ensure_initial()
    register_provider_snapshot_job(scheduler, provider_snapshot_queue.enqueue)
    ranking_job = RankingSchedulerJob(
        RankingSyncQueue(session_factory),
        credentials_configured=credentials_configured or (lambda: False),
    )
    ranking_job.ensure_initial()
    register_ranking_job(scheduler, ranking_job)
    return scheduler


def main() -> None:
    settings = load_settings()
    require_ready(settings)
    logger = configure_component_logging("scheduler", settings.log_level)
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    credential_check: Callable[[], bool] = lambda: False
    if settings.settings_key is not None:
        repository = EncryptedSettingRepository(
            factory,
            SecretCipher(
                SettingsSecretKeyProvider(
                    key_id=settings.settings_key_id,
                    key=settings.settings_key,
                )
            ),
        )
        credential_store = EncryptedJavdbCredentialStore(repository)

        def configured_or_invalid() -> bool:
            try:
                return credential_store.load() is not None
            except MetadataProviderProblem:
                return True

        credential_check = configured_or_invalid

    scheduler = build_scheduler(
        factory,
        credentials_configured=credential_check,
    )
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
