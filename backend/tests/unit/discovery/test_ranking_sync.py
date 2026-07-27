import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.providers.javdb import MetadataProviderProblem
from sakuraplayer.discovery.models import (
    RankingEntry,
    RankingSnapshot,
    RankingSyncRequest,
)
from sakuraplayer.discovery.ranking_sync import (
    RankingSnapshotSynchronizer,
    RankingSyncQueue,
)
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 26, 7, 0, tzinfo=timezone.utc)


def _context():
    assert Movie.metadata is Base.metadata
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    current = [NOW]
    queue = RankingSyncQueue(factory, now=lambda: current[0])
    return engine, factory, queue, current


def test_request_queue_merges_same_slot_and_active_scope() -> None:
    engine, factory, queue, _ = _context()
    try:
        first = queue.enqueue("daily", year=None, scheduled_for=NOW)
        repeated = queue.enqueue("daily", year=None, scheduled_for=NOW)
        overlapping = queue.enqueue(
            "daily",
            year=None,
            scheduled_for=NOW + timedelta(days=1),
        )

        assert first.created is True
        assert repeated.created is False
        assert overlapping.created is False
        assert repeated.request_id == overlapping.request_id == first.request_id
        with factory() as session:
            assert len(list(session.scalars(select(RankingSyncRequest)))) == 1
    finally:
        engine.dispose()


def test_request_queue_reclaims_expired_claim_and_fences_old_owner() -> None:
    engine, _, queue, current = _context()
    try:
        queued = queue.enqueue("weekly", year=None, scheduled_for=NOW)
        old = queue.claim_next("worker-old", lease_duration=timedelta(minutes=5))
        assert old is not None
        current[0] += timedelta(minutes=6)
        recovered = queue.claim_next("worker-new", lease_duration=timedelta(minutes=5))

        assert recovered is not None
        assert recovered.request_id == queued.request_id == old.request_id
        assert recovered.claim_token != old.claim_token
        with pytest.raises(RuntimeError, match="claim was lost"):
            queue.fail(old, code="javdb_upstream_error")
        queue.fail(recovered, code="javdb_upstream_error")

        next_slot = queue.enqueue(
            "weekly",
            year=None,
            scheduled_for=NOW + timedelta(days=1),
        )
        assert next_slot.created is True
        assert next_slot.request_id != queued.request_id
    finally:
        engine.dispose()


def test_due_targets_skip_credentials_and_completed_history() -> None:
    engine, factory, queue, _ = _context()
    try:
        public = queue.enqueue_due_targets(
            scheduled_for=NOW,
            current_year=2010,
            credentials_configured=False,
        )
        assert {(item.board, item.year) for item in public} == {
            ("daily", None),
            ("weekly", None),
            ("monthly", None),
        }
        for item in public:
            claim = queue.claim_next(
                "public-worker", lease_duration=timedelta(minutes=5)
            )
            assert claim is not None
            queue.fail(claim, code="fixture_done")

        with factory.begin() as session:
            session.add(
                RankingSnapshot(
                    id=uuid.uuid4(),
                    board="top250",
                    year=2008,
                    status="current",
                    source_synced_at=NOW,
                    created_at=NOW,
                )
            )
        targets = queue.enqueue_due_targets(
            scheduled_for=NOW + timedelta(days=1),
            current_year=2010,
            credentials_configured=True,
        )

        assert {(item.board, item.year) for item in targets} == {
            ("daily", None),
            ("weekly", None),
            ("monthly", None),
            ("top250", None),
            ("top250", 2009),
            ("top250", 2010),
        }
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("board", "year"),
    [("daily", 2026), ("unknown", None), ("top250", 2007), ("top250", 2027)],
)
def test_request_queue_rejects_invalid_scope(board: str, year: int | None) -> None:
    engine, _, queue, _ = _context()
    try:
        with pytest.raises(ValueError, match="ranking scope"):
            queue.enqueue(
                board,
                year=year,
                scheduled_for=NOW,
                current_year=2026,
            )
    finally:
        engine.dispose()


def _movie(number: str) -> Movie:
    return Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )


class _Provider:
    def __init__(self, results) -> None:
        self.results = results
        self.calls = []

    def fetch_rankings(self, board, *, year, credentials):
        self.calls.append((board, year, credentials))
        if isinstance(self.results, Exception):
            raise self.results
        return tuple(self.results)


