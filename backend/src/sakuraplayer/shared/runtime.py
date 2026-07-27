from __future__ import annotations

import logging
import signal
import sys
from collections.abc import Callable
from pathlib import Path
from threading import Event

from sakuraplayer.shared.config import (
    Settings,
    StartupConfigurationError,
    load_settings,
)
from sakuraplayer.shared.redaction import RedactionFilter
from sakuraplayer.shared.schema_guard import SchemaGuardError, check_schema

LOG_DIRECTORY = Path("/var/log/sakuraplayer")


def backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def alembic_ini() -> Path:
    return backend_root() / "alembic.ini"


def is_ready(settings: Settings) -> bool:
    try:
        check_schema(settings.database_url, alembic_ini())
    except SchemaGuardError:
        return False
    return True


def require_ready(settings: Settings) -> None:
    check_schema(settings.database_url, alembic_ini())


def guarded_main(component: str, entrypoint: Callable[[], None]) -> None:
    try:
        entrypoint()
    except (StartupConfigurationError, SchemaGuardError) as error:
        sys.stderr.write(f"startup_failed component={component} code={error.code}\n")
        raise SystemExit(1) from None


def configure_component_logging(
    component: str,
    level: str,
    *,
    log_directory: Path = LOG_DIRECTORY,
) -> logging.Logger:
    log_directory.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        f"%(asctime)s %(levelname)s component={component} %(message)s"
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(RedactionFilter())
    file_handler = logging.FileHandler(
        log_directory / f"{component}.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactionFilter())
    logging.basicConfig(
        level=level,
        handlers=[stream_handler, file_handler],
        force=True,
    )
    return logging.getLogger(component)


def run_process(component: str) -> None:
    settings = load_settings()
    require_ready(settings)
    logger = configure_component_logging(component, settings.log_level)
    stop_event = Event()

    def request_stop(signum, frame) -> None:
        del signum, frame
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    logger.info("component_started", extra={"component": component})
    while not stop_event.wait(30):
        require_ready(settings)
    logger.info("component_stopped", extra={"component": component})
