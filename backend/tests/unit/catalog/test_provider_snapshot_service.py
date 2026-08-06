import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.models import (
    Actor,
    ActorMappingSnapshot,
    GfriendsActorAsset,
    GfriendsSnapshot,
    ProviderSnapshotRequest,
)
from sakuraplayer.catalog.provider_snapshots import (
    ACTOR_MAPPING_SOURCE,
    GFRIENDS_SOURCE,
    ProviderSnapshotDownloader,
    ProviderSnapshotQueue,
    ProviderSnapshotRefreshService,
    ProviderSnapshotRegistry,
    ProviderSnapshotStore,
    SnapshotProblem,
    SnapshotSource,
)
from sakuraplayer.identity.models import Base
from sakuraplayer.resources import models as resource_models


def _factory():
    assert resource_models.Movie.__tablename__ == "movie"
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def test_snapshot_sources_are_frozen_with_expected_size_limits() -> None:
    assert ACTOR_MAPPING_SOURCE.url == (
        "https://raw.githubusercontent.com/li-peifeng/"
        "Jav-Actors-Mapping/main/actor-mapping.xml"
    )
    assert ACTOR_MAPPING_SOURCE.max_bytes == 16 * 1024 * 1024
    assert GFRIENDS_SOURCE.url == (
        "https://raw.githubusercontent.com/li-peifeng/gfriends/main/Filetree.json"
    )
    assert GFRIENDS_SOURCE.max_bytes == 32 * 1024 * 1024


def test_snapshot_queue_coalesces_duplicate_scheduler_minute() -> None:
    engine, factory = _factory()
    queue = ProviderSnapshotQueue(
        factory,
        now=lambda: datetime(2026, 7, 26, 21, 0, 45, tzinfo=timezone.utc),
    )

    first = queue.enqueue()
    repeated = queue.enqueue()

    assert first.created is True
    assert repeated.created is False
    assert repeated.request_id == first.request_id
    with factory() as session:
        requests = list(session.scalars(select(ProviderSnapshotRequest)))
        assert len(requests) == 1
        assert requests[0].scheduled_for == datetime(2026, 7, 26, 21, 0)
        assert requests[0].status == "queued"
        assert requests[0].attempt_count == 0
    engine.dispose()


def test_initial_snapshot_request_is_created_once_and_failure_is_not_retried() -> None:
    engine, factory = _factory()
    current = [datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc)]
    queue = ProviderSnapshotQueue(factory, now=lambda: current[0])

    first = queue.ensure_initial()
    repeated = queue.ensure_initial()

    assert first is not None and first.created is True
    assert repeated is None
    claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))
    assert claim is not None
    queue.fail(claim, code="provider_snapshot_upstream_error")
    current[0] += timedelta(days=1)
    assert queue.ensure_initial() is None
    with factory() as session:
        requests = list(session.scalars(select(ProviderSnapshotRequest)))
        assert len(requests) == 1
        assert requests[0].status == "failed"
    engine.dispose()


def test_initial_snapshot_request_skips_complete_current_snapshots() -> None:
    engine, factory = _factory()
    current = datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc)
    with factory.begin() as session:
        session.add_all(
            [
                ActorMappingSnapshot(
                    id=uuid.uuid4(),
                    sha256="a" * 64,
                    byte_size=1,
                    relative_path="metadata/actor_mapping/current.xml",
                    status="current",
                    fetched_at=current,
                    activated_at=current,
                ),
                GfriendsSnapshot(
                    id=uuid.uuid4(),
                    sha256="b" * 64,
                    byte_size=1,
                    relative_path="metadata/gfriends/current.json",
                    status="current",
                    fetched_at=current,
                    activated_at=current,
                ),
            ]
        )

    queue = ProviderSnapshotQueue(factory, now=lambda: current)

    assert queue.ensure_initial() is None
    with factory() as session:
        assert session.scalar(select(ProviderSnapshotRequest.id)) is None
    engine.dispose()


def test_snapshot_queue_claims_and_completes_with_fenced_token() -> None:
    engine, factory = _factory()
    current = datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc)
    queue = ProviderSnapshotQueue(factory, now=lambda: current)
    enqueued = queue.enqueue()

    claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=30))

    assert claim is not None
    assert claim.request_id == enqueued.request_id
    assert claim.claim_owner == "worker-1"
    queue.complete(claim)
    with factory() as session:
        request = session.get(ProviderSnapshotRequest, enqueued.request_id)
        assert request is not None and request.status == "completed"
        assert request.attempt_count == 1
        assert request.claim_owner is None
        assert request.claim_token is None
        assert request.claim_expires_at is None
        assert request.completed_at == current.replace(tzinfo=None)
    engine.dispose()


