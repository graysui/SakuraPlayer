from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from sakuraplayer.catalog.cache_availability import CacheSourceAvailabilityPort
from sakuraplayer.cloud_cache.capacity import (
    CacheCapacityService,
    CacheCapacityUnavailable,
    active_cache_jobs,
)
from sakuraplayer.cloud_cache.domain.cache_job import CacheJobStatus
from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CachePlayRequest,
    Cloud115Binding,
)
from sakuraplayer.cloud_cache.play_request import (
    CacheProblem,
    PlayRequestService,
)
from sakuraplayer.identity.crypto import InMemorySecretKeyProvider, SecretCipher
from sakuraplayer.identity.models import Base
from sakuraplayer.identity.secrets import EncryptedSettingRepository
from sakuraplayer.resources.models import ResourceSource
from sakuraplayer.resources.source_importer import SourceImporter
from sakuraplayer.resources.source_submission import SourceSubmissionService

NOW = datetime(2026, 7, 27, 12, 30, tzinfo=timezone.utc)


@pytest.fixture
def context(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'cache.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    cipher = SecretCipher(
        InMemorySecretKeyProvider(
            active_key_id="test-v1",
            keys={"test-v1": b"k" * 32},
        )
    )
    secrets = EncryptedSettingRepository(factory, cipher, now=lambda: NOW)
    version = secrets.create_secret("cloud115.cookie", b"UID=fixture").version
    with factory.begin() as session:
        session.add(_binding(version=version))
    SourceImporter(factory, cipher=cipher, now=lambda: NOW).import_batch(
        "fixture.zip",
        tuple(_row(index) for index in range(1, 15)),
    )
    source_port = SourceSubmissionService(factory, cipher=cipher)
    service = PlayRequestService(factory, source_port, now=lambda: NOW)
    capacity = CacheCapacityService(factory, now=lambda: NOW)
    try:
        yield factory, service, capacity
    finally:
        engine.dispose()


def _binding(*, version: int, binding_id: uuid.UUID | None = None):
    return Cloud115Binding(
        id=binding_id or uuid.uuid4(),
        singleton_key=True,
        account_key="account-fixture",
        display_name=None,
        cookie_setting_key="cloud115.cookie",
        login_app="alipaymini",
        cache_root_cid="root-fixture",
        status="active",
        credential_version=version,
        last_verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def _row(index: int) -> dict[str, object]:
    return {
        "tid": index,
        "number": f"IPX-{index:03d}",
        "title": f"Title {index}",
        "publish_date": date(2026, 7, 27),
        "magnet": f"magnet:?xt=urn:btih:fixture-{index}",
        "preview_images": "https://www.sehuatang.net/cover.jpg",
        "detail_url": "https://www.sehuatang.net/thread-fixture.htm",
        "size": 1024,
        "section": "亚洲有码",
        "category": None,
        "website": "sehuatang",
        "create_time": NOW,
        "update_time": NOW,
    }


def _sources(factory) -> list[tuple[uuid.UUID, uuid.UUID]]:
    with factory() as session:
        rows = list(
            session.execute(
                select(ResourceSource.movie_id, ResourceSource.id).order_by(
                    ResourceSource.external_post_id
                )
            )
        )
    assert all(movie_id is not None for movie_id, _ in rows)
    return [(movie_id, source_id) for movie_id, source_id in rows]


def _key(index: int) -> str:
    return f"request-key-{index:04d}"


def test_fixed_two_running_and_ten_queued_then_queue_full(context) -> None:
    factory, service, _ = context
    sources = _sources(factory)

    results = [
        service.create(
            movie_id=movie_id,
            source_id=source_id,
            idempotency_key=_key(index),
        )
        for index, (movie_id, source_id) in enumerate(sources[:12], start=1)
    ]

    assert [result.disposition for result in results[:2]] == ["started", "started"]
    assert [result.job.status for result in results[:2]] == [
        "submitting",
        "submitting",
    ]
    assert all(result.disposition == "queued" for result in results[2:])
    with pytest.raises(CacheProblem) as error:
        movie_id, source_id = sources[12]
        service.create(
            movie_id=movie_id,
            source_id=source_id,
            idempotency_key=_key(13),
        )
    assert (error.value.status_code, error.value.code) == (409, "cache_queue_full")
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(CacheJob.id)).where(
                    CacheJob.capacity_class == "running"
                )
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count(CacheJob.id)).where(
                    CacheJob.capacity_class == "queued"
                )
            )
            == 10
        )


def test_same_source_with_different_keys_reuses_job_and_persists_both_requests(
    context,
) -> None:
    factory, service, _ = context
    movie_id, source_id = _sources(factory)[0]

    first = service.create(
        movie_id=movie_id,
        source_id=source_id,
        idempotency_key=_key(1),
    )
    second = service.create(
        movie_id=movie_id,
        source_id=source_id,
        idempotency_key=_key(2),
    )

    assert second.disposition == "reused"
    assert second.job.id == first.job.id
    with factory() as session:
        assert session.scalar(select(func.count(CacheJob.id))) == 1
        assert session.scalar(select(func.count(CachePlayRequest.idempotency_key))) == 2


