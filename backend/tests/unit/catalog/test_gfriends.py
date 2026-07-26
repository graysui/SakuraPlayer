from pathlib import Path
from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.gfriends import (
    GfriendsAssetReconciler,
    GfriendsEntry,
    GfriendsProblem,
    parse_gfriends,
)
from sakuraplayer.catalog.models import (
    Actor,
    ActorAlias,
    GfriendsActorAsset,
    GfriendsSnapshot,
)
from sakuraplayer.identity.models import Base
from sakuraplayer.resources import models as resource_models


FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "catalog" / "gfriends.json"
)


def test_gfriends_parses_fixed_content_urls_without_downloading_images() -> None:
    entries = parse_gfriends(FIXTURE.read_bytes())

    assert [(entry.match_name, entry.url) for entry in entries] == [
        (
            "Actor One",
            "https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/"
            "fixture-source/Actor%20One.jpg?t=1600000000",
        ),
        (
            "Alias One",
            "https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/"
            "fixture-source/Actor%20One%20profile.jpg?t=1600000001",
        ),
        (
            "Marin.",
            "https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/"
            "fixture-source/Marin..jpg?t=1600000003",
        ),
        (
            "Same Name",
            "https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/"
            "fixture-source/Same%20Name.jpg?t=1600000002",
        ),
    ]


@pytest.mark.parametrize(
    "value",
    (
        "../escape.jpg?t=1",
        "/absolute.jpg?t=1",
        "https://evil.invalid/image.jpg?t=1",
        "nested/path.jpg?t=1",
        "back\\slash.jpg?t=1",
        "image.gif?t=1",
        "image.jpg?token=secret",
        "image.jpg?t=1&t=2",
    ),
)
def test_gfriends_rejects_unsafe_content_value(value: str) -> None:
    payload = (
        '{"Content":{"source":{"Actor.jpg":'
        + repr(value).replace("'", '"')
        + "}}}"
    ).encode()

    with pytest.raises(GfriendsProblem) as caught:
        parse_gfriends(payload)

    assert caught.value.code == "provider_snapshot_invalid"


@pytest.mark.parametrize(
    "payload",
    (
        b"[]",
        b'{"Content":[]}',
        b'{"Content":{".":{"Actor.jpg":"Actor.jpg?t=1"}}}',
        b'{"Content":{"source":{"../Actor.jpg":"Actor.jpg?t=1"}}}',
        b'{"Content":{"https:evil":{"Actor.jpg":"Actor.jpg?t=1"}}}',
        b'{"Content":{"source":{"https:evil.jpg":"Actor.jpg?t=1"}}}',
        b'{"Content":{"C:drive":{"Actor.jpg":"Actor.jpg?t=1"}}}',
        b'{"Content":{"source":{"Actor.jpg":{"nested":"x"}}}}',
    ),
)
def test_gfriends_rejects_invalid_shape_or_path_segments(payload: bytes) -> None:
    with pytest.raises(GfriendsProblem) as caught:
        parse_gfriends(payload)

    assert caught.value.code == "provider_snapshot_invalid"


def test_gfriends_rebuilds_unique_assets_and_removes_stale_rows() -> None:
    engine, factory, actor_one, _, _, snapshot_id, current = _asset_factory()
    entries = parse_gfriends(FIXTURE.read_bytes())
    reconciler = GfriendsAssetReconciler(factory, now=lambda: current)

    outcome = reconciler.rebuild(entries, snapshot_id=snapshot_id)

    assert outcome.matched_actors == 1
    assert outcome.asset_count == 2
    with factory() as session:
        assets = list(
            session.scalars(
                select(GfriendsActorAsset).order_by(GfriendsActorAsset.position)
            )
        )
        assert [asset.actor_id for asset in assets] == [actor_one, actor_one]
        assert [(asset.asset_kind, asset.position) for asset in assets] == [
            ("profile", 0),
            ("gallery", 1),
        ]
        assert [asset.url for asset in assets] == sorted(asset.url for asset in assets)

    reconciler.rebuild(
        (GfriendsEntry(match_name="Same Name", url=entries[-1].url),),
        snapshot_id=snapshot_id,
    )
    with factory() as session:
        assert list(session.scalars(select(GfriendsActorAsset))) == []
    engine.dispose()


def test_gfriends_discards_url_that_resolves_to_different_actors() -> None:
    engine, factory, actor_one, actor_two, _, snapshot_id, current = _asset_factory()
    shared_url = (
        "https://raw.githubusercontent.com/li-peifeng/gfriends/main/Content/"
        "fixture-source/shared.jpg?t=1"
    )

    outcome = GfriendsAssetReconciler(factory, now=lambda: current).rebuild(
        (
            GfriendsEntry(match_name="Actor One", url=shared_url),
            GfriendsEntry(match_name="Actor Two", url=shared_url),
        ),
        snapshot_id=snapshot_id,
    )

    assert outcome.asset_count == 0
    assert outcome.discarded_entries == 2
    with factory() as session:
        assert session.get(Actor, actor_one) is not None
        assert session.get(Actor, actor_two) is not None
        assert list(session.scalars(select(GfriendsActorAsset))) == []
    engine.dispose()


def _asset_factory():
    assert resource_models.Movie.__tablename__ == "movie"
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    current = datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc)
    actor_one = uuid.uuid4()
    actor_two = uuid.uuid4()
    same_two = uuid.uuid4()
    snapshot_id = uuid.uuid4()
    with factory.begin() as session:
        session.add_all(
            (
                _actor(actor_one, "javdb-1", "Actor One", current),
                _actor(actor_two, "javdb-2", "Actor Two", current),
                _actor(same_two, "javdb-3", "Same Name", current),
                ActorAlias(
                    actor_id=actor_one,
                    alias="Alias One",
                    normalized_alias="alias one",
                    authority="javdb",
                ),
                ActorAlias(
                    actor_id=actor_two,
                    alias="Same Name",
                    normalized_alias="same name",
                    authority="javdb",
                ),
                GfriendsSnapshot(
                    id=snapshot_id,
                    sha256="a" * 64,
                    byte_size=100,
                    relative_path="metadata/gfriends/a.json",
                    status="current",
                    fetched_at=current,
                    activated_at=current,
                ),
            )
        )
    return engine, factory, actor_one, actor_two, same_two, snapshot_id, current


def _actor(
    actor_id: uuid.UUID,
    javdb_id: str,
    name_ja: str,
    current: datetime,
) -> Actor:
    return Actor(
        id=actor_id,
        javdb_id=javdb_id,
        name_ja=name_ja,
        name_zh=None,
        bio_original=None,
        bio_zh=None,
        gender="unknown",
        created_at=current,
        updated_at=current,
    )
