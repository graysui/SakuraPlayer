from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.api.diagnostics import DiagnosticsService
from sakuraplayer.api.settings import SettingsService
from sakuraplayer.catalog.metadata_api import MetadataAdminService
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.providers.javdb import (
    EncryptedJavdbCredentialStore,
    MetadataProviderProblem,
)
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.catalog.translation.config import EncryptedAiConfigurationStore
from sakuraplayer.discovery.favorites import FavoriteService
from sakuraplayer.discovery.ranking_query import RankingQueryService
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.events.outbox import DomainEventWriter, EventLog
from sakuraplayer.events.snapshot import EventSnapshotService
from sakuraplayer.identity.crypto import SecretCipher, SettingsSecretKeyProvider
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.identity.service import AuthService
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
    factory = sessionmaker(engine, expire_on_commit=False)
    identity_service = AuthService(
        session_factory=factory,
        token_key=settings.token_key,
        bootstrap_token=settings.bootstrap_token,
    )
    secret_repository = EncryptedSettingRepository(
        factory,
        SecretCipher(
            SettingsSecretKeyProvider(
                key_id=settings.settings_key_id,
                key=settings.settings_key,
            )
        ),
    )
    event_writer = DomainEventWriter()
    event_log = EventLog(factory)
    metadata_queue = MetadataQueue(factory, event_writer=event_writer)
    credential_store = EncryptedJavdbCredentialStore(secret_repository)
    settings_service = SettingsService(
        factory,
        secret_repository,
        credential_store,
        EncryptedAiConfigurationStore(secret_repository),
    )

    def credential_status() -> str:
        try:
            return "configured" if credential_store.load() is not None else "not_configured"
        except MetadataProviderProblem:
            return "invalid"

    favorite_service = FavoriteService(factory)
    catalog_query_service = CatalogQueryService(
        factory,
        favorite_port=favorite_service,
        image_root=Path("/var/lib/sakuraplayer/catalog-images"),
    )
    app = create_app(
        readiness_probe=lambda: is_ready(settings),
        identity_service=identity_service,
        identification_service=IdentificationService(factory),
        movie_source_admin_service=MovieSourceService(factory),
        metadata_admin_service=MetadataAdminService(factory, metadata_queue),
        catalog_query_service=catalog_query_service,
        search_service=SearchService(catalog_query_service, metadata_queue),
        favorite_service=favorite_service,
        ranking_query_service=RankingQueryService(
            factory,
            catalog=catalog_query_service,
            completion=metadata_queue,
            credential_status=credential_status,
            current_year=lambda: datetime.now(ZoneInfo("Asia/Shanghai")).year,
        ),
        event_snapshot_service=EventSnapshotService(factory, event_log),
        event_log=event_log,
        settings_service=settings_service,
        diagnostics_service=DiagnosticsService(factory, settings_service),
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
