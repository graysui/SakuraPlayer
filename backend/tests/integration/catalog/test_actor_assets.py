from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import httpx
import pytest
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from sakuraplayer.catalog.gfriends import GfriendsAssetReconciler, GfriendsEntry
from sakuraplayer.catalog.models import (
    Actor,
    ActorAlias,
    ActorMappingSnapshot,
    CatalogImage,
    GfriendsActorAsset,
    GfriendsSnapshot,
    ProviderSnapshotRequest,
)
from sakuraplayer.catalog.provider_snapshots import (
    ACTOR_MAPPING_SOURCE,
    GFRIENDS_SOURCE,
    ProviderSnapshotQueue,
    ProviderSnapshotRefreshService,
)
from sakuraplayer.shared.migration import upgrade_database

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "catalog"
NOW = datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc)


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task009_{uuid.uuid4().hex}"
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


def test_provider_snapshot_migration_and_current_indexes(database_url: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(config, "0008_catalog_metadata")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert "provider_snapshot_request" not in tables
        assert "actor_mapping_snapshot" not in tables
        assert "gfriends_snapshot" not in tables
        assert "gfriends_actor_asset" not in tables
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    for model, prefix in (
        (ActorMappingSnapshot, "actor_mapping"),
        (GfriendsSnapshot, "gfriends"),
    ):
        with pytest.raises(IntegrityError):
            with factory.begin() as session:
                session.add_all(
                    _snapshots(model, prefix=prefix, statuses=("current", "current"))
                )
        with factory.begin() as session:
            session.add_all(
                _snapshots(model, prefix=prefix, statuses=("current", "superseded"))
            )
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(
                ActorMappingSnapshot(
                    id=uuid.uuid4(),
                    sha256="3" * 64,
                    byte_size=16 * 1024 * 1024 + 1,
                    relative_path="metadata/actor_mapping/oversize.xml",
                    status="superseded",
                    fetched_at=NOW,
                    activated_at=NOW,
                )
            )
    engine.dispose()


def test_upgrade_queues_one_repair_without_overwriting_existing_catalog(
    database_url: str,
) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(config, "0021_metadata_worker_control")
    engine = create_engine(database_url, hide_parameters=True)
    actor_id = uuid.uuid4()
    failed_request_id = uuid.uuid4()
    gfriends_snapshot_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO actor "
                "(id, javdb_id, name_ja, name_zh, bio_original, bio_zh, gender, "
                "created_at, updated_at) VALUES "
                "(:id, 'upgrade-actor', 'Actor One', NULL, NULL, NULL, "
                "'unknown', :now, :now)"
            ),
            {"id": actor_id, "now": NOW},
        )
        connection.execute(
            text(
                "INSERT INTO gfriends_snapshot "
                "(id, sha256, byte_size, relative_path, status, fetched_at, "
                "activated_at) VALUES "
                "(:id, :sha256, 1, 'metadata/gfriends/existing.json', "
                "'current', :now, :now)"
            ),
            {"id": gfriends_snapshot_id, "sha256": "f" * 64, "now": NOW},
        )
        connection.execute(
            text(
                "INSERT INTO provider_snapshot_request "
                "(id, scheduled_for, status, claim_owner, claim_token, "
                "claim_expires_at, attempt_count, created_at, completed_at, "
                "failure_code) VALUES "
                "(:id, :scheduled_for, 'failed', NULL, NULL, NULL, 1, :now, "
                ":now, 'provider_snapshot_invalid')"
            ),
            {
                "id": failed_request_id,
                "scheduled_for": NOW - timedelta(days=1),
                "now": NOW,
            },
        )
    engine.dispose()

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        requests = list(
            connection.execute(
                text(
                    "SELECT id, status, attempt_count FROM provider_snapshot_request "
                    "ORDER BY scheduled_for"
                )
            )
        )
        actor = connection.execute(
            text("SELECT javdb_id, name_ja FROM actor WHERE id = :id"),
            {"id": actor_id},
        ).one()
        gfriends_current = connection.scalar(
            text(
                "SELECT id FROM gfriends_snapshot "
                "WHERE id = :id AND status = 'current'"
            ),
            {"id": gfriends_snapshot_id},
        )
    assert [(str(row.id), row.status, row.attempt_count) for row in requests] == [
        (str(failed_request_id), "failed", 1),
        ("03260000-0000-4000-8000-000000000001", "queued", 0),
    ]
    assert actor == ("upgrade-actor", "Actor One")
    assert gfriends_current == gfriends_snapshot_id
    engine.dispose()


