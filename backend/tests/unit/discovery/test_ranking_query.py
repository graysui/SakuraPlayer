import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.metadata_queue import MetadataQueue
from sakuraplayer.catalog.models import MetadataJob
from sakuraplayer.catalog.query_service import CatalogQueryService
from sakuraplayer.discovery.models import RankingEntry, RankingSnapshot
from sakuraplayer.discovery.ranking_query import (
    RankingQueryProblem,
    RankingQueryService,
)
from sakuraplayer.discovery.ranking_sync import RankingSyncQueue
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie, ResourceSource

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


def _movie(number: str, *, state: str) -> Movie:
    return Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        title_original=f"Movie {number}",
        catalog_state=state,
        created_at=NOW,
        updated_at=NOW,
    )


def _source(movie: Movie, tid: int) -> ResourceSource:
    return ResourceSource(
        id=uuid.uuid4(),
        website="sehuatang",
        external_post_id=tid,
        movie_id=movie.id,
        raw_number=movie.normalized_number,
        normalized_number=movie.normalized_number,
        title=f"Source {tid}",
        publish_date=date(2026, 7, min(tid, 28)),
        section="亚洲有码",
        category=None,
        resource_size_mb=1000,
        detail_url="https://www.sehuatang.net/fixture",
        preview_urls=[],
        identification_status="identified",
        imported_at=NOW,
    )


def _context(*, credential_status: str = "configured"):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    metadata = MetadataQueue(factory, now=lambda: NOW)
    service = RankingQueryService(
        factory,
        catalog=CatalogQueryService(factory),
        completion=metadata,
        credential_status=lambda: credential_status,
        current_year=lambda: 2026,
    )
    return engine, factory, metadata, service


def test_query_filters_entries_promotes_raw_and_keeps_cursor_snapshot() -> None:
    engine, factory, _, service = _context()
    snapshot_id = uuid.uuid4()
    first = _movie("ABP-401", state="core_ready")
    raw = _movie("ABP-402", state="raw_only")
    no_source = _movie("ABP-403", state="core_ready")
    late = _movie("ABP-404", state="core_ready")
    last = _movie("ABP-405", state="core_ready")
    try:
        with factory.begin() as session:
            session.add_all(
                [
                    first,
                    raw,
                    no_source,
                    late,
                    last,
                    _source(first, 1),
                    _source(raw, 2),
                    _source(late, 4),
                    _source(last, 5),
                    RankingSnapshot(
                        id=snapshot_id,
                        board="daily",
                        year=None,
                        status="current",
                        source_synced_at=NOW,
                        created_at=NOW,
                    ),
                ]
            )
            session.add_all(
                [
                    RankingEntry(
                        snapshot_id=snapshot_id,
                        rank=1,
                        normalized_number=first.normalized_number,
                        movie_id=first.id,
                    ),
                    RankingEntry(
                        snapshot_id=snapshot_id,
                        rank=2,
                        normalized_number=raw.normalized_number,
                        movie_id=raw.id,
                    ),
                    RankingEntry(
                        snapshot_id=snapshot_id,
                        rank=3,
                        normalized_number=no_source.normalized_number,
                        movie_id=no_source.id,
                    ),
                    RankingEntry(
                        snapshot_id=snapshot_id,
                        rank=4,
                        normalized_number="ABP-404",
                        movie_id=None,
                    ),
                    RankingEntry(
                        snapshot_id=snapshot_id,
                        rank=5,
                        normalized_number=last.normalized_number,
                        movie_id=last.id,
                    ),
                ]
            )

        first_page = service.get_ranking(
            board="daily",
            year=None,
            cursor=None,
            limit=1,
        )
        assert [(item.rank, item.movie.id) for item in first_page.items] == [
            (1, first.id)
        ]
        assert first_page.next_cursor is not None
        with pytest.raises(RankingQueryProblem, match="validation_failed"):
            service.get_ranking(
                board="weekly",
                year=None,
                cursor=first_page.next_cursor,
                limit=1,
            )
        with factory() as session:
            promoted = session.scalar(
                select(MetadataJob).where(
                    MetadataJob.normalized_number == raw.normalized_number
                )
            )
            assert promoted is not None
            assert (promoted.priority, promoted.reason) == (20, "ranking")

        with factory.begin() as session:
            old = session.get(RankingSnapshot, snapshot_id, with_for_update=True)
            assert old is not None
            old.status = "superseded"
            session.add(
                RankingSnapshot(
                    id=uuid.uuid4(),
                    board="daily",
                    year=None,
                    status="current",
                    source_synced_at=NOW + timedelta(days=1),
                    created_at=NOW + timedelta(days=1),
                )
            )

        second_page = service.get_ranking(
            board="daily",
            year=None,
            cursor=first_page.next_cursor,
            limit=1,
        )

        assert [(item.rank, item.movie.id) for item in second_page.items] == [
            (4, late.id)
        ]
        assert second_page.synced_at == NOW
        assert second_page.next_cursor is not None
        third_page = service.get_ranking(
            board="daily",
            year=None,
            cursor=second_page.next_cursor,
            limit=1,
        )
        assert [(item.rank, item.movie.id) for item in third_page.items] == [
            (5, last.id)
        ]
        assert third_page.next_cursor is None
    finally:
        engine.dispose()


def test_query_returns_all_supported_top250_years_descending() -> None:
    engine, factory, _, service = _context()
    try:
        with factory.begin() as session:
            session.add_all(
                [
                    RankingSnapshot(
                        id=uuid.uuid4(),
                        board="top250",
                        year=None,
                        status="current",
                        source_synced_at=NOW,
                        created_at=NOW,
                    ),
                ]
            )

        page = service.get_ranking(
            board="top250",
            year=None,
            cursor=None,
            limit=24,
        )

        assert page.available_years == list(range(2026, 2007, -1))
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("board", "year"),
    [("daily", 2026), ("top250", 2027), ("unknown", None)],
)
def test_query_rejects_invalid_board_year_scope(board: str, year: int | None) -> None:
    engine, _, _, service = _context()
    try:
        with pytest.raises(RankingQueryProblem) as raised:
            service.get_ranking(
                board=board,
                year=year,
                cursor=None,
                limit=24,
            )
        assert raised.value.status_code == 422
        assert raised.value.code == "validation_failed"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("board", "credential_status", "failed_code", "reason"),
    [
        ("top250", "not_configured", None, "credentials_not_configured"),
        ("top250", "invalid", None, "credentials_invalid"),
        ("daily", "configured", None, "never_synced"),
        ("weekly", "configured", "javdb_upstream_error", "sync_failed"),
    ],
)
def test_query_reports_stable_unavailable_reason(
    board: str,
    credential_status: str,
    failed_code: str | None,
    reason: str,
) -> None:
    engine, factory, _, service = _context(credential_status=credential_status)
    try:
        if failed_code is not None:
            queue = RankingSyncQueue(factory, now=lambda: NOW)
            queue.enqueue(board, year=None, scheduled_for=NOW)
            claim = queue.claim_next(
                "ranking-worker",
                lease_duration=timedelta(minutes=5),
            )
            assert claim is not None
            queue.fail(claim, code=failed_code)

        with pytest.raises(RankingQueryProblem) as raised:
            service.get_ranking(
                board=board,
                year=None,
                cursor=None,
                limit=24,
            )

        assert raised.value.status_code == 503
        assert raised.value.code == "ranking_snapshot_unavailable"
        assert raised.value.details["reason"] == reason
        if failed_code is not None:
            assert raised.value.details["last_error_code"] == failed_code
    finally:
        engine.dispose()
