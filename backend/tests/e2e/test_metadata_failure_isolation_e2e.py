from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from conftest import (
    NOW,
    E2eContext,
    app_settings,
    fake_metadata_client,
)
from sqlalchemy import func, select

from sakuraplayer.catalog.models import MetadataJob, MetadataStage
from sakuraplayer.catalog.providers.runtime import build_metadata_stage_executor
from sakuraplayer.discovery.models import RankingEntry, RankingSnapshot
from sakuraplayer.resources.models import Movie, ResourceSource
from sakuraplayer.worker.metadata_child import MetadataChildRunner

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "ac_evidence",
    [pytest.param(None, id="AC-058-AC-132")],
)
def test_optional_provider_failures_preserve_catalog_and_ranking(
    e2e_context: E2eContext,
    tmp_path: Path,
    ac_evidence: None,
) -> None:
    del ac_evidence
    movie = _persist_movie_with_source(e2e_context, "ABP-123", 2001)
    outcome = e2e_context.queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=date(2026, 7, 27),
        reason="initial",
    )
    claim = e2e_context.queue.claim_next(
        "task014-failure-worker",
        lease_duration=timedelta(seconds=30),
    )
    assert claim is not None
    http_client = fake_metadata_client(fail_optional=True)
    try:
        executor = build_metadata_stage_executor(
            settings=app_settings(e2e_context.database_url),
            session_factory=e2e_context.factory,
            http_client=http_client,
            image_root=tmp_path / "catalog-images",
            now=lambda: NOW,
        )
        result = MetadataChildRunner(
            queue=e2e_context.queue,
            executor=executor,
        ).run(claim)
    finally:
        http_client.close()
    assert result == "completed_with_warnings"

    with e2e_context.factory.begin() as session:
        snapshot = RankingSnapshot(
            id=uuid.uuid4(),
            board="daily",
            year=None,
            status="current",
            source_synced_at=NOW,
            created_at=NOW,
        )
        session.add(snapshot)
        session.flush()
        session.add(
            RankingEntry(
                snapshot_id=snapshot.id,
                rank=1,
                normalized_number=movie.normalized_number,
                movie_id=movie.id,
            )
        )

    headers = e2e_context.auth_headers()
    catalog = e2e_context.client.get("/api/v1/movies", headers=headers)
    ranking = e2e_context.client.get(
        "/api/v1/rankings",
        params={"board": "daily"},
        headers=headers,
    )
    assert catalog.status_code == ranking.status_code == 200
    assert catalog.json()["items"][0]["number"] == "ABP-123"
    assert ranking.json()["items"][0]["movie"]["number"] == "ABP-123"
    with e2e_context.factory() as session:
        persisted = session.get(Movie, movie.id)
        job = session.get(MetadataJob, outcome.job_id)
        warnings = list(
            session.scalars(
                select(MetadataStage).where(
                    MetadataStage.job_id == outcome.job_id,
                    MetadataStage.status == "warning",
                )
            )
        )
        assert persisted is not None and persisted.catalog_state == "core_ready"
        assert job is not None and job.status == "completed_with_warnings"
        assert warnings


@pytest.mark.parametrize("ac_evidence", [pytest.param(None, id="AC-132-timeout-retry")])
def test_persisted_timeout_requires_independent_manual_retry(
    e2e_context: E2eContext,
    ac_evidence: None,
) -> None:
    del ac_evidence
    movie = _persist_movie_with_source(e2e_context, "TIMEOUT-014", 2014)
    queued = e2e_context.queue.enqueue(
        movie_id=movie.id,
        normalized_number=movie.normalized_number,
        sort_date=None,
        reason="manual_or_search",
    )
    claim = e2e_context.queue.claim_next(
        "task014-timeout-worker",
        lease_duration=timedelta(seconds=30),
    )
    assert claim is not None
    e2e_context.queue.start_stage(claim, "javdb_core")
    e2e_context.queue.fail_after_termination(
        claim,
        code="metadata_timeout",
        detail="metadata_timeout",
    )
    with e2e_context.factory() as session:
        assert session.scalar(select(func.count(MetadataJob.id))) == 1

    headers = e2e_context.auth_headers()
    response = e2e_context.client.post(
        f"/api/v1/admin/metadata-jobs/{queued.job_id}/retry",
        headers=headers,
    )
    assert response.status_code == 201
    retry = response.json()
    assert retry["parent_job_id"] == str(queued.job_id)
    assert retry["attempt_no"] == 2
    assert retry["status"] == "queued"

    with e2e_context.factory() as session:
        parent = session.get(MetadataJob, queued.job_id)
        attempts = list(
            session.scalars(
                select(MetadataJob)
                .where(MetadataJob.normalized_number == movie.normalized_number)
                .order_by(MetadataJob.attempt_no)
            )
        )
        assert parent is not None
        assert parent.status == "failed"
        assert parent.failure_code == "metadata_timeout"
        assert [attempt.attempt_no for attempt in attempts] == [1, 2]
        assert attempts[1].parent_job_id == parent.id


def _persist_movie_with_source(
    context: E2eContext,
    number: str,
    external_post_id: int,
) -> Movie:
    movie = Movie(
        id=uuid.uuid4(),
        normalized_number=number,
        raw_numbers=[number],
        catalog_state="raw_only",
        created_at=NOW,
        updated_at=NOW,
    )
    source = ResourceSource(
        id=uuid.uuid4(),
        website="sehuatang",
        external_post_id=external_post_id,
        movie_id=movie.id,
        raw_number=number,
        normalized_number=number,
        title=f"Fixture {number}",
        publish_date=date(2026, 7, 27),
        section="亚洲有码",
        category=None,
        resource_size_mb=1024,
        detail_url="https://www.sehuatang.net/fixture.htm",
        preview_urls=[],
        identification_status="identified",
        imported_at=NOW,
    )
    with context.factory.begin() as session:
        session.add_all((movie, source))
    return movie