def test_snapshot_queue_reclaims_expired_request_and_rejects_old_claim() -> None:
    engine, factory = _factory()
    current = [datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc)]
    queue = ProviderSnapshotQueue(factory, now=lambda: current[0])
    queue.enqueue()
    old_claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))
    current[0] += timedelta(minutes=6)

    new_claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))

    assert old_claim is not None and new_claim is not None
    assert old_claim.claim_token != new_claim.claim_token
    with pytest.raises(RuntimeError, match="provider snapshot request claim was lost"):
        queue.complete(old_claim)
    queue.fail(new_claim, code="UPSTREAM exploded https://secret.invalid/?token=x")
    with factory() as session:
        request = session.get(ProviderSnapshotRequest, new_claim.request_id)
        assert request is not None and request.status == "failed"
        assert request.attempt_count == 2
        assert request.failure_code == "internal_error"
    engine.dispose()


def test_snapshot_queue_renews_only_active_claim() -> None:
    engine, factory = _factory()
    current = [datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc)]
    queue = ProviderSnapshotQueue(factory, now=lambda: current[0])
    queue.enqueue()
    claim = queue.claim_next("worker-1", lease_duration=timedelta(minutes=5))
    assert claim is not None
    current[0] += timedelta(minutes=1)

    queue.renew(claim, lease_duration=timedelta(minutes=10))

    with factory() as session:
        request = session.get(ProviderSnapshotRequest, claim.request_id)
        assert request is not None
        assert request.claim_expires_at == datetime(2026, 7, 26, 21, 11)
    current[0] += timedelta(minutes=11)
    with pytest.raises(RuntimeError, match="provider snapshot request claim was lost"):
        queue.renew(claim, lease_duration=timedelta(minutes=10))
    engine.dispose()


def test_snapshot_downloader_validates_payload_and_digest() -> None:
    payload = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "catalog"
        / "actor_mapping.xml"
    ).read_bytes()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=payload, request=request)
        )
    )

    downloaded = ProviderSnapshotDownloader(client).fetch(ACTOR_MAPPING_SOURCE)

    assert downloaded.source == ACTOR_MAPPING_SOURCE
    assert downloaded.payload == payload
    assert downloaded.byte_size == len(payload)
    assert downloaded.sha256 == hashlib.sha256(payload).hexdigest()
    client.close()


def test_snapshot_probe_uses_head_without_downloading_payload() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"Content-Length": "1024"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        assert ProviderSnapshotDownloader(client).probe(GFRIENDS_SOURCE) is None
    finally:
        client.close()

    assert len(seen) == 1
    assert seen[0].method == "HEAD"


def test_snapshot_downloader_revalidates_redirect_and_stops_at_limit() -> None:
    calls = 0

    def same_url_redirect(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            302,
            headers={"Location": str(request.url)},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(same_url_redirect))
    with pytest.raises(SnapshotProblem) as caught:
        ProviderSnapshotDownloader(client).fetch(ACTOR_MAPPING_SOURCE)
    assert caught.value.code == "provider_snapshot_invalid"
    assert calls == 4
    client.close()

    evil = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                302,
                headers={"Location": "https://evil.invalid/payload.xml"},
                request=request,
            )
        )
    )
    with pytest.raises(SnapshotProblem):
        ProviderSnapshotDownloader(evil).fetch(ACTOR_MAPPING_SOURCE)
    evil.close()


def test_snapshot_downloader_rejects_declared_and_streamed_size_overflow() -> None:
    source = SnapshotSource(
        name="fixture",
        url="https://raw.githubusercontent.com/example/repo/main/fixture.bin",
        max_bytes=4,
        suffix=".bin",
        upstream_error="fixture_upstream_error",
        validate=lambda payload: None,
    )
    declared = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"Content-Length": "5"},
                content=b"12345",
                request=request,
            )
        )
    )
    with pytest.raises(SnapshotProblem) as caught:
        ProviderSnapshotDownloader(declared).fetch(source)
    assert caught.value.code == "provider_snapshot_invalid"
    declared.close()

    streamed = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"12345", request=request)
        )
    )
    with pytest.raises(SnapshotProblem):
        ProviderSnapshotDownloader(streamed).fetch(source)
    streamed.close()


