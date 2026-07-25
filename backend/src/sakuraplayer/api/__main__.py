from __future__ import annotations

import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.identity.service import AuthService
from sakuraplayer.identity.crypto import SecretCipher, SettingsSecretKeyProvider
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.identification_api import IdentificationService
from sakuraplayer.resources.movie_source_service import MovieSourceService
from sakuraplayer.shared.config import StartupConfigurationError, load_settings
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
    if settings.token_key is None:
        raise StartupConfigurationError("SAKURAPLAYER_TOKEN_KEY", "value is required")
    if settings.bootstrap_token is None:
        raise StartupConfigurationError(
            "SAKURAPLAYER_BOOTSTRAP_TOKEN",
            "value is required",
        )
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
    identity_service = AuthService(
        session_factory=sessionmaker(engine, expire_on_commit=False),
        token_key=settings.token_key,
        bootstrap_token=settings.bootstrap_token,
    )
    secret_repository = EncryptedSettingRepository(
        sessionmaker(engine, expire_on_commit=False),
        SecretCipher(
            SettingsSecretKeyProvider(
                key_id=settings.settings_key_id,
                key=settings.settings_key,
            )
        ),
    )
    app = create_app(
        readiness_probe=lambda: is_ready(settings),
        identity_service=identity_service,
        identification_service=IdentificationService(
            sessionmaker(engine, expire_on_commit=False)
        ),
        movie_source_admin_service=MovieSourceService(
            sessionmaker(engine, expire_on_commit=False)
        ),
    )
    app.add_event_handler("shutdown", engine.dispose)
    app.state.secret_repository = secret_repository
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
