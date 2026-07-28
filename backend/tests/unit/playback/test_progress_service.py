from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog import models as _catalog_models  # noqa: F401
from sakuraplayer.identity.models import Base
from sakuraplayer.playback.progress import (
    MoviePlaybackStateService,
    ProgressVersionConflict,
)
from sakuraplayer.resources.models import Movie

NOW = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)


def test_expected_version_creates_updates_and_reopens_completed_state() -> None:
    service, movie_id = _context()

    first = service.update(
        movie_id=movie_id,
        expected_version=0,
        position_seconds=Decimal("42.5"),
        duration_seconds=None,
    )
    completed = service.update(
        movie_id=movie_id,
        expected_version=1,
        position_seconds=Decimal("950"),
        duration_seconds=Decimal("1000"),
    )
    reopened = service.update(
        movie_id=movie_id,
        expected_version=2,
        position_seconds=Decimal("100"),
        duration_seconds=Decimal("1000"),
    )

    assert (first.version, first.position_seconds, first.duration_seconds) == (
        1,
        Decimal("42.5"),
        None,
    )
    assert completed.completed is True
    assert completed.position_seconds == 0
    assert reopened.completed is False
    assert reopened.position_seconds == Decimal("100")
    assert reopened.version == 3


@pytest.mark.parametrize("expected_version", [0, 2, 99])
def test_old_or_future_version_returns_authoritative_state(
    expected_version: int,
) -> None:
    service, movie_id = _context()
    authoritative = service.update(
        movie_id=movie_id,
        expected_version=0,
        position_seconds=Decimal("10"),
        duration_seconds=Decimal("1000"),
    )

    with pytest.raises(ProgressVersionConflict) as error:
        service.update(
            movie_id=movie_id,
            expected_version=expected_version,
            position_seconds=Decimal("20"),
            duration_seconds=Decimal("1000"),
        )

    assert error.value.authoritative == authoritative
    assert service.get(movie_id) == authoritative


def test_future_version_conflict_without_state_returns_null_authority() -> None:
    service, movie_id = _context()

    with pytest.raises(ProgressVersionConflict) as error:
        service.update(
            movie_id=movie_id,
            expected_version=1,
            position_seconds=Decimal("20"),
            duration_seconds=None,
        )

    assert error.value.authoritative is None
    assert service.get(movie_id) is None


def test_catalog_port_reads_same_movie_state() -> None:
    service, movie_id = _context()
    service.update(
        movie_id=movie_id,
        expected_version=0,
        position_seconds=Decimal("25.125"),
        duration_seconds=Decimal("1000"),
    )

    projection = service.get_many((movie_id, uuid.uuid4()))

    assert set(projection) == {movie_id}
    assert projection[movie_id].position_seconds == 25.125
    assert projection[movie_id].version == 1


def _context() -> tuple[MoviePlaybackStateService, uuid.UUID]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    movie_id = uuid.uuid4()
    with factory.begin() as session:
        session.add(
            Movie(
                id=movie_id,
                normalized_number="TASK-111",
                raw_numbers=["TASK-111"],
                catalog_state="core_ready",
                created_at=NOW,
                updated_at=NOW,
            )
        )
    return MoviePlaybackStateService(factory, now=lambda: NOW), movie_id
