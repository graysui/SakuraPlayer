from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.resources.avdb_crypto import AvdbAssetError
from sakuraplayer.resources.avdb_release import FetchedAsset, FetchedRelease
from sakuraplayer.resources.avdb_worker import AvdbWorkerConsumer
from sakuraplayer.resources.models import AvdbSyncRequest, Base
from sakuraplayer.resources.sync_service import (
    AvdbSyncQueue,
    AvdbSyncService,
    BatchStats,
)


@dataclass(frozen=True)
class Rows:
    manifest_summary = {
        "algorithm": "AES-256-GCM",
        "iterations": 200_000,
        "kdf": "PBKDF2-HMAC-SHA256",
        "key_length": 32,
    }

    def iter_rows(self):
        yield {"tid": 1, "title": "row"}


class SuccessfulReleaseClient:
    def __init__(self, validation=None) -> None:
        self.validation = validation or Rows()

    def fetch_release(self, *, mode, destination, validator):
        del destination, validator
        return FetchedRelease(
            repository="li-peifeng/AVdb-Only",
            release_id="42",
            tag="2026.07.25",
            mode=mode,
            assets=(
                FetchedAsset(
                    name="30D_202607250300.zip",
                    path=Path("fixture.zip"),
                    sha256="a" * 64,
                    byte_size=100,
                    validation=self.validation,
                ),
            ),
        )


class FailingReleaseClient:
    def fetch_release(self, *, mode, destination, validator):
        del mode, destination, validator
        raise AvdbAssetError("avdb_decryption_failed")


class FailingCloseRows(Rows):
    def close(self) -> None:
        raise OSError("sensitive temporary path")


class FailingCleanupReleaseClient(SuccessfulReleaseClient):
    def __init__(self) -> None:
        super().__init__(FailingCloseRows())
        self.plaintext_path: Path | None = None

    def fetch_release(self, *, mode, destination, validator):
        del validator
        directories = list(Path(destination).glob(".avdb-plaintext-*"))
        assert len(directories) == 1
        self.plaintext_path = directories[0] / "fixture.inner.zip"
        self.plaintext_path.write_bytes(b"temporary fixture")
        return super().fetch_release(
            mode=mode,
            destination=destination,
            validator=lambda path: path,
        )


def store():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def test_consumer_completes_claim_and_links_sync_run(tmp_path) -> None:
    engine, factory = store()
    queue = AvdbSyncQueue(factory)
    request = queue.enqueue("incremental_30d")
    consumer = AvdbWorkerConsumer(
        queue=queue,
        release_client=SuccessfulReleaseClient(),
        sync_service=AvdbSyncService(factory),
        asset_directory=tmp_path,
        plaintext_directory=tmp_path,
    )

    outcome = consumer.run_once(
        worker_id="worker-1",
        importer=lambda asset_name, rows: BatchStats(inserted=len(rows)),
    )

    assert outcome == "completed"
    with factory() as session:
        saved = session.get(AvdbSyncRequest, request.request_id)
        assert saved is not None and saved.status == "completed"
        assert saved.sync_run_id is not None
        assert saved.failure_code is None
    engine.dispose()


def test_consumer_persists_discovery_or_decryption_failure(tmp_path) -> None:
    engine, factory = store()
    queue = AvdbSyncQueue(factory)
    request = queue.enqueue("incremental_30d")
    consumer = AvdbWorkerConsumer(
        queue=queue,
        release_client=FailingReleaseClient(),
        sync_service=AvdbSyncService(factory),
        asset_directory=tmp_path,
        plaintext_directory=tmp_path,
    )

    outcome = consumer.run_once(
        worker_id="worker-1",
        importer=lambda asset_name, rows: BatchStats(),
    )

    assert outcome == "failed"
    with factory() as session:
        saved = session.scalar(
            select(AvdbSyncRequest).where(AvdbSyncRequest.id == request.request_id)
        )
        assert saved is not None and saved.status == "failed"
        assert saved.failure_code == "avdb_decryption_failed"
        assert saved.failure_detail == "avdb_decryption_failed"
        assert saved.sync_run_id is None
    engine.dispose()


def test_cleanup_failure_does_not_override_persisted_success(tmp_path, caplog) -> None:
    engine, factory = store()
    queue = AvdbSyncQueue(factory)
    request = queue.enqueue("incremental_30d")
    release_client = FailingCleanupReleaseClient()
    consumer = AvdbWorkerConsumer(
        queue=queue,
        release_client=release_client,
        sync_service=AvdbSyncService(factory),
        asset_directory=tmp_path,
        plaintext_directory=tmp_path,
    )

    with caplog.at_level(logging.ERROR):
        outcome = consumer.run_once(
            worker_id="worker-1",
            importer=lambda asset_name, rows: BatchStats(inserted=len(rows)),
        )

    assert outcome == "completed"
    assert "avdb_plaintext_cleanup_failed" in caplog.messages
    assert all("sensitive temporary path" not in message for message in caplog.messages)
    assert release_client.plaintext_path is not None
    assert not release_client.plaintext_path.exists()
    assert not list(tmp_path.glob(".avdb-plaintext-*"))
    with factory() as session:
        saved = session.get(AvdbSyncRequest, request.request_id)
        assert saved is not None and saved.status == "completed"
    engine.dispose()


