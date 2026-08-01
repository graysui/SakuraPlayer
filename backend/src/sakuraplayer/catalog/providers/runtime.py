from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.core_import import (
    CoreImportProblem,
    CoreMetadataImporter,
    MetadataWriteFence,
    require_active_metadata_claim,
)
from sakuraplayer.catalog.image_store import (
    ImageStoreProblem,
    PermanentImageStore,
    StoredImage,
)
from sakuraplayer.catalog.metadata_queue import MetadataClaim
from sakuraplayer.catalog.metadata_state import MetadataStageExecutionError
from sakuraplayer.catalog.models import (
    ActorMappingSnapshot,
    CatalogImage,
    GfriendsSnapshot,
)
from sakuraplayer.catalog.providers.dmm import DmmProvider
from sakuraplayer.catalog.providers.javdb import (
    EncryptedJavdbCredentialStore,
    JavdbProvider,
    MetadataProviderProblem,
)
from sakuraplayer.catalog.translation.adapter import OpenAiTranslationAdapter
from sakuraplayer.catalog.translation.config import EncryptedAiConfigurationStore
from sakuraplayer.catalog.translation.service import (
    TranslationService,
    TranslationServiceError,
)
from sakuraplayer.identity.crypto import SecretCipher, SettingsSecretKeyProvider
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import Movie
from sakuraplayer.shared.config import Settings

CATALOG_IMAGE_ROOT = Path("/var/lib/sakuraplayer/catalog-images")
_SNAPSHOT_STAGE_MODELS = {
    "actor_map": ActorMappingSnapshot,
    "gfriends": GfriendsSnapshot,
}


class CatalogMetadataStageExecutor:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        javdb: JavdbProvider,
        dmm: DmmProvider,
        image_store: PermanentImageStore,
        core_importer: CoreMetadataImporter,
        credential_store: EncryptedJavdbCredentialStore | None,
        translation_configuration_store: EncryptedAiConfigurationStore | None,
        translation_service: TranslationService | None,
        now: Callable[[], datetime],
    ) -> None:
        self._session_factory = session_factory
        self._javdb = javdb
        self._dmm = dmm
        self._image_store = image_store
        self._core_importer = core_importer
        self._credential_store = credential_store
        self._translation_configuration_store = translation_configuration_store
        self._translation_service = translation_service
        self._now = now

    @property
    def credential_store(self) -> EncryptedJavdbCredentialStore | None:
        return self._credential_store

    @property
    def translation_configuration_store(
        self,
    ) -> EncryptedAiConfigurationStore | None:
        return self._translation_configuration_store

    def execute(self, stage: str, claim: MetadataClaim) -> None:
        if stage == "javdb_core":
            self._execute_core(claim)
            return
        if stage == "images":
            self._execute_images(claim)
            return
        if stage == "dmm":
            self._execute_dmm(claim)
            return
        if stage in _SNAPSHOT_STAGE_MODELS:
            self._require_snapshot(claim, stage)
            return
        if stage == "translation":
            self._execute_translation(claim)
            return
        raise ValueError("invalid metadata stage")

    def _execute_core(self, claim: MetadataClaim) -> None:
        try:
            candidate = self._javdb.search_movie(claim.normalized_number)
            if candidate is None:
                raise MetadataStageExecutionError("javdb_movie_not_found")
            metadata = self._javdb.fetch_movie(candidate.javdb_id)
            self._core_importer.import_core(
                movie_id=claim.movie_id,
                metadata=metadata,
                fence=_fence(claim, "javdb_core"),
            )
        except MetadataStageExecutionError:
            raise
        except (MetadataProviderProblem, CoreImportProblem) as error:
            raise MetadataStageExecutionError(error.code) from None

    def _execute_images(self, claim: MetadataClaim) -> None:
        with self._session_factory() as session:
            pending = list(
                session.scalars(
                    select(CatalogImage)
                    .where(
                        CatalogImage.owner_type == "movie",
                        CatalogImage.owner_id == claim.movie_id,
                        CatalogImage.status == "retry_pending",
                    )
                    .order_by(CatalogImage.kind, CatalogImage.position)
                )
            )
        failure_code: str | None = None
        for image in pending:
            if image.source_url is None:
                failure_code = failure_code or "image_download_failed"
                continue
            try:
                stored = self._image_store.store(
                    owner_type=image.owner_type,
                    owner_id=image.owner_id,
                    kind=image.kind,
                    position=image.position,
                    source_url=image.source_url,
                )
                self._commit_stored_image(claim, image.id, image.source_url, stored)
            except ImageStoreProblem as error:
                failure_code = failure_code or error.code
        if failure_code is not None:
            raise MetadataStageExecutionError(failure_code)

    def _commit_stored_image(
        self,
        claim: MetadataClaim,
        image_id,
        source_url: str,
        stored: StoredImage,
    ) -> None:
        try:
            with self._session_factory.begin() as session:
                require_active_metadata_claim(
                    session,
                    _fence(claim, "images"),
                    current=self._utc_now(),
                )
                image = session.scalar(
                    select(CatalogImage)
                    .where(
                        CatalogImage.id == image_id,
                        CatalogImage.status == "retry_pending",
                        CatalogImage.source_url == source_url,
                    )
                    .with_for_update()
                )
                if image is None:
                    raise CoreImportProblem("metadata_image_state_conflict")
                image.relative_path = stored.relative_path
                image.sha256 = stored.sha256
                image.status = "ready"
        except Exception:
            self._image_store.discard(stored)
            raise

    def _execute_dmm(self, claim: MetadataClaim) -> None:
        try:
            description = self._dmm.fetch_description(claim.normalized_number)
        except MetadataProviderProblem as error:
            raise MetadataStageExecutionError(error.code) from None
        if description is None:
            return
        try:
            with self._session_factory.begin() as session:
                require_active_metadata_claim(
                    session,
                    _fence(claim, "dmm"),
                    current=self._utc_now(),
                )
                movie = session.get(Movie, claim.movie_id, with_for_update=True)
                if movie is None or movie.catalog_state != "core_ready":
                    raise CoreImportProblem("metadata_core_not_committed")
                if not movie.description_original:
                    movie.description_original = description
                    movie.updated_at = self._utc_now()
        except CoreImportProblem as error:
            raise MetadataStageExecutionError(error.code) from None

    def _require_snapshot(self, claim: MetadataClaim, stage: str) -> None:
        model = _SNAPSHOT_STAGE_MODELS[stage]
        try:
            with self._session_factory.begin() as session:
                require_active_metadata_claim(
                    session,
                    _fence(claim, stage),
                    current=self._utc_now(),
                )
                snapshot_id = session.scalar(
                    select(model.id).where(model.status == "current")
                )
                if snapshot_id is None:
                    raise MetadataStageExecutionError("provider_snapshot_unavailable")
        except CoreImportProblem as error:
            raise MetadataStageExecutionError(error.code) from None

    def _execute_translation(self, claim: MetadataClaim) -> None:
        if self._translation_service is None:
            raise MetadataStageExecutionError("translation_not_configured")
        try:
            self._translation_service.execute(claim)
        except TranslationServiceError as error:
            raise MetadataStageExecutionError(error.code) from None

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("metadata provider clock must be timezone-aware")
        return current.astimezone(timezone.utc)


