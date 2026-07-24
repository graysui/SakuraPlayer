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
