from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from sakuraplayer.resources.avdb_release import FetchedAsset, FetchedRelease
from sakuraplayer.resources.models import AvdbAsset, AvdbSyncRequest, AvdbSyncRun
from sakuraplayer.resources.sync_service import (
    AvdbSyncQueue,
    AvdbSyncService,
    BatchStats,
    RunClaimLost,
)
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


@dataclass(frozen=True)
class Rows:
    manifest_summary = {
        "algorithm": "AES-256-GCM",
        "iterations": 200_000,
        "kdf": "PBKDF2-HMAC-SHA256",
        "key_length": 32,
    }

    def iter_rows(self):
        yield {"tid": "1", "title": "safe"}


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task004_{uuid.uuid4().hex}"
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


@pytest.fixture
def store(database_url: str):
    upgrade_database(database_url, ALEMBIC_INI)
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def release(release_id: str = "42") -> FetchedRelease:
    return FetchedRelease(
        repository="li-peifeng/AVdb-Only",
        release_id=release_id,
        tag="2026.07.25",
        mode="incremental_30d",
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


def test_postgres_persists_one_idempotent_release_and_asset(store) -> None:
    imported = 0

    def importer(asset_name, rows):
        nonlocal imported
        assert asset_name == "30D_202607250300.zip"
        imported += len(rows)
        return BatchStats(inserted=len(rows))

    service = AvdbSyncService(store)
    first = service.sync(release(), importer=importer)
    second = service.sync(release(), importer=importer)

    assert first.idempotent is False
    assert second.idempotent is True
    assert imported == 1
    with store() as session:
        runs = session.scalars(select(AvdbSyncRun)).all()
        assets = session.scalars(select(AvdbAsset)).all()
        assert len(runs) == 1 and runs[0].status == "completed"
        assert runs[0].completed_at is not None
        assert len(assets) == 1 and assets[0].status == "imported"
        assert set(assets[0].manifest) == {
            "algorithm",
            "iterations",
            "kdf",
            "key_length",
        }


def test_new_release_keeps_prior_successful_cursor_and_history(store) -> None:
    service = AvdbSyncService(store)
    importer = lambda asset_name, rows: BatchStats(skipped=len(rows))

    service.sync(release("old"), importer=importer)
    service.sync(release("new"), importer=importer)

    with store() as session:
        runs = session.scalars(
            select(AvdbSyncRun).order_by(AvdbSyncRun.started_at, AvdbSyncRun.release_id)
        ).all()
        assert {run.release_id for run in runs} == {"old", "new"}
        assert all(run.cursor["row_offset"] == 1 for run in runs)
        assert all(run.status == "completed" for run in runs)


def test_postgres_concurrent_scheduler_enqueue_creates_one_slot(store) -> None:
    fixed = datetime(2026, 7, 25, 19, 0, 30, tzinfo=timezone.utc)

    def enqueue(_):
        return AvdbSyncQueue(store, now=lambda: fixed).enqueue("incremental_30d")

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(enqueue, range(2)))

    assert sorted(outcome.created for outcome in outcomes) == [False, True]
    assert outcomes[0].request_id == outcomes[1].request_id
    with store() as session:
        requests = session.scalars(select(AvdbSyncRequest)).all()
        assert len(requests) == 1


def test_postgres_concurrent_workers_claim_one_request_once(store) -> None:
    queue = AvdbSyncQueue(store)
    enqueued = queue.enqueue("incremental_30d")

    def claim(worker_id):
        return AvdbSyncQueue(store).claim_next(
            worker_id,
            lease_duration=timedelta(minutes=5),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("worker-1", "worker-2")))

    claimed = [claim for claim in claims if claim is not None]
    assert len(claimed) == 1
    assert claimed[0].request_id == enqueued.request_id


def test_postgres_expired_request_rejects_old_same_worker_claim(store) -> None:
    current = [datetime(2026, 7, 25, 19, 0, tzinfo=timezone.utc)]
    queue = AvdbSyncQueue(store, now=lambda: current[0])
    queue.enqueue("incremental_30d")
    old_claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))
    current[0] += timedelta(minutes=6)

    assert old_claim is not None
    with pytest.raises(RuntimeError):
        queue.renew(old_claim, lease_duration=timedelta(minutes=5))
    with pytest.raises(RuntimeError):
        queue.fail(old_claim, code="internal_error", detail="internal_error")

    new_claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))
    assert new_claim is not None
    assert old_claim.claim_token != new_claim.claim_token
    queue.fail(new_claim, code="internal_error", detail="internal_error")


def test_postgres_run_fence_blocks_takeover_until_asset_transaction_commits(
    store,
) -> None:
    current = [datetime(2026, 7, 25, 19, 0, tzinfo=timezone.utc)]
    old_service = AvdbSyncService(store, now=lambda: current[0])
    new_service = AvdbSyncService(store, now=lambda: current[0])
    fetched = release()
    old_claim = old_service._start_run(fetched)
    asset = fetched.assets[0]
    asset_id, _ = old_service._record_or_resume_asset(
        old_claim.run_id,
        asset,
        asset.validation,
        old_claim.claim_token,
    )
    old_locked = Event()
    allow_old_commit = Event()
    successor_started = Event()

    def finish_asset_transaction():
        with store.begin() as session:
            old_service._assert_run_claim(
                session,
                old_claim.run_id,
                old_claim.claim_token,
            )
            old_locked.set()
            assert allow_old_commit.wait(5)
            session.execute(
                update(AvdbAsset)
                .where(AvdbAsset.id == asset_id)
                .values(status="imported")
            )

    def take_over_expired_run():
        successor_started.set()
        return new_service._start_run(fetched)

    with ThreadPoolExecutor(max_workers=2) as pool:
        old_future = pool.submit(finish_asset_transaction)
        assert old_locked.wait(5)
        current[0] += timedelta(minutes=11)
        successor_future = pool.submit(take_over_expired_run)
        assert successor_started.wait(5)
        time.sleep(0.1)
        assert not successor_future.done()
        allow_old_commit.set()
        old_future.result(timeout=5)
        successor = successor_future.result(timeout=5)

    assert successor.should_process is True
    assert successor.claim_token != old_claim.claim_token
    with pytest.raises(RunClaimLost):
        old_service._set_asset_status(
            asset_id,
            "failed",
            run_id=old_claim.run_id,
            claim_token=old_claim.claim_token,
        )
    with store() as session:
        saved = session.get(AvdbAsset, asset_id)
        assert saved is not None and saved.status == "imported"


def test_postgres_rejects_non_hexadecimal_asset_digest(store) -> None:
    service = AvdbSyncService(store)
    service.sync(
        release(),
        importer=lambda asset_name, rows: BatchStats(inserted=len(rows)),
    )

    with pytest.raises(IntegrityError):
        with store.begin() as session:
            session.execute(update(AvdbAsset).values(sha256="z" * 64))
