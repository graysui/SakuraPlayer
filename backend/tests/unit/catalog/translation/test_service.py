from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import (
    Actor,
    MovieActor,
    MovieTag,
    Tag,
    TranslationRecord,
)
from sakuraplayer.catalog.translation.adapter import (
    PROMPT_VERSION,
    TranslationAdapterError,
    TranslationResult,
)
from sakuraplayer.catalog.translation.config import (
    AiConfiguration,
    EncryptedAiConfigurationStore,
)
from sakuraplayer.catalog.translation.service import (
    TranslationService,
    TranslationServiceError,
)
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc)


class FakeAdapter:
    def __init__(self, *, fail_first: bool = False, before_return=None) -> None:
        self.requests = []
        self.fail_first = fail_first
        self.before_return = before_return

    def translate(self, request, configuration):
        self.requests.append(request)
        if self.fail_first and len(self.requests) == 1:
            raise TranslationAdapterError("translation_upstream_error")
        if self.before_return is not None:
            self.before_return(request)
        return TranslationResult(translated_text=f"ZH:{request.source_text}")


def context(*, configured: bool = True, actor_has_chinese_bio: bool = False):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number="ABP-123",
        raw_numbers=["ABP-123"],
        javdb_id="movie-abp-123",
        title_original="Fixture title",
        title_zh=None,
        release_date=date(2026, 7, 1),
        maker="Fixture Maker",
        series="Fixture Series",
        director=None,
        description_original="Fixture description",
        description_zh=None,
        score=None,
        catalog_state="core_ready",
        metadata_updated_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    actor_a = Actor(
        id=uuid.uuid4(),
        javdb_id="actor-a",
        name_ja="Actor A",
        name_zh=None,
        bio_original="Actor A biography",
        bio_zh="演员甲简介" if actor_has_chinese_bio else None,
        bio_zh_source="actor_mapping" if actor_has_chinese_bio else None,
        gender="female",
        created_at=NOW,
        updated_at=NOW,
    )
    actor_b = Actor(
        id=uuid.uuid4(),
        javdb_id="actor-b",
        name_ja="Actor B",
        name_zh="演员乙",
        bio_original=None,
        bio_zh=None,
        bio_zh_source=None,
        gender="female",
        created_at=NOW,
        updated_at=NOW,
    )
    tag = Tag(id=uuid.uuid4(), name="Drama")
    with factory.begin() as session:
        session.add_all(
            (
                movie,
                actor_a,
                actor_b,
                tag,
                MovieActor(movie_id=movie.id, actor_id=actor_a.id, position=0),
                MovieActor(movie_id=movie.id, actor_id=actor_b.id, position=1),
                MovieTag(movie_id=movie.id, tag_id=tag.id),
            )
        )
    queue = MetadataQueue(factory, now=lambda: NOW)
    outcome = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=movie.release_date,
        reason="daily",
    )
    claim = queue.claim_next("translation-worker", lease_duration=timedelta(minutes=5))
    assert claim is not None
    with factory.begin() as session:
        persisted = session.get(Movie, movie.id)
        assert persisted is not None
        persisted.catalog_state = "core_ready"
    queue.start_stage(claim, "translation")

    cipher = SecretCipher(
        InMemorySecretKeyProvider(active_key_id="v1", keys={"v1": b"k" * 32})
    )
    config_store = EncryptedAiConfigurationStore(
        EncryptedSettingRepository(factory, cipher)
    )
    if configured:
        config_store.save(
            AiConfiguration(
                base_url="https://ai.example.test",
                api_key="fixture-key",
                model="fixture-model",
                timeout_seconds=60,
            ),
            expected_version=0,
        )
    return engine, factory, movie, actor_a, outcome, claim, config_store


def service(factory, config_store, adapter) -> TranslationService:
    return TranslationService(
        session_factory=factory,
        configuration_store=config_store,
        adapter=adapter,
        now=lambda: NOW,
    )


def test_service_translates_movie_fields_and_only_missing_actor_bio() -> None:
    engine, factory, movie, actor, _, claim, config_store = context()
    adapter = FakeAdapter()
    try:
        service(factory, config_store, adapter).execute(claim)

        assert [item.kind for item in adapter.requests] == [
            "movie_title",
            "movie_description",
            "actor_bio",
        ]
        with factory() as session:
            persisted_movie = session.get(Movie, movie.id)
            persisted_actor = session.get(Actor, actor.id)
            records = list(session.scalars(select(TranslationRecord)))
        assert persisted_movie is not None
        assert persisted_movie.title_zh == "ZH:Fixture title"
        assert persisted_movie.description_zh == "ZH:Fixture description"
        assert persisted_actor is not None
        assert persisted_actor.bio_zh == "ZH:Actor A biography"
        assert persisted_actor.bio_zh_source == "ai"
        assert len(records) == 3
        assert all(record.status == "completed" for record in records)
    finally:
        engine.dispose()


def test_completed_records_are_reused_without_new_provider_calls() -> None:
    engine, factory, _, _, _, claim, config_store = context()
    adapter = FakeAdapter()
    try:
        translation = service(factory, config_store, adapter)
        translation.execute(claim)
        translation.execute(claim)

        assert len(adapter.requests) == 3
    finally:
        engine.dispose()


def test_api_key_rotation_keeps_completed_business_key_reusable() -> None:
    engine, factory, _, _, _, claim, config_store = context()
    adapter = FakeAdapter()
    try:
        translation = service(factory, config_store, adapter)
        translation.execute(claim)
        config_store.save(
            AiConfiguration(
                base_url="https://other-ai.example.test",
                api_key="rotated-fixture-key",
                model="fixture-model",
                timeout_seconds=30,
            ),
            expected_version=1,
        )

        translation.execute(claim)

        assert len(adapter.requests) == 3
    finally:
        engine.dispose()