@pytest.mark.parametrize("complete_snapshots", (False, True))
def test_upgrade_does_not_duplicate_active_or_complete_snapshot_state(
    database_url: str,
    complete_snapshots: bool,
) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(config, "0021_metadata_worker_control")
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    expected_request_ids: set[uuid.UUID] = set()
    with factory.begin() as session:
        if complete_snapshots:
            session.add_all(
                (
                    ActorMappingSnapshot(
                        id=uuid.uuid4(),
                        sha256="a" * 64,
                        byte_size=1,
                        relative_path="metadata/actor_mapping/current.xml",
                        status="current",
                        fetched_at=NOW,
                        activated_at=NOW,
                    ),
                    GfriendsSnapshot(
                        id=uuid.uuid4(),
                        sha256="b" * 64,
                        byte_size=1,
                        relative_path="metadata/gfriends/current.json",
                        status="current",
                        fetched_at=NOW,
                        activated_at=NOW,
                    ),
                )
            )
        else:
            active_request_id = uuid.uuid4()
            expected_request_ids.add(active_request_id)
            session.add(
                ProviderSnapshotRequest(
                    id=active_request_id,
                    scheduled_for=NOW,
                    status="queued",
                    claim_owner=None,
                    claim_token=None,
                    claim_expires_at=None,
                    attempt_count=0,
                    created_at=NOW,
                    completed_at=None,
                    failure_code=None,
                )
            )
    engine.dispose()

    command.upgrade(config, "head")

    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        request_ids = set(
            connection.scalars(text("SELECT id FROM provider_snapshot_request"))
        )
    assert request_ids == expected_request_ids
    engine.dispose()


def test_postgres_queue_reclaims_expired_claim_and_fences_old_token(
    database_url: str,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    current = [NOW]
    queue = ProviderSnapshotQueue(factory, now=lambda: current[0])
    request = queue.enqueue()
    repeated = queue.enqueue()
    assert repeated.created is False
    assert repeated.request_id == request.request_id
    old_claim = queue.claim_next("worker-old", lease_duration=timedelta(minutes=5))
    assert old_claim is not None
    current[0] += timedelta(minutes=6)

    new_claim = queue.claim_next("worker-new", lease_duration=timedelta(minutes=5))

    assert new_claim is not None
    assert new_claim.request_id == old_claim.request_id == request.request_id
    assert new_claim.claim_token != old_claim.claim_token
    with pytest.raises(RuntimeError, match="claim was lost"):
        queue.complete(old_claim)
    queue.complete(new_claim)
    with factory() as session:
        persisted = session.get(ProviderSnapshotRequest, request.request_id)
        assert persisted is not None
        assert persisted.status == "completed"
        assert persisted.attempt_count == 2
    engine.dispose()


def test_postgres_serializes_concurrent_gfriends_rebuilds(database_url: str) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    actor_id = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    with factory.begin() as session:
        session.add_all(
            (
                Actor(
                    id=actor_id,
                    javdb_id="concurrent-actor",
                    name_ja="Concurrent Actor",
                    name_zh=None,
                    bio_original=None,
                    bio_zh=None,
                    gender="unknown",
                    created_at=NOW,
                    updated_at=NOW,
                ),
                GfriendsSnapshot(
                    id=snapshot_id,
                    sha256="c" * 64,
                    byte_size=100,
                    relative_path="metadata/gfriends/concurrent.json",
                    status="current",
                    fetched_at=NOW,
                    activated_at=NOW,
                ),
            )
        )
    entries = (
        GfriendsEntry(
            match_name="Concurrent Actor",
            url=(
                "https://raw.githubusercontent.com/li-peifeng/gfriends/main/"
                "Content/fixture/concurrent-1.jpg?t=1"
            ),
        ),
        GfriendsEntry(
            match_name="Concurrent Actor",
            url=(
                "https://raw.githubusercontent.com/li-peifeng/gfriends/main/"
                "Content/fixture/concurrent-2.jpg?t=2"
            ),
        ),
    )
    barrier = Barrier(2)

    def rebuild() -> None:
        barrier.wait()
        GfriendsAssetReconciler(factory, now=lambda: NOW).rebuild(
            entries,
            snapshot_id=snapshot_id,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: rebuild(), range(2)))

    with factory() as session:
        assets = list(
            session.scalars(
                select(GfriendsActorAsset).order_by(GfriendsActorAsset.position)
            )
        )
    assert [(asset.asset_kind, asset.position) for asset in assets] == [
        ("profile", 0),
        ("gallery", 1),
    ]
    assert len({asset.url for asset in assets}) == 2
    engine.dispose()


