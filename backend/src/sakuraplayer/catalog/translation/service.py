from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sakuraplayer.catalog.core_import import (
    MetadataWriteFence,
    require_active_metadata_claim,
)
from sakuraplayer.catalog.metadata_queue import MetadataClaim
from sakuraplayer.catalog.models import (
    Actor,
    MovieActor,
    MovieTag,
    Tag,
    TranslationRecord,
)
from sakuraplayer.catalog.translation.adapter import (
    MAX_TEXT_CHARACTERS,
    PROMPT_VERSION,
    TranslationAdapterError,
    TranslationRequest,
    TranslationResult,
)
from sakuraplayer.catalog.translation.config import (
    AiConfigurationSnapshot,
    EncryptedAiConfigurationStore,
    TranslationConfigurationError,
)
from sakuraplayer.catalog.translation.guard import ProtectedFields
from sakuraplayer.resources.models import Movie

_RESERVATION_LEASE = timedelta(seconds=30)


class TranslationServiceError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TranslationAdapter(Protocol):
    def translate(
        self,
        request: TranslationRequest,
        configuration: AiConfigurationSnapshot,
    ) -> TranslationResult: ...


@dataclass(frozen=True)
class _WorkItem:
    owner_type: str
    owner_id: uuid.UUID
    source_text: str
    protected: ProtectedFields


@dataclass(frozen=True)
class _Reservation:
    record_id: uuid.UUID
    claim_token: uuid.UUID | None
    translated_text: str | None


