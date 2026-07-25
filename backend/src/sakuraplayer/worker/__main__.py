from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import signal
import socket
from threading import Event
from typing import Protocol

import httpx
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.identity.crypto import SecretCipher, SettingsSecretKeyProvider
from sakuraplayer.resources.avdb_release import GitHubAvdbReleaseClient
from sakuraplayer.resources.avdb_worker import AvdbWorkerConsumer
from sakuraplayer.resources.source_importer import SourceImporter
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


PROVIDER_CACHE_DIRECTORY = Path("/var/lib/sakuraplayer/provider-cache")
IDLE_WAIT_SECONDS = 5.0


class StopEvent(Protocol):
    def is_set(self) -> bool: ...

    def wait(self, timeout: float) -> bool: ...


class Consumer(Protocol):
    def run_once(self, *, worker_id: str, importer: Importer) -> str: ...


@dataclass
class WorkerRuntime:
    consumer: AvdbWorkerConsumer
    importer: SourceImporter
    engine: Engine
    http_client: httpx.Client

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
        return WorkerRuntime(
            consumer=consumer,
            importer=SourceImporter(factory, cipher=cipher),
            engine=engine,
            http_client=http_client,
        )
    except Exception:
        http_client.close()
        engine.dispose()
        raise


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
        consume_avdb_requests(
            consumer=runtime.consumer,
            importer=runtime.importer,
            stop_event=stop_event,
            worker_id=worker_id,
        )
    finally:
        runtime.close()
        logger.info("component_stopped")


if __name__ == "__main__":
    guarded_main("worker", main)
