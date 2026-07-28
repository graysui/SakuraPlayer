from __future__ import annotations

import os
import signal
import socket
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from typing import Protocol

import httpx
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.metadata_seeder import MetadataQueueSeeder
from sakuraplayer.catalog.provider_snapshots import (
    ProviderSnapshotQueue,
    ProviderSnapshotRefreshService,
)
from sakuraplayer.catalog.providers.javdb import (
    EncryptedJavdbCredentialStore,
    JavdbProvider,
)
from sakuraplayer.cloud_cache.binding_service import BindingService
from sakuraplayer.cloud_cache.infrastructure.cloud115 import Cloud115Adapter
from sakuraplayer.cloud_cache.ports.cloud115 import Cloud115Port
from sakuraplayer.cloud_cache.source_rejection_client import SourceRejectionClient
from sakuraplayer.cloud_cache.worker.claim import CacheJobClaim, CacheJobClaimQueue
from sakuraplayer.cloud_cache.worker.offline import CacheOfflineWorker, OfflineWorker
from sakuraplayer.cloud_cache.worker.resolution import (
    CacheMediaResolver,
    CacheWorkerPipeline,
)
from sakuraplayer.discovery.ranking_sync import (
    RankingSnapshotSynchronizer,
    RankingSyncQueue,
)
from sakuraplayer.events.outbox import DomainEventWriter
from sakuraplayer.identity.crypto import SecretCipher, SettingsSecretKeyProvider
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.avdb_release import GitHubAvdbReleaseClient
from sakuraplayer.resources.avdb_worker import AvdbWorkerConsumer
from sakuraplayer.resources.initial_scope import InitialScopeSelector
from sakuraplayer.resources.rejection import SourceRejectionService
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import SourceSubmissionService
from sakuraplayer.resources.sync_service import (
    AvdbSyncQueue,
    AvdbSyncService,
    Importer,
)
from sakuraplayer.shared.config import (
    Settings,
    StartupConfigurationError,
    load_settings,
)
from sakuraplayer.shared.runtime import (
    configure_component_logging,
    guarded_main,
    require_ready,
)
from sakuraplayer.worker.metadata_child import metadata_executor_available
from sakuraplayer.worker.metadata_supervisor import (
    MetadataSupervisor,
    SubprocessGroupLauncher,
)
from sakuraplayer.worker.provider_snapshots import ProviderSnapshotConsumer
from sakuraplayer.worker.rankings import RankingConsumer

PROVIDER_CACHE_DIRECTORY = Path("/var/lib/sakuraplayer/provider-cache")
IDLE_WAIT_SECONDS = 5.0
SUPERVISOR_TICK_SECONDS = 1.0
WORKER_THREAD_JOIN_SECONDS = 5.0


class StopEvent(Protocol):
    def is_set(self) -> bool: ...

    def set(self) -> None: ...

    def wait(self, timeout: float) -> bool: ...


class Consumer(Protocol):
    def run_once(self, *, worker_id: str, importer: Importer) -> str: ...


class SnapshotConsumer(Protocol):
    def run_once(self, *, worker_id: str) -> str: ...


@dataclass
class WorkerRuntime:
    consumer: AvdbWorkerConsumer
    importer: SourceImporter
    engine: Engine
    http_client: httpx.Client
    provider_snapshot_consumer: ProviderSnapshotConsumer
    metadata_supervisor: MetadataSupervisor
    metadata_seeder: MetadataQueueSeeder
    ranking_consumer: RankingConsumer | None = None
    cache_consumer: OfflineWorker | None = None

    def close(self) -> None:
        try:
            self.http_client.close()
        finally:
            self.engine.dispose()


def consume_avdb_requests(
    *,
    consumer: Consumer,
    importer: SourceImporter,
    stop_event: StopEvent,
    worker_id: str,
    idle_wait_seconds: float = IDLE_WAIT_SECONDS,
) -> None:
    if not worker_id or len(worker_id) > 64 or idle_wait_seconds < 0:
        raise ValueError("invalid AVdb worker loop configuration")
    while not stop_event.is_set():
        outcome = consumer.run_once(
            worker_id=worker_id,
            importer=importer.import_batch,
        )
        if outcome == "idle":
            stop_event.wait(idle_wait_seconds)


def consume_provider_snapshot_requests(
    *,
    consumer: SnapshotConsumer,
    stop_event: StopEvent,
    worker_id: str,
    idle_wait_seconds: float = IDLE_WAIT_SECONDS,
) -> None:
    if not worker_id or len(worker_id) > 64 or idle_wait_seconds < 0:
        raise ValueError("invalid provider snapshot worker loop configuration")
    while not stop_event.is_set():
        outcome = consumer.run_once(worker_id=worker_id)
        if outcome == "idle":
            stop_event.wait(idle_wait_seconds)