def test_missing_configuration_fails_before_provider_call() -> None:
    engine, factory, _, _, _, claim, config_store = context(configured=False)
    adapter = FakeAdapter()
    try:
        with pytest.raises(TranslationServiceError) as error:
            service(factory, config_store, adapter).execute(claim)

        assert error.value.code == "translation_not_configured"
        assert adapter.requests == []
    finally:
        engine.dispose()


def test_existing_mapping_bio_skips_actor_translation() -> None:
    engine, factory, _, _, _, claim, config_store = context(actor_has_chinese_bio=True)
    adapter = FakeAdapter()
    try:
        service(factory, config_store, adapter).execute(claim)

        assert [item.kind for item in adapter.requests] == [
            "movie_title",
            "movie_description",
        ]
    finally:
        engine.dispose()


def test_one_failed_item_does_not_stop_other_translation_items() -> None:
    engine, factory, movie, actor, _, claim, config_store = context()
    adapter = FakeAdapter(fail_first=True)
    try:
        with pytest.raises(TranslationServiceError) as error:
            service(factory, config_store, adapter).execute(claim)

        assert error.value.code == "translation_upstream_error"
        assert len(adapter.requests) == 3
        with factory() as session:
            persisted_movie = session.get(Movie, movie.id)
            persisted_actor = session.get(Actor, actor.id)
        assert persisted_movie is not None and persisted_movie.title_zh is None
        assert persisted_movie.description_zh == "ZH:Fixture description"
        assert persisted_actor is not None
        assert persisted_actor.bio_zh == "ZH:Actor A biography"
    finally:
        engine.dispose()


def test_unknown_business_key_is_not_dispatched_again() -> None:
    engine, factory, _, _, _, claim, config_store = context()
    adapter = FakeAdapter(fail_first=True)
    try:
        translation = service(factory, config_store, adapter)
        with pytest.raises(TranslationServiceError) as first:
            translation.execute(claim)
        assert first.value.code == "translation_upstream_error"
        assert len(adapter.requests) == 3

        with pytest.raises(TranslationServiceError) as repeated:
            translation.execute(claim)
        assert repeated.value.code == "translation_result_unavailable"
        assert len(adapter.requests) == 3
        with factory() as session:
            title_record = session.scalar(
                select(TranslationRecord).where(
                    TranslationRecord.owner_type == "movie_title"
                )
            )
        assert title_record is not None and title_record.status == "unknown"
    finally:
        engine.dispose()


def test_expired_undispatched_reservation_can_be_safely_reclaimed() -> None:
    engine, factory, movie, _, _, claim, config_store = context()
    source_text = "Fixture title"
    with factory.begin() as session:
        session.add(
            TranslationRecord(
                id=uuid.uuid4(),
                owner_type="movie_title",
                owner_id=movie.id,
                source_text=source_text,
                source_hash=sha256(source_text.encode("utf-8")).hexdigest(),
                translated_text=None,
                model="fixture-model",
                prompt_version=PROMPT_VERSION,
                status="reserved",
                claim_token=uuid.uuid4(),
                claim_expires_at=NOW - timedelta(seconds=1),
                dispatch_started_at=None,
                failure_code=None,
                created_at=NOW - timedelta(minutes=1),
                updated_at=NOW - timedelta(minutes=1),
            )
        )
    adapter = FakeAdapter()
    try:
        service(factory, config_store, adapter).execute(claim)

        assert len(adapter.requests) == 3
        with factory() as session:
            title_record = session.scalar(
                select(TranslationRecord).where(
                    TranslationRecord.owner_type == "movie_title"
                )
            )
        assert title_record is not None and title_record.status == "completed"
    finally:
        engine.dispose()


def test_source_change_after_dispatch_does_not_overwrite_current_display() -> None:
    engine, factory, movie, _, _, claim, config_store = context()
    changed = False

    def change_title(request) -> None:
        nonlocal changed
        if request.kind != "movie_title" or changed:
            return
        changed = True
        with factory.begin() as session:
            persisted = session.get(Movie, movie.id)
            assert persisted is not None
            persisted.title_original = "New source title"

    adapter = FakeAdapter(before_return=change_title)
    try:
        service(factory, config_store, adapter).execute(claim)

        with factory() as session:
            persisted = session.get(Movie, movie.id)
            title_record = session.scalar(
                select(TranslationRecord).where(
                    TranslationRecord.owner_type == "movie_title"
                )
            )
        assert persisted is not None
        assert persisted.title_original == "New source title"
        assert persisted.title_zh is None
        assert title_record is not None and title_record.status == "completed"
    finally:
        engine.dispose()


def test_new_source_replaces_only_previous_ai_translation() -> None:
    engine, factory, movie, actor, _, claim, config_store = context()
    adapter = FakeAdapter()
    try:
        translation = service(factory, config_store, adapter)
        translation.execute(claim)
        with factory.begin() as session:
            persisted_movie = session.get(Movie, movie.id)
            persisted_actor = session.get(Actor, actor.id)
            assert persisted_movie is not None and persisted_actor is not None
            persisted_movie.title_original = "Updated title"
            persisted_actor.bio_original = "Updated actor biography"

        translation.execute(claim)

        with factory() as session:
            persisted_movie = session.get(Movie, movie.id)
            persisted_actor = session.get(Actor, actor.id)
        assert persisted_movie is not None
        assert persisted_movie.title_zh == "ZH:Updated title"
        assert persisted_actor is not None
        assert persisted_actor.bio_zh == "ZH:Updated actor biography"
        assert persisted_actor.bio_zh_source == "ai"
    finally:
        engine.dispose()
