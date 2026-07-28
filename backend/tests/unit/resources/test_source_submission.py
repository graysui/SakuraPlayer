from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import Base
from sakuraplayer.resources.models import ResourceSource, SourceRejection
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import (
    SourceSubmissionProblem,
    SourceSubmissionService,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def context(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'sources.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"k" * 32},
        )
    )
    importer = SourceImporter(factory, cipher=cipher, now=lambda: NOW)
    importer.import_batch("fixture.zip", (_row(1), _row(2, number="IPX-002")))
    service = SourceSubmissionService(factory, cipher=cipher)
    try:
        yield factory, service
    finally:
        engine.dispose()


def _row(tid: int, *, number: str = "IPX-001") -> dict[str, object]:
    return {
        "tid": tid,
        "number": number,
        "title": f"Title {tid}",
        "publish_date": date(2026, 7, 27),
        "magnet": f"magnet:?xt=urn:btih:fixture-{tid}",
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/thread-fixture.htm",
        "size": 1024,
        "section": "亚洲有码",
        "category": None,
        "website": "sehuatang",
        "create_time": NOW,
        "update_time": NOW,
    }


def _ids(factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    with factory() as session:
        sources = list(
            session.scalars(
                select(ResourceSource).order_by(ResourceSource.external_post_id)
            )
        )
    assert sources[0].movie_id is not None and sources[1].movie_id is not None
    return sources[0].movie_id, sources[0].id, sources[1].movie_id


def test_validates_source_in_callers_transaction_without_returning_magnet(
    context,
) -> None:
    factory, service = context
    movie_id, source_id, _ = _ids(factory)

    with factory.begin() as session:
        result = service.validate_for_play(
            session,
            movie_id=movie_id,
            source_id=source_id,
        )

    assert result.source_id == source_id
    assert result.website == "sehuatang"
    assert result.external_post_id == 1
    assert "magnet" not in repr(result).lower()


def test_decrypts_only_in_explicit_submission_payload_and_hides_repr(context) -> None:
    factory, service = context
    movie_id, source_id, _ = _ids(factory)

    payload = service.load_submission_payload(
        movie_id=movie_id,
        source_id=source_id,
    )

    assert payload.magnet == "magnet:?xt=urn:btih:fixture-1"
    assert payload.magnet not in repr(payload)


def test_loads_non_sensitive_reference_before_and_after_rejection(context) -> None:
    factory, service = context
    movie_id, source_id, _ = _ids(factory)

    active = service.load_submission_ref(movie_id=movie_id, source_id=source_id)
    with factory.begin() as session:
        source = session.get(ResourceSource, source_id)
        assert source is not None
        source.identification_status = "rejected"
        source.magnet_key_id = None
        source.magnet_nonce = None
        source.magnet_ciphertext = None
        session.add(
            SourceRejection(
                id=uuid.uuid4(),
                website=source.website,
                external_post_id=source.external_post_id,
                reason_code="cloud115_source_unavailable",
                rejected_at=NOW,
                last_seen_release_id=None,
            )
        )
    rejected = service.load_submission_ref(movie_id=movie_id, source_id=source_id)

    assert active.rejection_reason_code is None
    assert rejected.rejection_reason_code == "cloud115_source_unavailable"
    assert rejected.source_id == source_id
    assert "magnet" not in repr(rejected).lower()


def test_cross_movie_pending_and_unknown_sources_share_safe_not_found(context) -> None:
    factory, service = context
    movie_id, source_id, other_movie_id = _ids(factory)
    with factory.begin() as session:
        source = session.get(ResourceSource, source_id)
        assert source is not None
        source.identification_status = "pending"
        source.movie_id = None
        source.normalized_number = None

    cases = (
        (other_movie_id, source_id),
        (movie_id, source_id),
        (movie_id, uuid.uuid4()),
    )
    for requested_movie, requested_source in cases:
        with factory.begin() as session:
            with pytest.raises(SourceSubmissionProblem) as error:
                service.validate_for_play(
                    session,
                    movie_id=requested_movie,
                    source_id=requested_source,
                )
        assert (error.value.status_code, error.value.code) == (
            404,
            "resource_not_found",
        )


@pytest.mark.parametrize("rejected", [True, False])
def test_rejected_or_missing_magnet_is_permanently_unavailable(
    context,
    rejected: bool,
) -> None:
    factory, service = context
    movie_id, source_id, _ = _ids(factory)
    with factory.begin() as session:
        source = session.get(ResourceSource, source_id)
        assert source is not None
        source.magnet_key_id = None
        source.magnet_nonce = None
        source.magnet_ciphertext = None
        if rejected:
            source.identification_status = "rejected"

    with factory.begin() as session:
        with pytest.raises(SourceSubmissionProblem) as error:
            service.validate_for_play(
                session,
                movie_id=movie_id,
                source_id=source_id,
            )

    assert (error.value.status_code, error.value.code) == (
        422,
        "source_permanently_unavailable",
    )