def consume_cache_requests(
    *,
    consumer: OfflineWorker,
    stop_event: StopEvent,
    worker_id: str,
    idle_wait_seconds: float = IDLE_WAIT_SECONDS,
) -> None:
    if not worker_id or len(worker_id) > 64 or idle_wait_seconds < 0:
        raise ValueError("invalid cache worker loop configuration")
    while not stop_event.is_set():
        outcome = consumer.run_once(worker_id=worker_id)
        if outcome == "idle":
            stop_event.wait(idle_wait_seconds)


def build_worker_runtime(settings: Settings) -> WorkerRuntime:
    if settings.settings_key is None:
        raise StartupConfigurationError(
            "SAKURAPLAYER_SETTINGS_KEY",
            "value is required",
        )
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
    )
    http_client = httpx.Client(headers={"User-Agent": "SakuraPlayer/0.1"})
    try:
        factory = sessionmaker(engine, expire_on_commit=False)
        cipher = SecretCipher(
            SettingsSecretKeyProvider(
                key_id=settings.settings_key_id,
                key=settings.settings_key,
            )
        )
        cache_root = PROVIDER_CACHE_DIRECTORY / "avdb"
        consumer = AvdbWorkerConsumer(
            queue=AvdbSyncQueue(factory),
            release_client=GitHubAvdbReleaseClient(http_client=http_client),
            sync_service=AvdbSyncService(factory),
            asset_directory=cache_root / "assets",
            plaintext_directory=cache_root / "plaintext",
        )
        metadata_queue = MetadataQueue(factory, event_writer=DomainEventWriter())
        metadata_supervisor = MetadataSupervisor(
            queue=metadata_queue,
            launcher=SubprocessGroupLauncher(
                command_factory=lambda claim: (
                    sys.executable,
                    "-m",
                    "sakuraplayer.worker.metadata_child",
                    "--job-id",
                    str(claim.job_id),
                    "--claim-owner",
                    claim.claim_owner,
                ),
                availability=metadata_executor_available,
            ),
        )
        metadata_seeder = MetadataQueueSeeder(
            factory,
            queue=metadata_queue,
            selector=InitialScopeSelector(factory),
        )
        provider_snapshot_consumer = ProviderSnapshotConsumer(
            queue=ProviderSnapshotQueue(factory),
            service=ProviderSnapshotRefreshService(
                factory,
                http_client=http_client,
                cache_root=PROVIDER_CACHE_DIRECTORY,
            ),
        )
        ranking_queue = RankingSyncQueue(factory)
        secret_repository = EncryptedSettingRepository(factory, cipher)
        credential_store = EncryptedJavdbCredentialStore(secret_repository)
        ranking_consumer = RankingConsumer(
            queue=ranking_queue,
            synchronizer=RankingSnapshotSynchronizer(
                ranking_queue,
                JavdbProvider(http_client=http_client),
                credentials=credential_store.load,
            ),
        )

        @asynccontextmanager
        async def cloud115_scope(
            cookies: str | None,
        ) -> AsyncIterator[Cloud115Port]:
            async with Cloud115Adapter(cookies) as cloud:
                yield cloud

        binding_service = BindingService(factory, secret_repository, cloud115_scope)

        @asynccontextmanager
        async def cache_cloud_scope(
            claim: CacheJobClaim,
        ) -> AsyncIterator[Cloud115Port]:
            async with binding_service.cache_operation_scope(
                binding_id=claim.binding_id,
                account_key=claim.account_key,
                cache_root_cid=claim.cache_root_cid,
            ) as cloud:
                yield cloud

        cache_queue = CacheJobClaimQueue(factory)
        source_submission = SourceSubmissionService(factory, cipher=cipher)
        source_rejection = SourceRejectionClient(
            source_submission,
            SourceRejectionService(factory),
        )
        offline_consumer = CacheOfflineWorker(
            cache_queue,
            source_submission,
            source_rejection,
            cache_cloud_scope,
        )
        cache_consumer = CacheWorkerPipeline(
            offline_consumer,
            CacheMediaResolver(cache_queue, source_rejection, cache_cloud_scope),
        )
        return WorkerRuntime(
            consumer=consumer,
            importer=SourceImporter(factory, cipher=cipher),
            engine=engine,
            http_client=http_client,
            provider_snapshot_consumer=provider_snapshot_consumer,
            metadata_supervisor=metadata_supervisor,
            metadata_seeder=metadata_seeder,
            ranking_consumer=ranking_consumer,
            cache_consumer=cache_consumer,
        )
    except Exception:
        http_client.close()
        engine.dispose()
        raise


