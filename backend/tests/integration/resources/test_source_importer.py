from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.resources.avdb_release import FetchedAsset, FetchedRelease
from sakuraplayer.resources.avdb_worker import AvdbWorkerConsumer
from sakuraplayer.resources.initial_scope import InitialScopeSelector
from sakuraplayer.resources.models import AvdbSyncRequest, Movie, ResourceSource
from sakuraplayer.resources.source_importer import (
    SourceImporter,
    SourceImportError,
    source_magnet_context,
)
from sakuraplayer.resources.sync_service import (
    AvdbSyncQueue,
    AvdbSyncService,
    BatchStats,
)
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
NOW = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Rows:
    manifest_summary = {
        "algorithm": "AES-256-GCM",
        "iterations": 200_000,
        "kdf": "PBKDF2-HMAC-SHA256",
        "key_length": 32,
    }

    def iter_rows(self):
        yield avdb_row(900, number="SSIS-900")


class SuccessfulReleaseClient:
    def fetch_release(self, *, mode, destination, validator):
        del destination, validator
        return FetchedRelease(
            repository="li-peifeng/AVdb-Only",
            release_id="task005-worker",
            tag="2026.07.25",
            mode=mode,
            assets=(
                FetchedAsset(
                    name="30D_202607250300.zip",
                    path=Path("fixture.zip"),
                    sha256="a" * 64,
                    byte_size=100,
                    validation=Rows(),
                ),
            ),
        )


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task005_{uuid.uuid4().hex}"
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


@pytest.fixture
def importer(database_url: str) -> tuple[SourceImporter, sessionmaker, SecretCipher]:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"k" * 32},
        )
    )
    service = SourceImporter(factory, cipher=cipher, now=lambda: NOW)
    try:
        yield service, factory, cipher
    finally:
        engine.dispose()


def avdb_row(
    tid: int,
    *,
    number: str | None = "ABP-001",
    section: str = "亚洲有码",
    title: str | None = None,
    website: str = "sehuatang",
    publish_date: date | None = date(2026, 7, 24),
) -> dict[str, object]:
    return {
        "tid": tid,
        "number": number,
        "title": title or f"Title {tid}",
        "publish_date": publish_date,
        "magnet": f"urn:fixture-resource-{tid}",
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/thread-fixture.htm",
        "size": 1024,
        "section": section,
        "category": None,
        "website": website,
        "create_time": datetime(2026, 7, 24, 1, 0),
        "update_time": datetime(2026, 7, 24, 2, 0),
    }


