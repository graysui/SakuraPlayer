from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import uuid
import json

import httpx
from PIL import Image
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import (
    ActorMappingSnapshot,
    CatalogImage,
    GfriendsSnapshot,
    MetadataJob,
    MetadataStage,
)
from sakuraplayer.catalog.core_import import CoreImportProblem
from sakuraplayer.catalog.providers.runtime import build_metadata_stage_executor
from sakuraplayer.catalog.translation.config import AiConfiguration
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie
from sakuraplayer.shared.config import Settings
from sakuraplayer.worker.metadata_child import MetadataChildRunner


NOW = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "metadata"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color=(120, 30, 60)).save(output, format="PNG")
    return output.getvalue()


def settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite+pysqlite://",
        log_level="INFO",
        publish_host="127.0.0.1",
        api_port=8000,
        trust_proxy_headers=False,
        settings_key_id="v1",
        settings_key=b"s" * 32,
        token_key=b"t" * 32,
        playback_key=b"p" * 32,
        bootstrap_token=b"b" * 43,
    )


def context():
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
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add(movie)
    queue = MetadataQueue(factory, now=lambda: NOW)
    outcome = queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 1),
        reason="initial",
    )
    claim = queue.claim_next("fixture-worker", lease_duration=timedelta(seconds=30))
    assert claim is not None
    return engine, factory, queue, movie, outcome, claim


def fake_client(
    *,
    image_status: int = 200,
    dmm_status: int = 200,
    ai_requests: list[dict] | None = None,
) -> httpx.Client:
    image = png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "javdb.com" and request.url.path == "/search":
            return httpx.Response(200, text=fixture("javdb-search.html"))
        if request.url.host == "javdb.com":
            return httpx.Response(200, text=fixture("javdb-detail.html"))
        if request.url.host == "www.dmm.co.jp":
            if dmm_status != 200:
                return httpx.Response(dmm_status)
            return httpx.Response(200, text=fixture("dmm-description.html"))
        if request.url.host == "c0.jdbstatic.com":
            if image_status != 200:
                return httpx.Response(image_status)
            return httpx.Response(
                200,
                headers={"Content-Type": "image/png"},
                content=image,
            )
        if request.url.host == "ai.example.test":
            body = json.loads(request.content)
            user = json.loads(body["messages"][1]["content"])
            if ai_requests is not None:
                ai_requests.append(user)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "schema_version": 1,
                                        "translated_text": f"ZH:{user['source_text']}",
                                        "protected": user["protected"],
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected fake request: {request.url}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_runtime_commits_core_and_isolates_unimplemented_optional_stages(
    tmp_path: Path,
) -> None:
    engine, factory, queue, movie, outcome, claim = context()
    client = fake_client()
    try:
        executor = build_metadata_stage_executor(
            settings=settings(),
            session_factory=factory,
            http_client=client,
            image_root=tmp_path,
            now=lambda: NOW,
        )

        result = MetadataChildRunner(queue=queue, executor=executor).run(claim)

        assert result == "completed_with_warnings"
        with factory() as session:
            persisted = session.get(Movie, movie.id)
            job = session.get(MetadataJob, outcome.job_id)
            stages = {
                item.stage: item
                for item in session.scalars(
                    select(MetadataStage).where(MetadataStage.job_id == outcome.job_id)
                )
            }
            images = list(session.scalars(select(CatalogImage)))
        assert persisted is not None and persisted.catalog_state == "core_ready"
        assert persisted.description_original == "Fixture first line. Fixture second line."
        assert job is not None and job.status == "completed_with_warnings"
        assert stages["javdb_core"].status == "succeeded"
        assert stages["images"].status == "succeeded"
        assert stages["dmm"].status == "succeeded"
        assert stages["actor_map"].failure_code == "provider_snapshot_unavailable"
        assert stages["gfriends"].failure_code == "provider_snapshot_unavailable"
        assert stages["translation"].failure_code == "translation_not_configured"
        assert all(image.status == "ready" for image in images)
        assert all((tmp_path / image.relative_path).is_file() for image in images)
    finally:
        client.close()
        engine.dispose()


def test_dmm_and_image_failures_do_not_roll_back_core_and_retry_succeeds(
    tmp_path: Path,
) -> None:
    engine, factory, queue, movie, outcome, claim = context()
    failing_client = fake_client(image_status=503, dmm_status=503)
    try:
        failing = build_metadata_stage_executor(
            settings=settings(),
            session_factory=factory,
            http_client=failing_client,
            image_root=tmp_path,
            now=lambda: NOW,
        )
        assert MetadataChildRunner(queue=queue, executor=failing).run(claim) == (
            "completed_with_warnings"
        )
        with factory() as session:
            persisted = session.get(Movie, movie.id)
            images = list(session.scalars(select(CatalogImage)))
        assert persisted is not None and persisted.catalog_state == "core_ready"
        assert persisted.description_original is None
        assert images and all(image.status == "retry_pending" for image in images)

        retry = queue.retry_enrichment(outcome.job_id, stages=("images", "dmm"))
        retry_claim = queue.claim_next(
            "fixture-retry",
            lease_duration=timedelta(seconds=30),
        )
        assert retry_claim is not None and retry_claim.job_id == retry.job_id
        good_client = fake_client()
        try:
            good = build_metadata_stage_executor(
                settings=settings(),
                session_factory=factory,
                http_client=good_client,
                image_root=tmp_path,
                now=lambda: NOW,
            )
            assert MetadataChildRunner(queue=queue, executor=good).run(retry_claim) == (
                "completed"
            )
        finally:
            good_client.close()
        with factory() as session:
            persisted = session.get(Movie, movie.id)
            images = list(session.scalars(select(CatalogImage)))
        assert persisted is not None
        assert persisted.description_original == "Fixture first line. Fixture second line."
        assert all(image.status == "ready" for image in images)
    finally:
        failing_client.close()
        engine.dispose()