def run_worker(
    *,
    runtime: WorkerRuntime,
    stop_event: StopEvent,
    worker_id: str,
    thread_join_seconds: float = WORKER_THREAD_JOIN_SECONDS,
    supervisor_tick_seconds: float = SUPERVISOR_TICK_SECONDS,
) -> None:
    if thread_join_seconds <= 0 or supervisor_tick_seconds <= 0:
        raise ValueError("worker loop timing must be positive")
    background_errors: list[BaseException] = []
    seeder_started = Event()
    snapshot_consumer_started = Event()
    ranking_consumer_started = Event()
    cache_consumer_started = Event()
    ranking_consumer = getattr(runtime, "ranking_consumer", None)
    cache_consumer = getattr(runtime, "cache_consumer", None)

    def run_avdb_consumer() -> None:
        try:
            consume_avdb_requests(
                consumer=runtime.consumer,
                importer=runtime.importer,
                stop_event=stop_event,
                worker_id=worker_id,
            )
        except BaseException as error:
            background_errors.append(error)
            stop_event.set()

    def run_metadata_seeder() -> None:
        seeder_started.set()
        try:
            while not stop_event.is_set():
                runtime.metadata_seeder.seed_once()
                stop_event.wait(supervisor_tick_seconds)
        except BaseException as error:
            background_errors.append(error)
            stop_event.set()

    def run_snapshot_consumer() -> None:
        snapshot_consumer_started.set()
        try:
            consume_provider_snapshot_requests(
                consumer=runtime.provider_snapshot_consumer,
                stop_event=stop_event,
                worker_id=worker_id,
            )
        except BaseException as error:
            background_errors.append(error)
            stop_event.set()

    def run_ranking_consumer() -> None:
        ranking_consumer_started.set()
        assert ranking_consumer is not None
        try:
            consume_provider_snapshot_requests(
                consumer=ranking_consumer,
                stop_event=stop_event,
                worker_id=worker_id,
            )
        except BaseException as error:
            background_errors.append(error)
            stop_event.set()

    def run_cache_consumer() -> None:
        cache_consumer_started.set()
        assert cache_consumer is not None
        try:
            consume_cache_requests(
                consumer=cache_consumer,
                stop_event=stop_event,
                worker_id=worker_id,
            )
        except BaseException as error:
            background_errors.append(error)
            stop_event.set()

    avdb_thread = Thread(
        target=run_avdb_consumer,
        name="avdb-consumer",
        daemon=True,
    )
    seeder_thread = Thread(
        target=run_metadata_seeder,
        name="metadata-seeder",
        daemon=True,
    )
    snapshot_thread = Thread(
        target=run_snapshot_consumer,
        name="provider-snapshot-consumer",
        daemon=True,
    )
    threads = [avdb_thread, seeder_thread, snapshot_thread]
    if ranking_consumer is not None:
        threads.append(
            Thread(
                target=run_ranking_consumer,
                name="ranking-consumer",
                daemon=True,
            )
        )
    if cache_consumer is not None:
        threads.append(
            Thread(
                target=run_cache_consumer,
                name="cache-consumer",
                daemon=True,
            )
        )
    for thread in threads:
        thread.start()
    seeder_started.wait(thread_join_seconds)
    snapshot_consumer_started.wait(thread_join_seconds)
    if ranking_consumer is not None:
        ranking_consumer_started.wait(thread_join_seconds)
    if cache_consumer is not None:
        cache_consumer_started.wait(thread_join_seconds)
    loop_error: BaseException | None = None
    shutdown_error: BaseException | None = None
    try:
        while not stop_event.is_set():
            runtime.metadata_supervisor.tick(worker_id=worker_id)
            stop_event.wait(supervisor_tick_seconds)
    except BaseException as error:
        loop_error = error
    finally:
        stop_event.set()
        try:
            runtime.metadata_supervisor.shutdown()
        except BaseException as error:
            shutdown_error = error
        for thread in threads:
            thread.join(thread_join_seconds)
    timed_out = any(thread.is_alive() for thread in threads)
    if loop_error is not None:
        raise loop_error
    if background_errors:
        raise background_errors[0]
    if shutdown_error is not None:
        raise shutdown_error
    if timed_out:
        raise RuntimeError("worker_thread_shutdown_timeout")


def main() -> None:
    settings = load_settings()
    require_ready(settings)
    logger = configure_component_logging("worker", settings.log_level)
    runtime = build_worker_runtime(settings)
    stop_event = Event()

    def request_stop(signum, frame) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker_id = f"{socket.gethostname()}-{os.getpid()}"[:64]
    logger.info("component_started")
    try:
        run_worker(runtime=runtime, stop_event=stop_event, worker_id=worker_id)
    finally:
        runtime.close()
        logger.info("component_stopped")


if __name__ == "__main__":
    guarded_main("worker", main)
