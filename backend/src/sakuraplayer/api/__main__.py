from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.api.app import create_app
from sakuraplayer.api.diagnostics import DiagnosticsService
from sakuraplayer.api.settings import ProbeResult, SettingsService
from sakuraplayer.catalog.cache_availability import CacheSourceAvailabilityPort
from sakuraplayer.catalog.metadata_api import MetadataAdminService
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.providers.javdb import (
    EncryptedJavdbCredentialStore,
    MetadataProviderProblem,
)
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.catalog.translation.config import EncryptedAiConfigurationStore
from sakuraplayer.cloud_cache.binding_service import BindingService
from sakuraplayer.cloud_cache.capacity import active_cache_jobs
from sakuraplayer.cloud_cache.cleanup import CleanupQueue
from sakuraplayer.cloud_cache.infrastructure.cloud115 import Cloud115Adapter
from sakuraplayer.cloud_cache.play_request import PlayRequestService
from sakuraplayer.cloud_cache.qr_service import QrSessionService
from sakuraplayer.discovery.favorites import FavoriteService
from sakuraplayer.discovery.ranking_query import RankingQueryService
from sakuraplayer.discovery.search_service import SearchService
from sakuraplayer.events.outbox import DomainEventWriter, EventLog
from sakuraplayer.events.snapshot import EventSnapshotService
from sakuraplayer.identity.crypto import SecretCipher, SettingsSecretKeyProvider
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.identity.service import AuthService
from sakuraplayer.playback.heartbeat import PlaybackHeartbeatService
from sakuraplayer.playback.hls import HlsStreamResolver
from sakuraplayer.playback.original import OriginalStreamResolver
from sakuraplayer.playback.progress import MoviePlaybackStateService
from sakuraplayer.playback.resolver import PlaybackStreamResolver
from sakuraplayer.playback.session import PlaybackSessionService
from sakuraplayer.playback.subtitles import SubtitleDownloadService
from sakuraplayer.resources.identification_api import IdentificationService
from sakuraplayer.resources.movie_source_service import MovieSourceService
from sakuraplayer.resources.source_submission import SourceSubmissionService
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
    if settings.playback_key is None:
        raise StartupConfigurationError(
            "SAKURAPLAYER_PLAYBACK_KEY", "value is required"
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
    secret_cipher = SecretCipher(
        SettingsSecretKeyProvider(
            key_id=settings.settings_key_id,
            key=settings.settings_key,
        )
    )
    secret_repository = EncryptedSettingRepository(factory, secret_cipher)
    event_writer = DomainEventWriter()
    event_log = EventLog(factory)
    metadata_queue = MetadataQueue(factory, event_writer=event_writer)
    credential_store = EncryptedJavdbCredentialStore(secret_repository)

    @asynccontextmanager
    async def cloud115_scope(cookies: str | None):
        async with Cloud115Adapter(cookies) as cloud:
            yield cloud

    binding_service = BindingService(
        factory,
        secret_repository,
        cloud115_scope,
        active_cache_jobs=active_cache_jobs,
    )
    qr_service = QrSessionService(cloud115_scope)
    cache_service = PlayRequestService(
        factory,
        SourceSubmissionService(factory, cipher=secret_cipher),
        ttl_hours=lambda: _cache_ttl_hours(secret_repository),
    )
    cache_cleanup_service = CleanupQueue(factory)
    playback_progress_service = MoviePlaybackStateService(factory)
    playback_session_service = PlaybackSessionService(
        factory,
        signing_key=settings.playback_key,
        ttl_hours=lambda: _cache_ttl_hours(secret_repository),
        progress_service=playback_progress_service,
    )
    playback_heartbeat_service = PlaybackHeartbeatService(
        factory,
        progress_service=playback_progress_service,
        ttl_hours=lambda: _cache_ttl_hours(secret_repository),
    )
    playback_stream_resolver = PlaybackStreamResolver(
        OriginalStreamResolver(binding_service),
        HlsStreamResolver(binding_service),
    )
    subtitle_download_service = SubtitleDownloadService(
        factory,
        binding_service,
    )

    def probe_cloud115() -> ProbeResult:
        view = asyncio.run(binding_service.probe())
        if view.status == "active":
            return ProbeResult("available")
        if view.status == "expired":
            return ProbeResult("credentials_invalid", "cloud115_credentials_expired")
        if view.status == "unbound":
            return ProbeResult("not_configured")
        return ProbeResult("unavailable", "cloud115_unavailable")

    settings_service = SettingsService(
        factory,
        secret_repository,
        credential_store,
        EncryptedAiConfigurationStore(secret_repository),
        probes={"cloud115": probe_cloud115},
    )

    def credential_status() -> str:
        try:
            return (
                "configured"
                if credential_store.load() is not None
                else "not_configured"
            )
        except MetadataProviderProblem:
            return "invalid"

    favorite_service = FavoriteService(factory)
    catalog_query_service = CatalogQueryService(
        factory,
        favorite_port=favorite_service,
        availability_port=CacheSourceAvailabilityPort(factory),
        playback_port=playback_progress_service,
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
        cloud115_binding_service=binding_service,
        cloud115_qr_service=qr_service,
        cache_service=cache_service,
        cache_cleanup_service=cache_cleanup_service,
        playback_session_service=playback_session_service,
        playback_stream_resolver=playback_stream_resolver,
        subtitle_download_service=subtitle_download_service,
        playback_progress_service=playback_progress_service,
        playback_heartbeat_service=playback_heartbeat_service,
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


def _cache_ttl_hours(repository: EncryptedSettingRepository) -> int:
    setting = repository.get_public("cache.ttl_hours")
    value = setting.value if setting is not None else 24
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 168:
        return value
    return 24


if __name__ == "__main__":
    guarded_main("api", main)