def test_dmm_supplement_does_not_overwrite_existing_description(
    tmp_path: Path,
) -> None:
    engine, factory, queue, movie, _, claim = context()
    with factory.begin() as session:
        persisted = session.get(Movie, movie.id)
        assert persisted is not None
        persisted.description_original = "Existing core description"
    client = fake_client()
    try:
        executor = build_metadata_stage_executor(
            settings=settings(),
            session_factory=factory,
            http_client=client,
            image_root=tmp_path,
            now=lambda: NOW,
        )
        MetadataChildRunner(queue=queue, executor=executor).run(claim)
        with factory() as session:
            persisted = session.get(Movie, movie.id)
        assert persisted is not None
        assert persisted.description_original == "Existing core description"
    finally:
        client.close()
        engine.dispose()


def test_claim_lost_after_reusing_digest_keeps_existing_ready_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, factory, queue, movie, _, claim = context()
    queue.start_stage(claim, "javdb_core")
    source_url = "https://c0.jdbstatic.com/images/fixture.png"
    with factory.begin() as session:
        persisted = session.get(Movie, movie.id)
        assert persisted is not None
        persisted.catalog_state = "core_ready"
        session.add(
            CatalogImage(
                id=uuid.uuid4(),
                owner_type="movie",
                owner_id=movie.id,
                kind="cover",
                position=0,
                source_url=source_url,
                relative_path="_placeholder/catalog.png",
                sha256=None,
                status="retry_pending",
                created_at=NOW,
            )
        )
    queue.finish_stage(claim, "javdb_core", status="succeeded")
    queue.start_stage(claim, "images")
    client = fake_client()
    try:
        executor = build_metadata_stage_executor(
            settings=settings(),
            session_factory=factory,
            http_client=client,
            image_root=tmp_path,
            now=lambda: NOW,
        )
        preexisting = executor._image_store.store(
            owner_type="movie",
            owner_id=movie.id,
            kind="cover",
            position=0,
            source_url=source_url,
        )
        original_store = executor._image_store.store

        def reuse_then_expire(**kwargs):
            stored = original_store(**kwargs)
            assert stored.created_new is False
            queue.expire(claim)
            return stored

        monkeypatch.setattr(executor._image_store, "store", reuse_then_expire)

        with pytest.raises(CoreImportProblem) as lost:
            executor.execute("images", claim)

        assert lost.value.code == "metadata_claim_lost"
        assert (tmp_path / preexisting.relative_path).is_file()
        with factory() as session:
            image = session.scalar(select(CatalogImage))
        assert image is not None and image.status == "retry_pending"
    finally:
        client.close()
        engine.dispose()


def test_runtime_succeeds_snapshot_stages_when_current_snapshots_exist(
    tmp_path: Path,
) -> None:
    engine, factory, queue, _, outcome, claim = context()
    with factory.begin() as session:
        session.add_all(
            (
                ActorMappingSnapshot(
                    id=uuid.uuid4(),
                    sha256="a" * 64,
                    byte_size=100,
                    relative_path="metadata/actor_mapping/a.xml",
                    status="current",
                    fetched_at=NOW,
                    activated_at=NOW,
                ),
                GfriendsSnapshot(
                    id=uuid.uuid4(),
                    sha256="b" * 64,
                    byte_size=100,
                    relative_path="metadata/gfriends/b.json",
                    status="current",
                    fetched_at=NOW,
                    activated_at=NOW,
                ),
            )
        )
    client = fake_client()
    try:
        executor = build_metadata_stage_executor(
            settings=settings(),
            session_factory=factory,
            http_client=client,
            image_root=tmp_path,
            now=lambda: NOW,
        )

        result = MetadataChildRunner(queue=queue, executor=executor).run(claim)

        assert result == "completed_with_warnings"
        with factory() as session:
            stages = {
                item.stage: item
                for item in session.scalars(
                    select(MetadataStage).where(MetadataStage.job_id == outcome.job_id)
                )
            }
        assert stages["actor_map"].status == "succeeded"
        assert stages["gfriends"].status == "succeeded"
        assert stages["translation"].failure_code == "translation_not_configured"
    finally:
        client.close()
        engine.dispose()


def test_runtime_executes_configured_translation_stage(tmp_path: Path) -> None:
    engine, factory, queue, movie, outcome, claim = context()
    ai_requests: list[dict] = []
    client = fake_client(ai_requests=ai_requests)
    try:
        executor = build_metadata_stage_executor(
            settings=settings(),
            session_factory=factory,
            http_client=client,
            image_root=tmp_path,
            now=lambda: NOW,
        )
        assert executor.translation_configuration_store is not None
        executor.translation_configuration_store.save(
            AiConfiguration(
                base_url="https://ai.example.test",
                api_key="fixture-key",
                model="fixture-model",
                timeout_seconds=60,
            ),
            expected_version=0,
        )

        result = MetadataChildRunner(queue=queue, executor=executor).run(claim)

        assert result == "completed_with_warnings"
        assert [item["kind"] for item in ai_requests] == [
            "movie_title",
            "movie_description",
        ]
        with factory() as session:
            persisted = session.get(Movie, movie.id)
            stages = {
                item.stage: item
                for item in session.scalars(
                    select(MetadataStage).where(MetadataStage.job_id == outcome.job_id)
                )
            }
        assert persisted is not None
        assert persisted.title_zh == "ZH:Fixture Original Title"
        assert persisted.description_zh == (
            "ZH:Fixture first line. Fixture second line."
        )
        assert stages["translation"].status == "succeeded"
    finally:
        client.close()
        engine.dispose()
