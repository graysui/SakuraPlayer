from __future__ import annotations

import logging

import sakuraplayer.shared.runtime as runtime


def test_component_logging_writes_safe_persistent_log(tmp_path) -> None:
    configure = getattr(runtime, "configure_component_logging", None)

    assert callable(configure)

    logger = configure("worker", "INFO", log_directory=tmp_path)
    logger.info("component_started", extra={"component": "worker"})
    for handler in logging.getLogger().handlers:
        handler.flush()

    content = (tmp_path / "worker.log").read_text(encoding="utf-8")
    assert "component_started" in content
    assert "worker" in content


def test_component_logging_redacts_secrets_and_capability_urls(tmp_path) -> None:
    logger = runtime.configure_component_logging(
        "api",
        "INFO",
        log_directory=tmp_path,
    )
    logger.info(
        "upstream=%s cookie=%s",
        "https://cdn.example/video?signature=private-signature",
        "private-cookie",
        extra={"api_key": "private-ai-key"},
    )
    for handler in logging.getLogger().handlers:
        handler.flush()

    content = (tmp_path / "api.log").read_text(encoding="utf-8")
    for secret in ("private-signature", "private-cookie", "private-ai-key"):
        assert secret not in content


def test_component_handlers_filter_propagated_access_logs(tmp_path) -> None:
    runtime.configure_component_logging("api", "INFO", log_directory=tmp_path)
    logging.getLogger("uvicorn.access").info(
        '%s - "GET %s HTTP/1.1" 302',
        "127.0.0.1",
        "/play/stream?signature=private-signature&token=private-token",
    )
    for handler in logging.getLogger().handlers:
        handler.flush()

    content = (tmp_path / "api.log").read_text(encoding="utf-8")
    assert "/play/stream" in content
    assert "private-signature" not in content
    assert "private-token" not in content