def test_consumer_heartbeats_request_during_slow_release_fetch(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'queue.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    queue = AvdbSyncQueue(factory)
    queue.enqueue("incremental_30d")
    stolen = []

    class SlowReleaseClient(SuccessfulReleaseClient):
        def fetch_release(self, *, mode, destination, validator):
            time.sleep(0.3)
            stolen.append(
                queue.claim_next(
                    "worker-2",
                    lease_duration=timedelta(milliseconds=200),
                )
            )
            return super().fetch_release(
                mode=mode,
                destination=destination,
                validator=validator,
            )

    consumer = AvdbWorkerConsumer(
        queue=queue,
        release_client=SlowReleaseClient(),
        sync_service=AvdbSyncService(factory),
        asset_directory=tmp_path,
        plaintext_directory=tmp_path,
        request_lease_duration=timedelta(milliseconds=200),
        heartbeat_interval=timedelta(milliseconds=20),
    )

    assert (
        consumer.run_once(
            worker_id="worker-1",
            importer=lambda asset_name, rows: BatchStats(inserted=len(rows)),
        )
        == "completed"
    )
    assert stolen == [None]
    engine.dispose()


def test_consumer_sweeps_only_owned_stale_plaintext_directories(tmp_path) -> None:
    engine, factory = store()
    stale = tmp_path / f".avdb-plaintext-{uuid.uuid4()}-{uuid.uuid4().hex}"
    stale.mkdir()
    (stale / "fixture.inner.zip").write_bytes(b"stale plaintext")
    unrelated = tmp_path / ".avdb-plaintext-user-data"
    unrelated.mkdir()
    consumer = AvdbWorkerConsumer(
        queue=AvdbSyncQueue(factory),
        release_client=SuccessfulReleaseClient(),
        sync_service=AvdbSyncService(factory),
        asset_directory=tmp_path,
        plaintext_directory=tmp_path,
    )

    assert (
        consumer.run_once(
            worker_id="worker-1",
            importer=lambda asset_name, rows: BatchStats(),
        )
        == "idle"
    )
    assert not stale.exists()
    assert unrelated.exists()
    engine.dispose()


def test_consumer_does_not_sweep_another_active_claim_directory(tmp_path) -> None:
    engine, factory = store()
    queue = AvdbSyncQueue(factory)
    queue.enqueue("incremental_30d")
    claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))
    assert claim is not None
    active = tmp_path / (f".avdb-plaintext-{claim.request_id}-{claim.claim_token.hex}")
    active.mkdir()
    (active / "fixture.inner.zip").write_bytes(b"active plaintext")
    consumer = AvdbWorkerConsumer(
        queue=queue,
        release_client=SuccessfulReleaseClient(),
        sync_service=AvdbSyncService(factory),
        asset_directory=tmp_path,
        plaintext_directory=tmp_path,
    )

    assert (
        consumer.run_once(
            worker_id="worker-2",
            importer=lambda asset_name, rows: BatchStats(inserted=len(rows)),
        )
        == "idle"
    )
    assert active.exists()
    engine.dispose()


def test_consumer_rejects_symlink_plaintext_root_before_release_fetch(tmp_path) -> None:
    engine, factory = store()
    queue = AvdbSyncQueue(factory)
    request = queue.enqueue("incremental_30d")
    outside = tmp_path / "outside"
    outside.mkdir()
    plaintext_root = tmp_path / "plaintext"
    plaintext_root.symlink_to(outside, target_is_directory=True)

    class UnexpectedReleaseClient(SuccessfulReleaseClient):
        def fetch_release(self, *, mode, destination, validator):
            raise AssertionError("release fetch must not run for an unsafe root")

    consumer = AvdbWorkerConsumer(
        queue=queue,
        release_client=UnexpectedReleaseClient(),
        sync_service=AvdbSyncService(factory),
        asset_directory=tmp_path,
        plaintext_directory=plaintext_root,
    )

    assert (
        consumer.run_once(
            worker_id="worker-1",
            importer=lambda asset_name, rows: BatchStats(),
        )
        == "failed"
    )
    assert list(outside.iterdir()) == []
    with factory() as session:
        saved = session.get(AvdbSyncRequest, request.request_id)
        assert saved is not None and saved.status == "failed"
        assert saved.failure_code == "avdb_asset_invalid"
    engine.dispose()
