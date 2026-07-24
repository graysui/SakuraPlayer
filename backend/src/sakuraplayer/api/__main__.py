from __future__ import annotations

import uvicorn

from sakuraplayer.api.app import create_app
from sakuraplayer.shared.config import load_settings
from sakuraplayer.shared.runtime import (
    configure_component_logging,
    guarded_main,
    is_ready,
    require_ready,
)


def main() -> None:
    settings = load_settings()
    require_ready(settings)
    logger = configure_component_logging("api", settings.log_level)
    logger.info("component_started")
    app = create_app(readiness_probe=lambda: is_ready(settings))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower(),
        log_config=None,
        proxy_headers=settings.trust_proxy_headers,
    )


if __name__ == "__main__":
    guarded_main("api", main)
