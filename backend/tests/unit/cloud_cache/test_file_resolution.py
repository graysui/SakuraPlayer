from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.cache_availability import CacheSourceAvailabilityPort
from sakuraplayer.cloud_cache.media_selection_api import (
    MediaSelectionProblem,
    MediaSelectionService,
)
from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    RemoteMedia,
    RemoteSubtitle,
)
from sakuraplayer.cloud_cache.ports.cloud115 import (
    DirectoryBreadcrumb,
    DirectoryInfo,
    RemoteFile,
)
from sakuraplayer.cloud_cache.worker.claim import CacheJobClaimQueue
from sakuraplayer.cloud_cache.worker.resolution import (
    CacheMediaResolver,
    CacheWorkerPipeline,
)
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import Movie, ResourceSource
from tests.fakes.cloud115 import FakeCloud115

NOW = datetime(2026, 7, 27, 18, 0, tzinfo=timezone.utc)


@pytest.fixture
def context(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'media.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    movie_id = uuid.uuid4()
    source_id = uuid.uuid4()
    job_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(
            Movie(
                id=movie_id,
                normalized_number="IPX-001",
                raw_numbers=["IPX-001"],
                catalog_state="core_ready",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            ResourceSource(
                id=source_id,
                website="sehuatang",
                external_post_id=1,
                movie_id=movie_id,
                raw_number="IPX-001",
                normalized_number="IPX-001",
                title="fixture",
                publish_date=date(2026, 7, 27),
                section="亚洲有码",
                resource_size_mb=2048,
                preview_urls=[],
                identification_status="identified",
                imported_at=NOW,
            )
        )
        session.add(
            CacheJob(
                id=job_id,
                movie_id=movie_id,
                source_id=source_id,
                binding_id=uuid.uuid4(),
                status="resolving",
                capacity_class="running",
                account_key="account-fixture",
                cache_root_cid="root",
                task_dir_cid="task",
                task_dir_name="cache-fixture",
                remote_percent=100,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    try:
        yield factory, job_id
    finally:
        engine.dispose()


def test_resolver_auto_selects_decisive_media_and_persists_subtitle(context) -> None:
    factory, job_id = context
    fake = FakeCloud115(
        directory_infos=[_directory(), _directory()],
        file_batches=[
            (
                _file("main", "IPX-001.mkv", 2_000_000_000, parent="task"),
                _file("bonus", "bonus.mkv", 1_000_000_000, parent="task"),
                _file("sub", "IPX-001.srt", 1000, parent="task"),
            )
        ],
    )

    assert _resolver(factory, fake).run_once(worker_id="resolver-a") == "worked"

    with factory() as session:
        job = session.get(CacheJob, job_id)
        selected = list(
            session.scalars(
                select(RemoteMedia)
                .join(
                    CacheJobMediaSelection,
                    CacheJobMediaSelection.media_id == RemoteMedia.id,
                )
                .order_by(CacheJobMediaSelection.sequence_no)
            )
        )
        assert job is not None and job.status == "ready"
        assert [item.file_id for item in selected] == ["main"]
        assert session.scalar(select(func.count(RemoteSubtitle.id))) == 1
        assert job.claim_owner is None
        source_id = job.source_id
    availability = CacheSourceAvailabilityPort(factory).get_many((source_id,))[
        source_id
    ]
    assert (availability.state, availability.video_file_size_bytes) == (
        "ready",
        2_000_000_000,
    )


def test_ambiguous_media_waits_for_one_complete_candidate_selection(context) -> None:
    factory, job_id = context
    fake = FakeCloud115(
        directory_infos=[_directory(), _directory()],
        file_batches=[
            (
                _file("a", "feature-a.mkv", 1_000_000_000),
                _file("b", "feature-b.mkv", 1_000_000_000),
            )
        ],
    )
    assert _resolver(factory, fake).run_once(worker_id="resolver-a") == "worked"

    with factory() as session:
        job = session.get(CacheJob, job_id)
        candidates = list(
            session.scalars(select(RemoteMedia).order_by(RemoteMedia.file_id))
        )
        assert job is not None and job.status == "awaiting_selection"
        assert len(candidates) == 2
        assert session.scalar(select(func.count(CacheJobMediaSelection.media_id))) == 0
        source_id = job.source_id

    assert CacheSourceAvailabilityPort(factory).get_many((source_id,))[
        source_id
    ].state == ("running")

    selected = MediaSelectionService(factory, now=lambda: NOW).select(
        job_id=job_id,
        media_ids=(candidates[0].id,),
    )
    assert selected.status == "ready"
    assert selected.selected_media_ids == (candidates[0].id,)


def test_resolver_directory_move_detaches_without_partial_media(context) -> None:
    factory, job_id = context
    moved = DirectoryInfo(
        cid="task",
        parent_cid="outside",
        name="cache-fixture",
        path=(DirectoryBreadcrumb("outside", "outside"),),
    )
    fake = FakeCloud115(
        directory_infos=[_directory(), moved],
        file_batches=[(_file("main", "IPX-001.mkv", 2_000_000_000),)],
    )

    assert _resolver(factory, fake).run_once(worker_id="resolver-a") == "worked"

    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None and job.status == "detached"
        assert session.scalar(select(func.count(RemoteMedia.id))) == 0


def test_segment_candidate_must_be_selected_as_complete_ordered_group(context) -> None:
    factory, job_id = context
    fake = FakeCloud115(
        directory_infos=[_directory(), _directory()],
        file_batches=[
            (
                _file("main", "IPX-001.mkv", 2_000_000_000),
                _file("cd1", "IPX-001-CD1.mkv", 1_000_000_000),
                _file("cd2", "IPX-001-CD2.mkv", 1_000_000_000),
            )
        ],
    )
    assert _resolver(factory, fake).run_once(worker_id="resolver-a") == "worked"
    with factory() as session:
        segments = list(
            session.scalars(
                select(RemoteMedia)
                .where(RemoteMedia.file_id.in_(("cd1", "cd2")))
                .order_by(RemoteMedia.sequence_no)
            )
        )
    service = MediaSelectionService(factory, now=lambda: NOW)
    with pytest.raises(MediaSelectionProblem) as raised:
        service.select(job_id=job_id, media_ids=(segments[0].id,))
    assert raised.value.code == "state_conflict"

    result = service.select(
        job_id=job_id,
        media_ids=(segments[1].id, segments[0].id),
    )
    assert result.selected_media_ids == (segments[0].id, segments[1].id)


def test_resolver_without_valid_video_fails_deterministically(context) -> None:
    factory, job_id = context
    fake = FakeCloud115(
        directory_infos=[_directory(), _directory()],
        file_batches=[(_file("tiny", "tiny.mp4", 1000),)],
    )

    assert _resolver(factory, fake).run_once(worker_id="resolver-a") == "worked"

    with factory() as session:
        job = session.get(CacheJob, job_id)
        assert job is not None
        assert (job.status, job.failure_code) == ("failed", "cache_no_valid_media")


def test_cache_pipeline_advances_offline_and_resolution_without_starvation() -> None:
    calls: list[str] = []

    class Consumer:
        def __init__(self, name: str, result: str) -> None:
            self.name = name
            self.result = result

        def run_once(self, *, worker_id: str) -> str:
            assert worker_id == "worker-a"
            calls.append(self.name)
            return self.result

    pipeline = CacheWorkerPipeline(
        Consumer("offline", "worked"),
        Consumer("resolution", "worked"),
    )

    assert pipeline.run_once(worker_id="worker-a") == "worked"
    assert calls == ["offline", "resolution"]


def _resolver(factory, fake):
    @asynccontextmanager
    async def cloud_scope(_claim):
        yield fake

    return CacheMediaResolver(
        CacheJobClaimQueue(factory, now=lambda: NOW),
        cloud_scope,
        now=lambda: NOW,
    )


def _directory() -> DirectoryInfo:
    return DirectoryInfo(
        cid="task",
        parent_cid="root",
        name="cache-fixture",
        path=(DirectoryBreadcrumb("root", "SakuraPlayer-Cache"),),
    )


def _file(
    file_id: str,
    name: str,
    size: int,
    *,
    parent: str = "task",
) -> RemoteFile:
    return RemoteFile(
        file_id=file_id,
        parent_cid=parent,
        name=name,
        size_bytes=size,
        pickcode=f"pick-{file_id}",
        sha1=None,
        is_directory=False,
        is_video=name.endswith((".mkv", ".mp4")),
        duration_seconds=3600 if name.endswith((".mkv", ".mp4")) else None,
        blocked=False,
    )
