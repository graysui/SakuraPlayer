from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from threading import Barrier

import httpx
import pytest
from alembic.config import Config
from PIL import Image
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from sakuraplayer.catalog.core_import import (
    CoreImportProblem,
    CoreMetadataImporter,
    MetadataWriteFence,
)
from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import (
    Actor,
    CatalogImage,
    MetadataJob,
    MetadataStage,
    MovieActor,
    Tag,
)
from sakuraplayer.catalog.providers.javdb import CoreActorMetadata, CoreMovieMetadata
from sakuraplayer.catalog.providers.runtime import build_metadata_stage_executor
from sakuraplayer.resources.models import Movie
from sakuraplayer.shared.config import Settings
from sakuraplayer.shared.migration import upgrade_database
from sakuraplayer.worker.metadata_child import MetadataChildRunner

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "metadata"
NOW = datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task008_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()
    test_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        upgrade_database(test_url, ALEMBIC_INI)
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


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color=(120, 30, 60)).save(output, format="PNG")
    return output.getvalue()


def app_settings(database_url: str) -> Settings:
    return Settings(
        environment="test",
        database_url=database_url,
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


def fake_client(*, fail_optional: bool) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if (
            request.url.host == "jdforrepam.com"
            and request.url.path == "/api/v2/search"
        ):
            return httpx.Response(200, text=fixture("javdb-search.json"))
        if request.url.host == "jdforrepam.com" and request.url.path.startswith(
            "/api/v4/movies/"
        ):
            return httpx.Response(200, text=fixture("javdb-detail.json"))
        if request.url.host == "www.dmm.co.jp":
            if fail_optional:
                return httpx.Response(503)
            return httpx.Response(200, text=fixture("dmm-description.html"))
        if request.url.host == "c0.jdbstatic.com":
            if fail_optional:
                return httpx.Response(503)
            return httpx.Response(
                200,
                headers={"Content-Type": "image/png"},
                content=png_bytes(),
            )
        raise AssertionError(f"unexpected fake request: {request.url}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_core_ready_survives_optional_failures_and_explicit_retry(
    database_url: str,
    tmp_path: Path,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
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
    claim = queue.claim_next("postgres-worker", lease_duration=timedelta(seconds=30))
    assert claim is not None
    failing_client = fake_client(fail_optional=True)
    try:
        executor = build_metadata_stage_executor(
            settings=app_settings(database_url),
            session_factory=factory,
            http_client=failing_client,
            image_root=tmp_path,
            now=lambda: NOW,
        )
        assert MetadataChildRunner(queue=queue, executor=executor).run(claim) == (
            "completed_with_warnings"
        )
    finally:
        failing_client.close()

    with factory() as session:
        persisted = session.get(Movie, movie.id)
        first_job = session.get(MetadataJob, outcome.job_id)
        images = list(session.scalars(select(CatalogImage)))
    assert persisted is not None and persisted.catalog_state == "core_ready"
    assert persisted.javdb_id == "fixture-abp-123"
    assert persisted.description_original is None
    assert first_job is not None and first_job.status == "completed_with_warnings"
    assert images and all(image.status == "retry_pending" for image in images)

    retry = queue.retry_enrichment(outcome.job_id, stages=("images", "dmm"))
    retry_claim = queue.claim_next(
        "postgres-retry",
        lease_duration=timedelta(seconds=30),
    )
    assert retry_claim is not None and retry_claim.job_id == retry.job_id
    good_client = fake_client(fail_optional=False)
    try:
        executor = build_metadata_stage_executor(
            settings=app_settings(database_url),
            session_factory=factory,
            http_client=good_client,
            image_root=tmp_path,
            now=lambda: NOW,
        )
        assert MetadataChildRunner(queue=queue, executor=executor).run(retry_claim) == (
            "completed"
        )
    finally:
        good_client.close()

    with factory() as session:
        persisted = session.get(Movie, movie.id)
        retry_job = session.get(MetadataJob, retry.job_id)
        retry_stages = list(
            session.scalars(
                select(MetadataStage).where(MetadataStage.job_id == retry.job_id)
            )
        )
        images = list(session.scalars(select(CatalogImage)))
    assert persisted is not None
    assert persisted.catalog_state == "core_ready"
    assert persisted.description_original == "Fixture first line. Fixture second line."
    assert retry_job is not None and retry_job.status == "completed"
    assert all(image.status == "ready" for image in images)
    assert {stage.stage for stage in retry_stages if stage.status == "succeeded"} == {
        "images",
        "dmm",
    }
    engine.dispose()


def test_concurrent_core_imports_share_actor_and_tag_without_false_failure(
    database_url: str,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    movies = [
        Movie(
            id=uuid.uuid4(),
            normalized_number=f"ABP-{number}",
            raw_numbers=[f"ABP-{number}"],
            catalog_state="raw_only",
            created_at=NOW,
            updated_at=NOW,
        )
        for number in (201, 202)
    ]
    with factory.begin() as session:
        session.add_all(movies)
    queue = MetadataQueue(factory, now=lambda: NOW)
    for movie in movies:
        queue.enqueue(
            movie_id=movie.id,
            normalized_number=movie.normalized_number,
            sort_date=date(2026, 7, 1),
            reason="initial",
        )
    claims = [
        queue.claim_next(
            f"concurrent-{index}",
            lease_duration=timedelta(seconds=30),
        )
        for index in range(2)
    ]
    assert all(claim is not None for claim in claims)
    for claim in claims:
        assert claim is not None
        queue.start_stage(claim, "javdb_core")
    barrier = Barrier(2)

    def import_one(index: int) -> None:
        claim = claims[index]
        assert claim is not None
        core = CoreMovieMetadata(
            javdb_id=f"movie-{index}",
            normalized_number=claim.normalized_number,
            title_original=f"Movie {index}",
            actors=(
                CoreActorMetadata(
                    javdb_id="shared-actor",
                    name="Shared Actor",
                    aliases=("Shared Alias",),
                ),
            ),
            tags=("Shared Tag",),
            score=Decimal("4.00"),
        )
        barrier.wait()
        CoreMetadataImporter(
            factory,
            placeholder_relative_path="_placeholder/catalog.png",
            now=lambda: NOW,
        ).import_core(
            movie_id=claim.movie_id,
            metadata=core,
            fence=MetadataWriteFence(
                job_id=claim.job_id,
                claim_owner=claim.claim_owner,
                movie_id=claim.movie_id,
                normalized_number=claim.normalized_number,
                stage="javdb_core",
            ),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(import_one, range(2)))

    with factory() as session:
        states = list(
            session.scalars(
                select(Movie.catalog_state)
                .where(Movie.id.in_([movie.id for movie in movies]))
                .order_by(Movie.normalized_number)
            )
        )
        actor_count = session.scalar(select(func.count(Actor.id)))
        tag_count = session.scalar(select(func.count(Tag.id)))
        relation_count = session.scalar(select(func.count(MovieActor.movie_id)))
    assert states == ["core_ready", "core_ready"]
    assert actor_count == 1
    assert tag_count == 1
    assert relation_count == 2
    engine.dispose()


def test_postgres_rejects_wrong_movie_fence_and_nonzero_cover_position(
    database_url: str,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    owner = Movie(
        id=uuid.uuid4(),
        normalized_number="ABP-301",
        raw_numbers=["ABP-301"],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
    target = Movie(
        id=uuid.uuid4(),
        normalized_number="ABP-302",
        raw_numbers=["ABP-302"],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add_all((owner, target))
    queue = MetadataQueue(factory, now=lambda: NOW)
    queue.enqueue(
        movie_id=owner.id,
        normalized_number=owner.normalized_number,
        sort_date=date(2026, 7, 1),
        reason="initial",
    )
    claim = queue.claim_next("wrong-fence", lease_duration=timedelta(seconds=30))
    assert claim is not None
    queue.start_stage(claim, "javdb_core")

    with pytest.raises(CoreImportProblem) as wrong_fence:
        CoreMetadataImporter(
            factory,
            placeholder_relative_path="_placeholder/catalog.png",
            now=lambda: NOW,
        ).import_core(
            movie_id=target.id,
            metadata=CoreMovieMetadata(
                javdb_id="target-javdb",
                normalized_number=target.normalized_number,
                title_original="Target",
            ),
            fence=MetadataWriteFence(
                job_id=claim.job_id,
                claim_owner=claim.claim_owner,
                movie_id=target.id,
                normalized_number=target.normalized_number,
                stage="javdb_core",
            ),
        )
    assert wrong_fence.value.code == "metadata_claim_lost"

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO catalog_image "
                    "(id, owner_type, owner_id, kind, position, source_url, "
                    "relative_path, sha256, status, created_at) VALUES "
                    "(:id, 'movie', :owner_id, 'cover', 7, :source_url, "
                    ":relative_path, :sha256, 'ready', :created_at)"
                ),
                {
                    "id": uuid.uuid4(),
                    "owner_id": owner.id,
                    "source_url": "https://c0.jdbstatic.com/fixture.png",
                    "relative_path": f"movie/{owner.id}/cover.png",
                    "sha256": "a" * 64,
                    "created_at": NOW,
                },
            )
    with factory() as session:
        assert session.get(Movie, target.id).catalog_state == "raw_only"
    engine.dispose()


def test_catalog_metadata_migration_downgrades_and_reupgrades(
    database_url: str,
) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(config, "0007_metadata_queue")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert "catalog_image" not in inspector.get_table_names()
        assert "javdb_id" not in {
            column["name"] for column in inspector.get_columns("movie")
        }
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert "catalog_image" in inspector.get_table_names()
        assert "javdb_id" in {
            column["name"] for column in inspector.get_columns("movie")
        }
    engine.dispose()
