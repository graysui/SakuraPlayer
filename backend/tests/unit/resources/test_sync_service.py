from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.resources.avdb_release import FetchedAsset, FetchedRelease
from sakuraplayer.resources.models import AvdbAsset, AvdbSyncRun, Base
from sakuraplayer.resources.sync_service import (
    AvdbSyncFailed,
    AvdbSyncService,
    BatchStats,
)


@dataclass(frozen=True)
class Rows:
    values: tuple[dict[str, str], ...]
    manifest_summary = {
        "algorithm": "AES-256-GCM",
        "iterations": 200_000,
        "kdf": "PBKDF2-HMAC-SHA256",
        "key_length": 32,
    }

    def iter_rows(self):
        yield from self.values


@pytest.fixture
def store():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def fetched_release(*, release_id: str = "42", asset_count: int = 1):
    assets = tuple(
        FetchedAsset(
            name=(
                "30D_202607250300.zip"
                if asset_count == 1
                else f"All_{'sehuatang' if index == 0 else 'X1080X'}_1_202607250400.zip"
            ),
            path=Path(f"asset-{index}.zip"),
            sha256=str(index + 1) * 64,
            byte_size=100 + index,
            validation=Rows(({"tid": str(index + 1), "title": "row"},)),
        )
        for index in range(asset_count)
    )
    return FetchedRelease(
        repository="li-peifeng/AVdb-Only",
        release_id=release_id,
        tag="2026.07.25",
        mode="incremental_30d" if asset_count == 1 else "full_reconcile",
        assets=assets,
    )


def test_persists_cursor_asset_digest_stats_and_idempotent_completion(store) -> None:
    imported: list[tuple[str, tuple[dict[str, str], ...]]] = []

    def importer(asset_name, rows):
        imported.append((asset_name, rows))
        return BatchStats(inserted=len(rows))

    service = AvdbSyncService(store, batch_size=100)
    first = service.sync(fetched_release(), importer=importer)
    repeated = service.sync(fetched_release(), importer=importer)

    assert first.status == "completed"
    assert repeated.status == "completed"
    assert repeated.idempotent is True
    assert len(imported) == 1
    with store() as session:
        run = session.scalar(select(AvdbSyncRun))
        asset = session.scalar(select(AvdbAsset))
        assert run is not None and run.status == "completed"
        assert run.cursor == {
            "asset_index": 1,
            "asset_name": "30D_202607250300.zip",
            "row_offset": 1,
        }
        assert run.stats == {
            "inserted": 1,
            "pending": 0,
            "skipped": 0,
            "updated": 0,
        }
        assert asset is not None and asset.status == "imported"
        assert asset.sha256 == "1" * 64
        assert "salt" not in asset.manifest


def test_failed_later_batch_keeps_prior_asset_and_redacts_failure(store) -> None:
    calls: list[str] = []

    def importer(asset_name, rows):
        del rows
        calls.append(asset_name)
        if len(calls) == 2:
            raise RuntimeError("sensitive fixture payload")
        return BatchStats(updated=1)

    service = AvdbSyncService(store, batch_size=1)
    with pytest.raises(AvdbSyncFailed) as error:
        service.sync(fetched_release(asset_count=2), importer=importer)

    assert error.value.code == "internal_error"
    with store() as session:
        run = session.scalar(select(AvdbSyncRun))
        assets = session.scalars(select(AvdbAsset).order_by(AvdbAsset.asset_name)).all()
        assert run is not None and run.status == "failed"
        assert run.failure_code == "internal_error"
        assert "private" not in (run.failure_detail or "")
        assert sorted(asset.status for asset in assets) == ["failed", "imported"]
        assert run.cursor["row_offset"] == 1

    resumed_calls: list[str] = []

    def resumed_importer(asset_name, rows):
        resumed_calls.append(asset_name)
        return BatchStats(inserted=len(rows))

    resumed = service.sync(
        fetched_release(asset_count=2),
        importer=resumed_importer,
    )

    assert resumed.status == "completed"
    assert resumed.idempotent is False
    assert resumed_calls == ["All_X1080X_1_202607250400.zip"]


def test_new_full_release_preserves_completed_sync_history(store) -> None:
    service = AvdbSyncService(store)
    source_keys = {"legacy-missing-from-full"}

    def importer(asset_name, rows):
        del asset_name
        source_keys.update(str(row["tid"]) for row in rows)
        return BatchStats(skipped=len(rows))

    service.sync(fetched_release(release_id="first", asset_count=2), importer=importer)
    service.sync(fetched_release(release_id="second", asset_count=2), importer=importer)

    latest = service.latest_successful("full_reconcile")

    with store() as session:
        runs = session.scalars(
            select(AvdbSyncRun).order_by(AvdbSyncRun.release_id)
        ).all()
        assert [run.release_id for run in runs] == ["first", "second"]
        assert all(run.status == "completed" for run in runs)
    assert "legacy-missing-from-full" in source_keys
    assert latest is not None and latest.release_id == "second"
    assert latest.cursor["row_offset"] == 1


def test_old_run_claim_cannot_mark_successor_asset_failed(store) -> None:
    current = [datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)]
    old_service = AvdbSyncService(store, now=lambda: current[0])
    new_service = AvdbSyncService(store, now=lambda: current[0])
    release = fetched_release()

    def old_importer(asset_name, rows):
        del asset_name
        current[0] += timedelta(minutes=11)
        successor = new_service.sync(
            release,
            importer=lambda name, batch: BatchStats(inserted=len(batch)),
        )
        assert successor.status == "completed"
        return BatchStats(inserted=len(rows))

    with pytest.raises(AvdbSyncFailed) as error:
        old_service.sync(release, importer=old_importer)

    assert error.value.code == "state_conflict"
    with store() as session:
        run = session.scalar(select(AvdbSyncRun))
        asset = session.scalar(select(AvdbAsset))
        assert run is not None and run.status == "completed"
        assert asset is not None and asset.status == "imported"


def test_expired_run_cannot_renew_itself_after_slow_importer(store) -> None:
    current = [datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)]
    service = AvdbSyncService(store, now=lambda: current[0])

    def slow_importer(asset_name, rows):
        del asset_name
        current[0] += timedelta(minutes=11)
        return BatchStats(inserted=len(rows))

    with pytest.raises(AvdbSyncFailed) as error:
        service.sync(fetched_release(), importer=slow_importer)

    assert error.value.code == "state_conflict"
