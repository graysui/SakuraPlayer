from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import uuid

import pytest
from sqlalchemy import func, select

from sakuraplayer.catalog.metadata_seeder import MetadataQueueSeeder
from sakuraplayer.catalog.models import MetadataJob
from sakuraplayer.catalog.providers.runtime import build_metadata_stage_executor
from sakuraplayer.discovery.models import RankingEntry, RankingSnapshot
from sakuraplayer.resources.initial_scope import InitialScopeSelector
from sakuraplayer.resources.models import Movie, ResourceSource
from sakuraplayer.worker.metadata_child import MetadataChildRunner

from conftest import (
    NOW,
    E2eContext,
    app_settings,
    fake_metadata_client,
    fetched_release,
)


pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "ac_evidence",
    [pytest.param(None, id="AC-001-AC-010-AC-018-AC-078-AC-115-AC-134")],
)
def test_phase1_catalog_metadata_chain(
    e2e_context: E2eContext,
    tmp_path: Path,
    ac_evidence: None,
) -> None:
    del ac_evidence
    client = e2e_context.client
    assert e2e_context.database_url not in repr(e2e_context)
    credentials = {
        "username": "admin",
        "password": "correct horse battery staple",
        "client_instance_id": str(uuid.uuid4()),
    }
    assert client.post("/api/v1/auth/bootstrap", json=credentials).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/bootstrap",
            headers={"X-Bootstrap-Token": "wrong-token"},
            json=credentials,
        ).status_code
        == 401
    )
    headers = e2e_context.auth_headers()
    repeated = client.post("/api/v1/auth/bootstrap")
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "bootstrap_already_completed"

    outcome = e2e_context.sync_service.sync(
        fetched_release(tmp_path, "main-chain"),
        importer=e2e_context.source_importer.import_batch,
    )
    assert outcome.status == "completed" and outcome.idempotent is False
    seeded = MetadataQueueSeeder(
        e2e_context.factory,
        queue=e2e_context.queue,
        selector=InitialScopeSelector(e2e_context.factory),
        now=lambda: NOW,
    ).seed_once()
    assert seeded.initial == 6

    claim = e2e_context.queue.claim_next(
        "task014-worker",
        lease_duration=timedelta(seconds=30),
    )
    assert claim is not None and claim.normalized_number == "ABP-123"
    http_client = fake_metadata_client(fail_optional=False)
    try:
        executor = build_metadata_stage_executor(
            settings=app_settings(e2e_context.database_url),
            session_factory=e2e_context.factory,
            http_client=http_client,
            image_root=tmp_path / "catalog-images",
            now=lambda: NOW,
        )
        assert MetadataChildRunner(
            queue=e2e_context.queue,
            executor=executor,
        ).run(claim) in {"completed", "completed_with_warnings"}
    finally:
        http_client.close()

    with e2e_context.factory.begin() as session:
        movie = session.scalar(
            select(Movie).where(Movie.normalized_number == "ABP-123")
        )
        assert movie is not None and movie.catalog_state == "core_ready"
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

    movies = client.get("/api/v1/movies", headers=headers)
    search = client.get(
        "/api/v1/search",
        params={"q": "ABP-123"},
        headers=headers,
    )
    ranking = client.get(
        "/api/v1/rankings",
        params={"board": "daily"},
        headers=headers,
    )
    events = client.get("/api/v1/events/snapshot", headers=headers)
    settings = client.get("/api/v1/settings", headers=headers)
    diagnostics = client.get("/api/v1/admin/diagnostics", headers=headers)

    assert movies.status_code == search.status_code == ranking.status_code == 200
    assert movies.json()["items"][0]["number"] == "ABP-123"
    assert search.json()["movies"][0]["number"] == "ABP-123"
    assert ranking.json()["items"][0]["movie"]["number"] == "ABP-123"
    assert events.status_code == 200 and events.json()["snapshot_version"] >= 7
    assert settings.status_code == 200
    assert settings.json()["avdb_sync"]["incremental_30d"]["status"] == "succeeded"
    assert diagnostics.status_code == 200
    components = {item["component"]: item for item in diagnostics.json()["components"]}
    assert components["api"]["status"] == "healthy"
    assert components["postgres"]["status"] == "healthy"
    assert components["avdb"]["status"] == "healthy"

    combined_response = "".join(
        response.text for response in (movies, search, ranking, events, settings, diagnostics)
    )
    assert "urn:e2e-resource" not in combined_response
    with e2e_context.factory() as session:
        assert session.scalar(select(func.count(Movie.id))) == 6
        assert session.scalar(select(func.count(ResourceSource.id))) == 6
        assert session.scalar(select(func.count(MetadataJob.id))) == 6
        assert set(session.scalars(select(ResourceSource.section))) == {
            "亚洲有码",
            "亚洲无码",
            "中文字幕",
            "4K原版",
            "素人有码",
            "FC2",
        }