def test_snapshot_store_and_registry_atomically_switch_current(tmp_path: Path) -> None:
    engine, factory = _factory()
    fixture = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "catalog"
        / "actor_mapping.xml"
    ).read_bytes()
    payloads = [fixture, fixture.replace("演员一".encode(), "演员二".encode(), 1)]
    store = ProviderSnapshotStore(tmp_path)
    registry = ProviderSnapshotRegistry(
        factory,
        now=lambda: datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc),
    )
    activated = []
    for payload in payloads:
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request, body=payload: httpx.Response(
                    200,
                    content=body,
                    request=request,
                )
            )
        )
        downloaded = ProviderSnapshotDownloader(client).fetch(ACTOR_MAPPING_SOURCE)
        relative_path = store.store(downloaded)
        activated.append(registry.activate(downloaded, relative_path=relative_path))
        client.close()

    assert activated[0] != activated[1]
    current = registry.current("actor_mapping")
    assert current is not None and current.snapshot_id == activated[1]
    assert (tmp_path / current.relative_path).is_file()
    with factory() as session:
        snapshots = list(
            session.scalars(
                select(ActorMappingSnapshot).order_by(ActorMappingSnapshot.sha256)
            )
        )
        assert {snapshot.status for snapshot in snapshots} == {
            "current",
            "superseded",
        }
    repeated = registry.activate(
        ProviderSnapshotDownloader(
            httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        content=payloads[-1],
                        request=request,
                    )
                )
            )
        ).fetch(ACTOR_MAPPING_SOURCE),
        relative_path=current.relative_path,
    )
    assert repeated == activated[1]
    engine.dispose()


def test_refresh_service_keeps_failed_source_and_independently_activates_other(
    tmp_path: Path,
) -> None:
    engine, factory = _factory()
    fixture_root = Path(__file__).resolve().parents[2] / "fixtures" / "catalog"
    actor_valid = (fixture_root / "actor_mapping.xml").read_bytes()
    actor_invalid = (fixture_root / "actor_mapping_xxe.xml").read_bytes()
    gfriends_valid = (fixture_root / "gfriends.json").read_bytes()
    gfriends_updated = gfriends_valid.replace(b"1600000003", b"1600000004")
    payloads = {
        str(ACTOR_MAPPING_SOURCE.url): [actor_valid, actor_invalid],
        "https://raw.githubusercontent.com/li-peifeng/gfriends/main/Filetree.json": [
            gfriends_valid,
            gfriends_updated,
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payloads[str(request.url)].pop(0),
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ProviderSnapshotRefreshService(
        factory,
        http_client=client,
        cache_root=tmp_path,
        now=lambda: datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc),
    )

    first = service.refresh_all()
    actor_current = service.registry.current("actor_mapping")
    gfriends_current = service.registry.current("gfriends")
    second = service.refresh_all()

    assert first.failures == ()
    assert second.failures == (("actor_mapping", "provider_snapshot_invalid"),)
    assert service.registry.current("actor_mapping").snapshot_id == (
        actor_current.snapshot_id
    )
    assert service.registry.current("gfriends").snapshot_id != (
        gfriends_current.snapshot_id
    )
    client.close()
    engine.dispose()


def test_refresh_service_reapplies_same_snapshots_to_actors_added_later(
    tmp_path: Path,
) -> None:
    engine, factory = _factory()
    fixture_root = Path(__file__).resolve().parents[2] / "fixtures" / "catalog"
    payloads = {
        ACTOR_MAPPING_SOURCE.url: (fixture_root / "actor_mapping.xml").read_bytes(),
        GFRIENDS_SOURCE.url: (fixture_root / "gfriends.json").read_bytes(),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payloads[str(request.url)], request=request)

    current = datetime(2026, 8, 6, 3, 0, tzinfo=timezone.utc)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = ProviderSnapshotRefreshService(
        factory,
        http_client=client,
        cache_root=tmp_path,
        now=lambda: current,
    )

    initial = service.refresh_all()
    actor_snapshot = service.registry.current("actor_mapping")
    gfriends_snapshot = service.registry.current("gfriends")
    assert initial.failures == ()
    assert actor_snapshot is not None
    assert gfriends_snapshot is not None
    with factory.begin() as session:
        session.add(
            Actor(
                id=uuid.uuid4(),
                javdb_id="actor-added-after-snapshot",
                name_ja="Actor One",
                name_zh=None,
                bio_original=None,
                bio_zh=None,
                gender="unknown",
                created_at=current,
                updated_at=current,
            )
        )

    repair = service.refresh_all()

    assert repair.failures == ()
    assert service.registry.current("actor_mapping").snapshot_id == (
        actor_snapshot.snapshot_id
    )
    assert service.registry.current("gfriends").snapshot_id == (
        gfriends_snapshot.snapshot_id
    )
    with factory() as session:
        actor = session.scalar(select(Actor))
        assets = list(
            session.scalars(
                select(GfriendsActorAsset).order_by(GfriendsActorAsset.position)
            )
        )
    assert actor is not None
    assert actor.name_zh == "演员一"
    assert actor.bio_zh == "演员一简介"
    assert [(asset.asset_kind, asset.position) for asset in assets] == [
        ("profile", 0),
        ("gallery", 1),
    ]
    client.close()
    engine.dispose()