def test_imports_target_sections_and_builds_deduplicated_movie_skeletons(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, cipher = importer

    stats = service.import_batch(
        "All_fixture.zip",
        (
            avdb_row(1),
            avdb_row(2, number="abp_001"),
            avdb_row(3, number=None, section="FC2"),
            avdb_row(4, section="欧美"),
        ),
    )

    assert stats == BatchStats(inserted=3, skipped=1, pending=1)
    with factory() as session:
        movies = list(session.scalars(select(Movie)))
        sources = list(
            session.scalars(
                select(ResourceSource).order_by(ResourceSource.external_post_id)
            )
        )
    assert len(movies) == 1
    assert movies[0].normalized_number == "ABP-001"
    assert movies[0].raw_numbers == ["ABP-001", "abp_001"]
    assert [source.identification_status for source in sources] == [
        "identified",
        "identified",
        "pending",
    ]
    assert sources[0].movie_id == sources[1].movie_id == movies[0].id
    assert sources[2].movie_id is None and sources[2].normalized_number is None
    assert sources[0].magnet_ciphertext != b"urn:fixture-resource-1"
    assert (
        cipher.decrypt(
            sources[0].magnet_envelope,
            context=source_magnet_context("sehuatang", 1),
        ).decode("utf-8")
        == "urn:fixture-resource-1"
    )


def test_upsert_updates_present_sources_without_deleting_missing_history(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, _ = importer
    service.import_batch("old.zip", (avdb_row(10), avdb_row(11, number="SSIS-002")))

    stats = service.import_batch(
        "new.zip",
        (avdb_row(11, number="SSIS-002", title="Updated title"),),
    )

    assert stats == BatchStats(updated=1)
    with factory() as session:
        sources = list(
            session.scalars(
                select(ResourceSource).order_by(ResourceSource.external_post_id)
            )
        )
    assert [(source.external_post_id, source.title) for source in sources] == [
        (10, "Title 10"),
        (11, "Updated title"),
    ]


def test_accepts_all_six_target_sections(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, _ = importer
    sections = ["亚洲有码", "亚洲无码", "中文字幕", "4K原版", "素人有码", "FC2"]

    stats = service.import_batch(
        "all-sections.zip",
        tuple(
            avdb_row(
                100 + index,
                number=(f"ABC-{index + 10}" if section != "FC2" else "FC2-1234567"),
                section=section,
            )
            for index, section in enumerate(sections)
        ),
    )

    assert stats == BatchStats(inserted=6)
    with factory() as session:
        assert set(session.scalars(select(ResourceSource.section))) == set(sections)


def test_concurrent_imports_keep_one_movie_and_source_with_exact_stats(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, _ = importer
    barrier = Barrier(2)

    def import_one(raw_number: str) -> BatchStats:
        barrier.wait()
        return service.import_batch(
            "concurrent.zip",
            (avdb_row(200, number=raw_number),),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(import_one, ("ABP-001", "abp_001")))

    assert sum(item.inserted for item in results) == 1
    assert sum(item.updated for item in results) == 1
    with factory() as session:
        assert session.scalar(select(func.count(Movie.id))) == 1
        assert session.scalar(select(func.count(ResourceSource.id))) == 1
        movie = session.scalar(select(Movie))
    assert movie is not None
    assert movie.raw_numbers == ["ABP-001", "abp_001"]


def test_sync_preserves_a_manual_identification_link(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, _ = importer
    service.import_batch("before-manual.zip", (avdb_row(300),))
    with factory.begin() as session:
        source = session.scalar(select(ResourceSource))
        assert source is not None
        session.execute(
            update(ResourceSource)
            .where(ResourceSource.id == source.id)
            .values(identification_status="manual")
        )
        movie_id = source.movie_id

    stats = service.import_batch(
        "after-manual.zip",
        (avdb_row(300, number=None, title="Refreshed"),),
    )

    with factory() as session:
        source = session.scalar(select(ResourceSource))
    assert source is not None
    assert source.identification_status == "manual"
    assert source.movie_id == movie_id
    assert source.normalized_number == "ABP-001"
    assert source.title == "Refreshed"
    assert stats == BatchStats(updated=1)


def test_invalid_batch_does_not_leave_partial_source_rows(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, _ = importer
    invalid = avdb_row(401)
    invalid["magnet"] = None

    with pytest.raises(SourceImportError):
        service.import_batch(
            "invalid.zip",
            (avdb_row(400), invalid),
        )

    with factory() as session:
        assert session.scalar(select(func.count(ResourceSource.id))) == 0


def test_duplicate_source_in_one_batch_keeps_last_row_without_upsert_conflict(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, _ = importer

    stats = service.import_batch(
        "duplicates.zip",
        (
            avdb_row(450, title="Older duplicate"),
            avdb_row(450, title="Latest duplicate"),
        ),
    )

    assert stats == BatchStats(inserted=1, skipped=1)
    with factory() as session:
        sources = list(session.scalars(select(ResourceSource)))
    assert len(sources) == 1
    assert sources[0].title == "Latest duplicate"


def test_preview_urls_are_filtered_by_the_source_host_allowlist(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, _ = importer
    source_row = avdb_row(451)
    source_row["preview_images"] = (
        "https://evil.example/private.jpg,"
        "https://img.sehuatang.net/allowed.jpg,"
        "http://www.sehuatang.net/insecure.jpg"
    )

    service.import_batch("preview.zip", (source_row,))

    with factory() as session:
        source = session.scalar(select(ResourceSource))
    assert source is not None
    assert source.preview_urls == ["https://img.sehuatang.net/allowed.jpg"]


def test_initial_scope_uses_calendar_boundary_and_keeps_remaining_history(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, _ = importer
    as_of = date(2026, 7, 25)
    rows = (
        avdb_row(500, number="AAA-010", publish_date=as_of),
        avdb_row(501, number="AAA-010", publish_date=date(2026, 7, 1)),
        avdb_row(502, number="AAA-011", publish_date=date(2026, 4, 27)),
        avdb_row(503, number="AAA-012", publish_date=date(2026, 4, 26)),
        avdb_row(504, number="AAA-013", publish_date=date(2026, 7, 26)),
        avdb_row(505, number="AAA-014", publish_date=None),
        avdb_row(506, number=None, publish_date=as_of),
    )
    service.import_batch("scope.zip", rows)
    selector = InitialScopeSelector(factory)

    initial = selector.select_initial(as_of=as_of)
    history = selector.iter_history(as_of=as_of)

    actual_initial = [
        (item.normalized_number, item.publish_date, item.reason) for item in initial
    ]
    assert actual_initial == [
        ("AAA-010", as_of, "initial"),
        ("AAA-011", date(2026, 4, 27), "initial"),
    ]
    assert iter(history) is history
    assert [
        (item.normalized_number, item.publish_date, item.reason) for item in history
    ] == [
        ("AAA-013", date(2026, 7, 26), "history"),
        ("AAA-012", date(2026, 4, 26), "history"),
        ("AAA-014", None, "history"),
    ]


def test_initial_scope_truncates_unique_numbers_before_streaming_history(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
) -> None:
    service, factory, _ = importer
    as_of = date(2026, 7, 25)
    generated = (
        avdb_row(
            10_000 + index,
            number=f"AAA-{index:05d}",
            publish_date=as_of,
        )
        for index in range(5_001)
    )
    batch: list[dict[str, object]] = []
    for row in generated:
        batch.append(row)
        if len(batch) == 1_000:
            service.import_batch("capacity.zip", tuple(batch))
            batch = []
    if batch:
        service.import_batch("capacity.zip", tuple(batch))

    selector = InitialScopeSelector(factory)
    initial = selector.select_initial(as_of=as_of)
    history = selector.iter_history(as_of=as_of)

    assert len(initial) == 5_000
    assert initial[0].normalized_number == "AAA-00000"
    assert initial[-1].normalized_number == "AAA-04999"
    remaining = list(history)
    assert [(item.normalized_number, item.reason) for item in remaining] == [
        ("AAA-05000", "history")
    ]


def test_worker_consumer_completes_scheduled_request_with_real_importer(
    importer: tuple[SourceImporter, sessionmaker, SecretCipher],
    tmp_path: Path,
) -> None:
    service, factory, _ = importer
    queue = AvdbSyncQueue(factory, now=lambda: NOW)
    request = queue.enqueue("incremental_30d")
    consumer = AvdbWorkerConsumer(
        queue=queue,
        release_client=SuccessfulReleaseClient(),
        sync_service=AvdbSyncService(factory, now=lambda: NOW),
        asset_directory=tmp_path / "assets",
        plaintext_directory=tmp_path / "plaintext",
    )

    outcome = consumer.run_once(
        worker_id="task005-worker",
        importer=service.import_batch,
    )

    assert outcome == "completed"
    with factory() as session:
        saved = session.get(AvdbSyncRequest, request.request_id)
        source = session.scalar(
            select(ResourceSource).where(ResourceSource.external_post_id == 900)
        )
    assert saved is not None and saved.status == "completed"
    assert saved.sync_run_id is not None
    assert source is not None and source.normalized_number == "SSIS-900"
