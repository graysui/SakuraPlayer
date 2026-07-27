from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_metadata_queue_migration_owns_persistent_jobs_and_stages() -> None:
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "0007_metadata_queue.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0007_metadata_queue"' in source
    assert (
        "down_revision: Union[str, Sequence[str], None] = "
        '"0006_movie_source_management"'
    ) in source
    assert '"metadata_job"' in source
    assert '"metadata_stage"' in source
    assert '"metadata_queue_state"' in source
    assert '"sort_date"' in source
    assert '"claim_expires_at"' in source
    assert '"uq_metadata_job_active_number"' in source
    assert "status IN ('queued', 'running')" in source
    assert '"ix_metadata_job_claim"' in source
    assert "sort_date DESC NULLS LAST" in source


def test_metadata_queue_migration_has_retry_and_state_guards() -> None:
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "0007_metadata_queue.py"
    ).read_text(encoding="utf-8")

    assert "ck_metadata_job_priority_reason" in source
    assert "ck_metadata_job_retry_shape" in source
    assert "ck_metadata_job_state" in source
    assert "ck_metadata_stage_state" in source
    assert "trg_metadata_job_terminal_immutable" in source
    assert "trg_metadata_stage_terminal_immutable" in source
    assert "parent_job_id" in source
    assert "requested_stages" in source
    assert 'op.drop_table("metadata_stage")' in source
    assert 'op.drop_table("metadata_job")' in source