def test_snapshot_sync_atomically_switches_current_and_binds_existing_movie() -> None:
    engine, factory, queue, _ = _context()
    movie = _movie("ABP-300")
    provider = _Provider(
        [
            SimpleNamespace(rank=1, normalized_number="ABP-300"),
            SimpleNamespace(rank=3, normalized_number="IPX-999"),
        ]
    )
    sync = RankingSnapshotSynchronizer(queue, provider, credentials=lambda: None)
    try:
        with factory.begin() as session:
            session.add(movie)
        queue.enqueue("daily", year=None, scheduled_for=NOW)
        first_claim = queue.claim_next(
            "ranking-worker", lease_duration=timedelta(minutes=5)
        )
        assert first_claim is not None
        first_id = sync.synchronize(first_claim)

        provider.results = [SimpleNamespace(rank=2, normalized_number="ABP-300")]
        queue.enqueue(
            "daily",
            year=None,
            scheduled_for=NOW + timedelta(days=1),
        )
        second_claim = queue.claim_next(
            "ranking-worker",
            lease_duration=timedelta(minutes=5),
        )
        assert second_claim is not None
        second_id = sync.synchronize(second_claim)

        with factory() as session:
            first = session.get(RankingSnapshot, first_id)
            second = session.get(RankingSnapshot, second_id)
            first_entries = list(
                session.scalars(
                    select(RankingEntry)
                    .where(RankingEntry.snapshot_id == first_id)
                    .order_by(RankingEntry.rank)
                )
            )
            request = session.get(RankingSyncRequest, second_claim.request_id)
            assert first is not None and first.status == "superseded"
            assert second is not None and second.status == "current"
            assert [(item.rank, item.movie_id) for item in first_entries] == [
                (1, movie.id),
                (3, None),
            ]
            assert request is not None
            assert (request.status, request.snapshot_id) == ("completed", second_id)
    finally:
        engine.dispose()


def test_snapshot_sync_failure_and_empty_candidate_preserve_current() -> None:
    engine, factory, queue, _ = _context()
    provider = _Provider([SimpleNamespace(rank=1, normalized_number="ABP-301")])
    sync = RankingSnapshotSynchronizer(queue, provider, credentials=lambda: None)
    try:
        queue.enqueue("weekly", year=None, scheduled_for=NOW)
        first_claim = queue.claim_next(
            "ranking-worker", lease_duration=timedelta(minutes=5)
        )
        assert first_claim is not None
        current_id = sync.synchronize(first_claim)

        queue.enqueue(
            "weekly",
            year=None,
            scheduled_for=NOW + timedelta(days=1),
        )
        failed_claim = queue.claim_next(
            "ranking-worker",
            lease_duration=timedelta(minutes=5),
        )
        assert failed_claim is not None
        provider.results = MetadataProviderProblem("javdb_upstream_error")
        with pytest.raises(MetadataProviderProblem, match="javdb_upstream_error"):
            sync.synchronize(failed_claim)
        queue.fail(failed_claim, code="javdb_upstream_error")

        queue.enqueue(
            "weekly",
            year=None,
            scheduled_for=NOW + timedelta(days=2),
        )
        empty_claim = queue.claim_next(
            "ranking-worker",
            lease_duration=timedelta(minutes=5),
        )
        assert empty_claim is not None
        provider.results = []
        with pytest.raises(ValueError, match="ranking snapshot candidates"):
            sync.synchronize(empty_claim)

        with factory() as session:
            currents = list(
                session.scalars(
                    select(RankingSnapshot).where(RankingSnapshot.status == "current")
                )
            )
            assert [item.id for item in currents] == [current_id]
    finally:
        engine.dispose()


def test_snapshot_activation_fences_expired_claim() -> None:
    engine, factory, queue, current = _context()
    provider = _Provider([SimpleNamespace(rank=1, normalized_number="ABP-302")])
    sync = RankingSnapshotSynchronizer(queue, provider, credentials=lambda: None)
    try:
        queue.enqueue("monthly", year=None, scheduled_for=NOW)
        claim = queue.claim_next("ranking-worker", lease_duration=timedelta(minutes=5))
        assert claim is not None
        current[0] += timedelta(minutes=6)

        with pytest.raises(RuntimeError, match="claim was lost"):
            sync.synchronize(claim)

        with factory() as session:
            assert list(session.scalars(select(RankingSnapshot))) == []
    finally:
        engine.dispose()
