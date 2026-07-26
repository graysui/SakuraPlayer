from pathlib import Path
from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.actor_mapping import (
    ActorMappingReconciler,
    ActorMappingProblem,
    normalize_actor_alias,
    parse_actor_mapping,
)
from sakuraplayer.catalog.models import Actor, ActorAlias
from sakuraplayer.identity.models import Base
from sakuraplayer.resources import models as resource_models


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "catalog"


def test_actor_mapping_parses_authoritative_names_aliases_and_bio() -> None:
    entries = parse_actor_mapping((FIXTURES / "actor_mapping.xml").read_bytes())

    assert len(entries) == 3
    first = entries[0]
    assert first.name_ja == "Actor One"
    assert first.name_zh == "演员一"
    assert first.bio_zh == "演员一简介"
    assert first.aliases == ("Actor One", "Alias One", "演员一", "演員一")


def test_actor_alias_normalization_is_shared_casefold_and_whitespace() -> None:
    assert normalize_actor_alias("  ACTOR\t One  ") == "actor one"
    assert normalize_actor_alias("　演员　一　") == "演员 一"


def test_actor_mapping_rejects_dtd_and_external_entity() -> None:
    with pytest.raises(ActorMappingProblem) as caught:
        parse_actor_mapping((FIXTURES / "actor_mapping_xxe.xml").read_bytes())

    assert caught.value.code == "provider_snapshot_invalid"


@pytest.mark.parametrize(
    "payload",
    (
        b"<wrong />",
        b"<actor-mapping><wrong /></actor-mapping>",
        b'<actor-mapping><actor><a jp="A" zh_cn="A" zh_tw="A" '
        b'keyword="A" unexpected="x" /></actor></actor-mapping>',
        b'<actor-mapping><actor><a jp="" zh_cn="A" zh_tw="A" '
        b'keyword="A" /></actor></actor-mapping>',
    ),
)
def test_actor_mapping_rejects_unknown_or_incomplete_structure(payload: bytes) -> None:
    with pytest.raises(ActorMappingProblem) as caught:
        parse_actor_mapping(payload)

    assert caught.value.code == "provider_snapshot_invalid"


def test_actor_mapping_rebuilds_only_unique_javdb_actor_and_preserves_javdb_aliases() -> None:
    assert resource_models.Movie.__tablename__ == "movie"
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    current = datetime(2026, 7, 26, 21, 0, tzinfo=timezone.utc)
    actor_one = uuid.uuid4()
    same_one = uuid.uuid4()
    same_two = uuid.uuid4()
    with factory.begin() as session:
        session.add_all(
            (
                _actor(actor_one, "javdb-1", "Current JavDB Name", current),
                _actor(same_one, "javdb-2", "Same Name", current),
                _actor(same_two, "javdb-3", "Same Name", current),
                ActorAlias(
                    actor_id=actor_one,
                    alias="Actor One",
                    normalized_alias="actor one",
                    authority="javdb",
                ),
                ActorAlias(
                    actor_id=actor_one,
                    alias="Alias One",
                    normalized_alias="alias one",
                    authority="javdb",
                ),
                ActorAlias(
                    actor_id=actor_one,
                    alias="Stale Mapping",
                    normalized_alias="stale mapping",
                    authority="actor_mapping",
                ),
            )
        )
    entries = parse_actor_mapping((FIXTURES / "actor_mapping.xml").read_bytes())

    outcome = ActorMappingReconciler(factory, now=lambda: current).rebuild(entries)

    assert outcome.matched_actors == 1
    assert outcome.discarded_entries == 2
    with factory() as session:
        actor = session.get(Actor, actor_one)
        assert actor is not None
        assert actor.name_ja == "Current JavDB Name"
        assert actor.name_zh == "演员一"
        assert actor.bio_zh == "演员一简介"
        aliases = list(
            session.scalars(
                select(ActorAlias)
                .where(ActorAlias.actor_id == actor_one)
                .order_by(ActorAlias.normalized_alias)
            )
        )
        assert [(item.normalized_alias, item.authority) for item in aliases] == [
            ("actor one", "javdb"),
            ("alias one", "javdb"),
            ("演员一", "actor_mapping"),
            ("演員一", "actor_mapping"),
        ]
        assert session.get(Actor, same_one).name_zh is None
        assert session.get(Actor, same_two).name_zh is None
    engine.dispose()


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