def test_refresh_fallback_rebuild_cleanup_and_catalog_image_isolation(
    database_url: str,
    tmp_path: Path,
) -> None:
    engine = create_engine(database_url, hide_parameters=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    actor_id = uuid.uuid4()
    image_id = uuid.uuid4()
    with factory.begin() as session:
        session.add_all(
            (
                Actor(
                    id=actor_id,
                    javdb_id="fixture-actor-one",
                    name_ja="Actor One",
                    name_zh=None,
                    bio_original=None,
                    bio_zh=None,
                    gender="unknown",
                    created_at=NOW,
                    updated_at=NOW,
                ),
                CatalogImage(
                    id=image_id,
                    owner_type="actor",
                    owner_id=actor_id,
                    kind="profile",
                    position=0,
                    source_url="https://c0.jdbstatic.com/permanent.png",
                    relative_path=f"actor/{actor_id}/profile.png",
                    sha256="a" * 64,
                    status="ready",
                    created_at=NOW,
                ),
            )
        )

    actor_initial = (FIXTURES / "actor_mapping.xml").read_bytes()
    actor_invalid = (FIXTURES / "actor_mapping_xxe.xml").read_bytes()
    actor_updated = actor_initial.replace(
        b'keyword="Actor One,Alias One"',
        b'keyword="Actor One"',
    )
    gfriends_initial = (FIXTURES / "gfriends.json").read_bytes()
    gfriends_invalid = b'{"Content":[]}'
    gfriends_updated = (
        b'{"Content":{"fixture-source":{"Actor One.jpg":"Actor One.jpg?t=1700000000"}}}'
    )
    payloads = {
        ACTOR_MAPPING_SOURCE.url: [actor_initial, actor_invalid, actor_updated],
        GFRIENDS_SOURCE.url: [gfriends_initial, gfriends_invalid, gfriends_updated],
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
        cache_root=tmp_path / "provider-cache",
        now=lambda: NOW,
    )
    first = service.refresh_all()
    actor_current = service.registry.current("actor_mapping")
    gfriends_current = service.registry.current("gfriends")
    assert first.failures == ()
    assert actor_current is not None and gfriends_current is not None
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(ActorAlias.normalized_alias)).where(
                    ActorAlias.normalized_alias == "alias one",
                    ActorAlias.authority == "actor_mapping",
                )
            )
            == 1
        )
        assert session.scalar(select(func.count(GfriendsActorAsset.id))) == 2

    failed = service.refresh_all()

    assert failed.failures == (
        ("actor_mapping", "provider_snapshot_invalid"),
        ("gfriends", "provider_snapshot_invalid"),
    )
    assert (
        service.registry.current("actor_mapping").snapshot_id
        == actor_current.snapshot_id
    )
    assert (
        service.registry.current("gfriends").snapshot_id == gfriends_current.snapshot_id
    )
    with factory() as session:
        assert session.scalar(select(func.count(GfriendsActorAsset.id))) == 2

    final = service.refresh_all()

    assert final.failures == ()
    with factory() as session:
        mapping_aliases = list(
            session.scalars(
                select(ActorAlias.normalized_alias).where(
                    ActorAlias.authority == "actor_mapping"
                )
            )
        )
        assets = list(session.scalars(select(GfriendsActorAsset)))
        images = list(session.scalars(select(CatalogImage)))
    assert "alias one" not in mapping_aliases
    assert len(assets) == 1
    assert assets[0].snapshot_id == service.registry.current("gfriends").snapshot_id
    assert len(images) == 1 and images[0].id == image_id
    assert images[0].source_url == "https://c0.jdbstatic.com/permanent.png"
    assert list(tmp_path.rglob("*.jpg")) == []
    assert list(tmp_path.rglob("*.png")) == []
    client.close()
    engine.dispose()


def _snapshots(model, *, prefix: str, statuses: tuple[str, str]):
    return (
        model(
            id=uuid.uuid4(),
            sha256="1" * 64,
            byte_size=1,
            relative_path=f"metadata/{prefix}/one.snapshot",
            status=statuses[0],
            fetched_at=NOW,
            activated_at=NOW,
        ),
        model(
            id=uuid.uuid4(),
            sha256="2" * 64,
            byte_size=1,
            relative_path=f"metadata/{prefix}/two.snapshot",
            status=statuses[1],
            fetched_at=NOW,
            activated_at=NOW,
        ),
    )