def test_key_replay_survives_terminal_state_and_payload_conflict_is_rejected(
    context,
) -> None:
    _, service, capacity = context
    first_source, other_source = _sources(context[0])[:2]
    first = service.create(
        movie_id=first_source[0],
        source_id=first_source[1],
        idempotency_key=_key(1),
    )
    capacity.transition(first.job.id, CacheJobStatus.FAILED)

    replay = service.create(
        movie_id=first_source[0],
        source_id=first_source[1],
        idempotency_key=_key(1),
    )
    assert replay.job.id == first.job.id
    assert replay.job.status == "failed"
    assert replay.disposition == "reused"

    with pytest.raises(CacheProblem) as error:
        service.create(
            movie_id=other_source[0],
            source_id=other_source[1],
            idempotency_key=_key(1),
        )
    assert (error.value.status_code, error.value.code) == (
        409,
        "idempotency_conflict",
    )


def test_cancelling_retains_running_capacity_and_active_binding_guard(context) -> None:
    factory, service, capacity = context
    sources = _sources(factory)
    first = service.create(
        movie_id=sources[0][0],
        source_id=sources[0][1],
        idempotency_key=_key(1),
    )
    service.create(
        movie_id=sources[1][0],
        source_id=sources[1][1],
        idempotency_key=_key(2),
    )
    capacity.transition(first.job.id, CacheJobStatus.CANCELLING)

    queued = service.create(
        movie_id=sources[2][0],
        source_id=sources[2][1],
        idempotency_key=_key(3),
    )

    assert queued.disposition == "queued"
    assert capacity.snapshot().running == 2
    with factory.begin() as session:
        assert active_cache_jobs(session) is True


def test_queued_transition_cannot_oversell_running_capacity(context) -> None:
    _, service, capacity = context
    sources = _sources(context[0])
    results = [
        service.create(
            movie_id=movie_id,
            source_id=source_id,
            idempotency_key=_key(index),
        )
        for index, (movie_id, source_id) in enumerate(sources[:3], start=1)
    ]

    with pytest.raises(CacheCapacityUnavailable):
        capacity.transition(results[2].job.id, CacheJobStatus.SUBMITTING)
    assert capacity.snapshot().running == 2
    assert service.get(results[2].job.id).status == "queued"

    capacity.transition(results[0].job.id, CacheJobStatus.FAILED)
    capacity.transition(results[2].job.id, CacheJobStatus.SUBMITTING)
    assert capacity.snapshot().running == 2


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, (409, "cloud115_binding_required")),
        ("expired", (422, "cloud115_credentials_expired")),
        ("unavailable", (503, "cloud115_unavailable")),
        ("detached", (404, "cloud115_directory_not_found")),
    ],
)
def test_binding_preconditions_are_stable(context, status, expected) -> None:
    factory, service, _ = context
    movie_id, source_id = _sources(factory)[0]
    with factory.begin() as session:
        binding = session.scalar(select(Cloud115Binding))
        assert binding is not None
        if status is None:
            session.delete(binding)
        else:
            binding.status = status

    with pytest.raises(CacheProblem) as error:
        service.create(
            movie_id=movie_id,
            source_id=source_id,
            idempotency_key=_key(1),
        )

    assert (error.value.status_code, error.value.code) == expected


def test_key_validation_uses_frozen_safe_ascii_shape(context) -> None:
    _, service, _ = context
    movie_id, source_id = _sources(context[0])[0]
    for key in ("short", "unsafe key with spaces", "非ascii-key-000000"):
        with pytest.raises(CacheProblem) as error:
            service.create(
                movie_id=movie_id,
                source_id=source_id,
                idempotency_key=key,
            )
        assert (error.value.status_code, error.value.code) == (
            422,
            "validation_failed",
        )


def test_query_cursor_and_catalog_availability_use_persisted_cache_state(
    context,
) -> None:
    factory, service, capacity = context
    sources = _sources(factory)[:3]
    results = [
        service.create(
            movie_id=movie_id,
            source_id=source_id,
            idempotency_key=_key(index),
        )
        for index, (movie_id, source_id) in enumerate(sources, start=1)
    ]

    first_page = service.list(limit=2)
    assert len(first_page.items) == 2
    assert first_page.next_cursor is not None
    second_page = service.list(cursor=first_page.next_cursor, limit=2)
    assert len(second_page.items) == 1
    assert {item.id for item in first_page.items + second_page.items} == {
        result.job.id for result in results
    }
    assert service.get(results[0].job.id).source_id == sources[0][1]

    availability = CacheSourceAvailabilityPort(factory)
    initial = availability.get_many(tuple(source_id for _, source_id in sources))
    assert [initial[source_id].state for _, source_id in sources] == [
        "running",
        "running",
        "queued",
    ]
    capacity.transition(results[0].job.id, CacheJobStatus.FAILED)
    with factory.begin() as session:
        rejected = session.get(ResourceSource, sources[1][1])
        assert rejected is not None
        rejected.identification_status = "rejected"
        rejected.magnet_key_id = None
        rejected.magnet_nonce = None
        rejected.magnet_ciphertext = None
    updated = availability.get_many(tuple(source_id for _, source_id in sources))
    assert updated[sources[0][1]].state == "failed"
    assert updated[sources[1][1]].state == "rejected"

    replacement = service.create(
        movie_id=sources[0][0],
        source_id=sources[0][1],
        idempotency_key=_key(4),
    )
    assert replacement.job.id != results[0].job.id
    assert availability.get_many((sources[0][1],))[sources[0][1]].state == "running"
