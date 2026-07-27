from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from sakuraplayer.resources.models import (
    AvdbSyncRun,
    Movie,
    ResourceSource,
    SourceRejection,
)

from conftest import E2eContext, fetched_release


pytestmark = pytest.mark.integration


@pytest.mark.parametrize("ac_evidence", [pytest.param(None, id="AC-023")])
def test_release_source_and_rejection_are_idempotent(
    e2e_context: E2eContext,
    tmp_path: Path,
    ac_evidence: None,
) -> None:
    del ac_evidence
    first_release = fetched_release(tmp_path, "release-one")
    first = e2e_context.sync_service.sync(
        first_release,
        importer=e2e_context.source_importer.import_batch,
    )
    repeated = e2e_context.sync_service.sync(
        first_release,
        importer=e2e_context.source_importer.import_batch,
    )
    second = e2e_context.sync_service.sync(
        fetched_release(tmp_path, "release-two"),
        importer=e2e_context.source_importer.import_batch,
    )

    assert first.idempotent is False
    assert repeated.idempotent is True and repeated.run_id == first.run_id
    assert second.idempotent is False
    with e2e_context.factory() as session:
        assert session.scalar(select(func.count(AvdbSyncRun.id))) == 2
        assert session.scalar(select(func.count(Movie.id))) == 6
        assert session.scalar(select(func.count(ResourceSource.id))) == 6

    e2e_context.rejection_service.reject(
        website="sehuatang",
        external_post_id=1001,
        reason_code="fixture_rejected",
    )
    third = e2e_context.sync_service.sync(
        fetched_release(tmp_path, "release-three"),
        importer=e2e_context.source_importer.import_batch,
    )
    assert third.status == "completed"

    with e2e_context.factory() as session:
        rejected = session.scalar(
            select(ResourceSource).where(ResourceSource.external_post_id == 1001)
        )
        tombstone = session.scalar(
            select(SourceRejection).where(SourceRejection.external_post_id == 1001)
        )
        assert rejected is not None
        assert rejected.identification_status == "rejected"
        assert rejected.magnet_ciphertext is None
        assert tombstone is not None
        assert session.scalar(select(func.count(ResourceSource.id))) == 6