class TranslationService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        configuration_store: EncryptedAiConfigurationStore,
        adapter: TranslationAdapter,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._configuration_store = configuration_store
        self._adapter = adapter
        self._now = now or (lambda: datetime.now(timezone.utc))

    def execute(self, claim: MetadataClaim) -> None:
        try:
            configuration = self._configuration_store.load()
        except TranslationConfigurationError as error:
            raise TranslationServiceError(error.code) from None
        if configuration is None:
            raise TranslationServiceError("translation_not_configured")
        items = self._load_items(claim)
        failures: list[str] = []
        for item in items:
            try:
                self._translate_item(claim, item, configuration)
            except TranslationServiceError as error:
                failures.append(error.code)
        if failures:
            raise TranslationServiceError(failures[0])

    def _load_items(self, claim: MetadataClaim) -> tuple[_WorkItem, ...]:
        with self._session_factory() as session:
            movie = session.get(Movie, claim.movie_id)
            if movie is None or movie.catalog_state != "core_ready":
                raise TranslationServiceError("metadata_core_not_committed")
            actors = list(
                session.scalars(
                    select(Actor)
                    .join(MovieActor, MovieActor.actor_id == Actor.id)
                    .where(MovieActor.movie_id == movie.id)
                    .order_by(MovieActor.position)
                )
            )
            tags = tuple(
                session.scalars(
                    select(Tag.name)
                    .join(MovieTag, MovieTag.tag_id == Tag.id)
                    .where(MovieTag.movie_id == movie.id)
                    .order_by(Tag.name)
                )
            )
            protected = ProtectedFields(
                number=movie.normalized_number,
                actors=tuple(
                    actor.name_ja or actor.name_zh or actor.javdb_id for actor in actors
                ),
                maker=movie.maker,
                series=movie.series,
                tags=tags,
            )
            items: list[_WorkItem] = []
            if movie.title_original:
                items.append(
                    _WorkItem(
                        owner_type="movie_title",
                        owner_id=movie.id,
                        source_text=movie.title_original,
                        protected=protected,
                    )
                )
            if movie.description_original:
                items.append(
                    _WorkItem(
                        owner_type="movie_description",
                        owner_id=movie.id,
                        source_text=movie.description_original,
                        protected=protected,
                    )
                )
            items.extend(
                _WorkItem(
                    owner_type="actor_bio",
                    owner_id=actor.id,
                    source_text=actor.bio_original,
                    protected=protected,
                )
                for actor in actors
                if actor.bio_original and actor.bio_zh_source != "actor_mapping"
            )
            return tuple(items)

    def _translate_item(
        self,
        claim: MetadataClaim,
        item: _WorkItem,
        configuration: AiConfigurationSnapshot,
    ) -> None:
        if len(item.source_text) > MAX_TEXT_CHARACTERS:
            raise TranslationServiceError("translation_input_too_large")
        reservation = self._reserve(item, configuration)
        if reservation.translated_text is not None:
            self._apply_cached(claim, item, reservation.translated_text)
            return
        if reservation.claim_token is None:
            raise TranslationServiceError("translation_result_unavailable")
        self._mark_dispatched(claim, reservation)
        try:
            result = self._adapter.translate(
                TranslationRequest(
                    kind=item.owner_type,
                    source_text=item.source_text,
                    protected=item.protected,
                ),
                configuration,
            )
        except TranslationAdapterError as error:
            status = (
                "rejected"
                if error.code == "translation_guardrail_failed"
                else "unknown"
            )
            self._finalize_failure(
                claim,
                reservation,
                status=status,
                failure_code=error.code,
            )
            raise TranslationServiceError(error.code) from None
        self._finalize_success(claim, item, reservation, result.translated_text)

    def _reserve(
        self,
        item: _WorkItem,
        configuration: AiConfigurationSnapshot,
    ) -> _Reservation:
        current = self._utc_now()
        token = uuid.uuid4()
        record = TranslationRecord(
            id=uuid.uuid4(),
            owner_type=item.owner_type,
            owner_id=item.owner_id,
            source_text=item.source_text,
            source_hash=_source_hash(item.source_text),
            translated_text=None,
            model=configuration.model,
            prompt_version=PROMPT_VERSION,
            status="reserved",
            claim_token=token,
            claim_expires_at=current + _RESERVATION_LEASE,
            dispatch_started_at=None,
            failure_code=None,
            created_at=current,
            updated_at=current,
        )
        try:
            with self._session_factory.begin() as session:
                existing = self._find_record(
                    session,
                    item,
                    configuration,
                    for_update=True,
                )
                if existing is not None:
                    return self._claim_existing(existing, current)
                session.add(record)
                session.flush()
            return _Reservation(record.id, token, None)
        except IntegrityError:
            with self._session_factory.begin() as session:
                existing = self._find_record(
                    session,
                    item,
                    configuration,
                    for_update=True,
                )
                if existing is None:
                    raise
                return self._claim_existing(existing, current)

    def _claim_existing(
        self,
        record: TranslationRecord,
        current: datetime,
    ) -> _Reservation:
        if record.status == "completed" and record.translated_text is not None:
            return _Reservation(record.id, None, record.translated_text)
        if record.status != "reserved":
            raise TranslationServiceError("translation_result_unavailable")
        expiry = record.claim_expires_at
        if expiry is None or _aware(expiry) > current:
            raise TranslationServiceError("translation_dispatch_in_progress")
        token = uuid.uuid4()
        record.claim_token = token
        record.claim_expires_at = current + _RESERVATION_LEASE
        record.updated_at = current
        return _Reservation(record.id, token, None)

    def _mark_dispatched(
        self,
        claim: MetadataClaim,
        reservation: _Reservation,
    ) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            require_active_metadata_claim(
                session,
                _fence(claim),
                current=current,
            )
            record = session.get(
                TranslationRecord,
                reservation.record_id,
                with_for_update=True,
            )
            if (
                record is None
                or record.status != "reserved"
                or record.claim_token != reservation.claim_token
                or record.claim_expires_at is None
                or _aware(record.claim_expires_at) <= current
            ):
                raise TranslationServiceError("translation_dispatch_in_progress")
            record.status = "dispatched"
            record.claim_expires_at = None
            record.dispatch_started_at = current
            record.updated_at = current

    def _finalize_success(
        self,
        claim: MetadataClaim,
        item: _WorkItem,
        reservation: _Reservation,
        translated_text: str,
    ) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            require_active_metadata_claim(session, _fence(claim), current=current)
            record = self._require_dispatched(session, reservation)
            record.status = "completed"
            record.translated_text = translated_text
            record.claim_token = None
            record.updated_at = current
            self._apply_translation(session, item, translated_text, current=current)

    def _finalize_failure(
        self,
        claim: MetadataClaim,
        reservation: _Reservation,
        *,
        status: str,
        failure_code: str,
    ) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            require_active_metadata_claim(session, _fence(claim), current=current)
            record = self._require_dispatched(session, reservation)
            record.status = status
            record.claim_token = None
            record.failure_code = failure_code
            record.updated_at = current

    def _apply_cached(
        self,
        claim: MetadataClaim,
        item: _WorkItem,
        translated_text: str,
    ) -> None:
        current = self._utc_now()
        with self._session_factory.begin() as session:
            require_active_metadata_claim(session, _fence(claim), current=current)
            self._apply_translation(session, item, translated_text, current=current)

    @staticmethod
    def _apply_translation(
        session: Session,
        item: _WorkItem,
        translated_text: str,
        *,
        current: datetime,
    ) -> None:
        if item.owner_type in {"movie_title", "movie_description"}:
            movie = session.get(Movie, item.owner_id, with_for_update=True)
            if movie is None:
                return
            source_field = (
                "title_original"
                if item.owner_type == "movie_title"
                else "description_original"
            )
            translated_field = (
                "title_zh" if item.owner_type == "movie_title" else "description_zh"
            )
            if getattr(movie, source_field) == item.source_text:
                setattr(movie, translated_field, translated_text)
                movie.updated_at = current
            return
        actor = session.get(Actor, item.owner_id, with_for_update=True)
        if (
            actor is not None
            and actor.bio_original == item.source_text
            and actor.bio_zh_source != "actor_mapping"
        ):
            actor.bio_zh = translated_text
            actor.bio_zh_source = "ai"
            actor.updated_at = current

    @staticmethod
    def _require_dispatched(
        session: Session,
        reservation: _Reservation,
    ) -> TranslationRecord:
        record = session.get(
            TranslationRecord,
            reservation.record_id,
            with_for_update=True,
        )
        if (
            record is None
            or record.status != "dispatched"
            or record.claim_token != reservation.claim_token
        ):
            raise TranslationServiceError("translation_result_unavailable")
        return record

    @staticmethod
    def _find_record(
        session: Session,
        item: _WorkItem,
        configuration: AiConfigurationSnapshot,
        *,
        for_update: bool,
    ) -> TranslationRecord | None:
        statement = select(TranslationRecord).where(
            TranslationRecord.owner_type == item.owner_type,
            TranslationRecord.owner_id == item.owner_id,
            TranslationRecord.source_hash == _source_hash(item.source_text),
            TranslationRecord.model == configuration.model,
            TranslationRecord.prompt_version == PROMPT_VERSION,
        )
        if for_update:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def _utc_now(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise ValueError("translation clock must be timezone-aware")
        return current.astimezone(timezone.utc)


def _source_hash(source_text: str) -> str:
    return sha256(source_text.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _fence(claim: MetadataClaim) -> MetadataWriteFence:
    return MetadataWriteFence(
        job_id=claim.job_id,
        claim_owner=claim.claim_owner,
        movie_id=claim.movie_id,
        normalized_number=claim.normalized_number,
        stage="translation",
    )


__all__ = ["TranslationService", "TranslationServiceError"]