def build_metadata_stage_executor(
    *,
    settings: Settings,
    session_factory: sessionmaker[Session],
    http_client: httpx.Client,
    image_root: Path = CATALOG_IMAGE_ROOT,
    now: Callable[[], datetime] | None = None,
) -> CatalogMetadataStageExecutor:
    clock = now or (lambda: datetime.now(timezone.utc))
    image_store = PermanentImageStore(root=image_root, http_client=http_client)
    placeholder = image_store.ensure_placeholder()
    credential_store = None
    translation_configuration_store = None
    translation_service = None
    if settings.settings_key is not None:
        cipher = SecretCipher(
            SettingsSecretKeyProvider(
                key_id=settings.settings_key_id,
                key=settings.settings_key,
            )
        )
        setting_repository = EncryptedSettingRepository(session_factory, cipher)
        credential_store = EncryptedJavdbCredentialStore(setting_repository)
        translation_configuration_store = EncryptedAiConfigurationStore(
            setting_repository
        )
        translation_service = TranslationService(
            session_factory=session_factory,
            configuration_store=translation_configuration_store,
            adapter=OpenAiTranslationAdapter(http_client),
            now=clock,
        )
    return CatalogMetadataStageExecutor(
        session_factory=session_factory,
        javdb=JavdbProvider(http_client=http_client, host=settings.javdb_host),
        dmm=DmmProvider(http_client=http_client),
        image_store=image_store,
        core_importer=CoreMetadataImporter(
            session_factory,
            placeholder_relative_path=placeholder,
            now=clock,
        ),
        credential_store=credential_store,
        translation_configuration_store=translation_configuration_store,
        translation_service=translation_service,
        now=clock,
    )


def _fence(claim: MetadataClaim, stage: str) -> MetadataWriteFence:
    return MetadataWriteFence(
        job_id=claim.job_id,
        claim_owner=claim.claim_owner,
        movie_id=claim.movie_id,
        normalized_number=claim.normalized_number,
        stage=stage,
    )


__all__ = [
    "CATALOG_IMAGE_ROOT",
    "CatalogMetadataStageExecutor",
    "build_metadata_stage_executor",
]
