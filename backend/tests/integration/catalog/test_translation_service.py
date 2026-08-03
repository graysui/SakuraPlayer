from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import Actor, MovieActor, TranslationRecord
from sakuraplayer.catalog.translation.adapter import PROMPT_VERSION, TranslationResult
from sakuraplayer.catalog.translation.config import (
    AiConfiguration,
    EncryptedAiConfigurationStore,
)
from sakuraplayer.catalog.translation.service import (
    TranslationService,
    TranslationServiceError,
)
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import Movie
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 26, 10, 30, tzinfo=timezone.utc)


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task010_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()

    test_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        yield test_url
    finally:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin_engine.dispose()


class BlockingAdapter:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self._lock = Lock()
        self.calls = 0

    def translate(self, request, configuration):
        with self._lock:
            self.calls += 1
        self.entered.set()
        if not self.release.wait(5):
            raise AssertionError("translation test release timed out")
        return TranslationResult(translated_text="共享演员简介")


class ImmediateAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def translate(self, request, configuration):
        self.calls += 1
        return TranslationResult(translated_text="合成中文标题")


def test_shared_actor_is_dispatched_at_most_once_across_movie_workers(
    database_url: str,
) -> None:
    upgrade_database(database_url, ALEMBIC_INI)
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    actor = Actor(
        id=uuid.uuid4(),
        javdb_id="shared-actor",
        name_ja="Shared Actor",
        name_zh=None,
        bio_original="Shared biography",
        bio_zh=None,
        bio_zh_source=None,
        gender="female",
        created_at=NOW,
        updated_at=NOW,
    )
    movies = [
        Movie(
            id=uuid.uuid4(),
            normalized_number=f"ABP-12{index}",
            raw_numbers=[f"ABP-12{index}"],
            title_original=None,
            description_original=None,
            catalog_state="core_ready",
            created_at=NOW,
            updated_at=NOW,
        )
        for index in (3, 4)
    ]
    with factory.begin() as session:
        session.add(actor)
        session.add_all(movies)
        session.flush()
        session.add_all(
            MovieActor(movie_id=movie.id, actor_id=actor.id, position=0)
            for movie in movies
        )
    queue = MetadataQueue(factory, now=lambda: NOW)
    for movie in movies:
        queue.enqueue(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 1),
            reason="daily",
        )
    claims = [
        queue.claim_next(f"worker-{index}", lease_duration=timedelta(minutes=5))
        for index in (1, 2)
    ]
    assert all(claim is not None for claim in claims)
    for claim in claims:
        assert claim is not None
        queue.start_stage(claim, "translation")

    cipher = SecretCipher(
        InMemorySecretKeyProvider(active_key_id="v1", keys={"v1": b"k" * 32})
    )
    configuration_store = EncryptedAiConfigurationStore(
        EncryptedSettingRepository(factory, cipher)
    )
    configuration_store.save(
        AiConfiguration(
            base_url="https://ai.example.test",
            api_key="fixture-key",
            model="fixture-model",
            timeout_seconds=60,
        ),
        expected_version=0,
    )
    adapter = BlockingAdapter()
    services = [
        TranslationService(
            session_factory=factory,
            configuration_store=configuration_store,
            adapter=adapter,
            now=lambda: NOW,
        )
        for _ in claims
    ]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(services[0].execute, claims[0])
            assert adapter.entered.wait(5)
            second = pool.submit(services[1].execute, claims[1])
            with pytest.raises(TranslationServiceError) as blocked:
                second.result(timeout=5)
            assert blocked.value.code == "translation_result_unavailable"
            assert adapter.calls == 1
            adapter.release.set()
            first.result(timeout=5)

        with factory() as session:
            records = list(session.scalars(select(TranslationRecord)))
            persisted_actor = session.get(Actor, actor.id)
        assert len(records) == 1
        assert records[0].status == "completed"
        assert persisted_actor is not None
        assert persisted_actor.bio_zh == "共享演员简介"
    finally:
        adapter.release.set()
        engine.dispose()


def test_v2_dispatch_preserves_all_legacy_v1_failure_facts(
    database_url: str,
) -> None:
    upgrade_database(database_url, ALEMBIC_INI)
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number="ABP-225",
        raw_numbers=["ABP-225"],
        title_original="Synthetic title",
        description_original=None,
        catalog_state="core_ready",
        created_at=NOW,
        updated_at=NOW,
    )
    legacy_rows = [
        TranslationRecord(
            id=uuid.uuid4(),
            owner_type=owner_type,
            owner_id=movie.id if index == 0 else uuid.uuid4(),
            source_text=source_text,
            source_hash=sha256(source_text.encode("utf-8")).hexdigest(),
            translated_text=None,
            model="fixture-model",
            prompt_version="sakuraplayer-zh-v1",
            status=status,
            claim_token=uuid.uuid4() if status == "dispatched" else None,
            claim_expires_at=None,
            dispatch_started_at=NOW - timedelta(minutes=1),
            failure_code=(
                None
                if status == "dispatched"
                else (
                    "translation_guardrail_failed"
                    if status == "rejected"
                    else "translation_upstream_error"
                )
            ),
            created_at=NOW - timedelta(minutes=1),
            updated_at=NOW - timedelta(minutes=1),
        )
        for index, (owner_type, source_text, status) in enumerate(
            (
                ("movie_title", "Synthetic title", "unknown"),
                ("movie_description", "Legacy description", "rejected"),
                ("actor_bio", "Legacy biography", "dispatched"),
            )
        )
    ]
    with factory.begin() as session:
        session.add(movie)
        session.add_all(legacy_rows)
    queue = MetadataQueue(factory, now=lambda: NOW)
    queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 1),
        reason="daily",
    )
    claim = queue.claim_next("translation-worker", lease_duration=timedelta(minutes=5))
    assert claim is not None
    queue.start_stage(claim, "translation")
    cipher = SecretCipher(
        InMemorySecretKeyProvider(active_key_id="v1", keys={"v1": b"k" * 32})
    )
    configuration_store = EncryptedAiConfigurationStore(
        EncryptedSettingRepository(factory, cipher)
    )
    configuration_store.save(
        AiConfiguration(
            base_url="https://ai.example.test",
            api_key="fixture-key",
            model="fixture-model",
            timeout_seconds=60,
        ),
        expected_version=0,
    )
    adapter = ImmediateAdapter()
    try:
        TranslationService(
            session_factory=factory,
            configuration_store=configuration_store,
            adapter=adapter,
            now=lambda: NOW,
        ).execute(claim)

        with factory() as session:
            persisted_legacy = [
                session.get(TranslationRecord, row.id) for row in legacy_rows
            ]
            current = session.scalar(
                select(TranslationRecord).where(
                    TranslationRecord.owner_type == "movie_title",
                    TranslationRecord.owner_id == movie.id,
                    TranslationRecord.prompt_version == PROMPT_VERSION,
                )
            )
        assert adapter.calls == 1
        assert [row.status for row in persisted_legacy if row is not None] == [
            "unknown",
            "rejected",
            "dispatched",
        ]
        assert [row.failure_code for row in persisted_legacy if row is not None] == [
            "translation_upstream_error",
            "translation_guardrail_failed",
            None,
        ]
        assert current is not None and current.status == "completed"
    finally:
        engine.dispose()
