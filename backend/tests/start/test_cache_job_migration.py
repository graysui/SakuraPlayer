from pathlib import Path

from sakuraplayer.cloud_cache.models import (
    CacheJob,
    CacheJobMediaSelection,
    CachePlayRequest,
    RemoteMedia,
    RemoteSubtitle,
)
from sakuraplayer.identity.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_cache_job_models_are_registered_with_exact_task_103_shape() -> None:
    assert CacheJob.__tablename__ == "cache_job"
    assert CachePlayRequest.__tablename__ == "cache_play_request"
    assert CacheJob.metadata is CachePlayRequest.metadata is Base.metadata
    assert set(Base.metadata.tables["cache_job"].columns.keys()) == {
        "id",
        "movie_id",
        "source_id",
        "binding_id",
        "status",
        "capacity_class",
        "account_key",
        "cache_root_cid",
        "task_dir_cid",
        "task_dir_name",
        "remote_info_hash",
        "submit_started_at",
        "remote_percent",
        "ready_at",
        "last_accessed_at",
        "expires_at",
        "claim_owner",
        "claim_token",
        "claim_expires_at",
        "failure_code",
        "failure_detail",
        "created_at",
        "updated_at",
    }
    assert set(Base.metadata.tables["cache_play_request"].columns.keys()) == {
        "idempotency_key",
        "movie_id",
        "source_id",
        "cache_job_id",
        "created_at",
    }


def test_task_103_migration_is_linear_and_owns_only_job_and_request_schema() -> None:
    path = BACKEND_ROOT / "alembic" / "versions" / "0015_cache_jobs.py"
    source = path.read_text(encoding="utf-8")
    assert 'revision: str = "0015_cache_jobs"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0014_cloud115_binding"'
    ) in source
    for expected in (
        '"cache_job"',
        '"cache_play_request"',
        "ck_cache_job_state_capacity",
        "uq_cache_job_active_source_binding",
        "uq_cache_job_task_dir_cid",
        "fk_cache_job_binding_id_cloud115_binding",
        'ondelete="SET NULL"',
        "ck_cache_play_request_idempotency_key",
    ):
        assert expected in source
    for deferred in (
        '"remote_media"',
        '"remote_subtitle"',
        '"cache_job_media_selection"',
    ):
        assert deferred not in source


def test_task_104_migration_adds_dispatch_and_claim_fencing_shape() -> None:
    path = BACKEND_ROOT / "alembic" / "versions" / "0016_cache_offline.py"
    source = path.read_text(encoding="utf-8")
    assert 'revision: str = "0016_cache_offline"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0015_cache_jobs"' in source
    )
    for expected in (
        '"submit_started_at"',
        "submit_uncertain",
        "ck_cache_job_claim_shape",
        "ck_cache_job_submission_shape",
        "cloud115_submit_uncertain",
    ):
        assert expected in source


def test_task_105_models_and_migration_own_media_resolution_schema() -> None:
    tables = Base.metadata.tables
    assert RemoteMedia.__tablename__ == "remote_media"
    assert RemoteSubtitle.__tablename__ == "remote_subtitle"
    assert CacheJobMediaSelection.__tablename__ == "cache_job_media_selection"
    assert set(tables["remote_media"].columns.keys()) == {
        "id",
        "cache_job_id",
        "file_id",
        "pickcode",
        "parent_cid",
        "name",
        "size_bytes",
        "duration_seconds",
        "candidate_id",
        "sequence_no",
        "selection_score",
        "selection_evidence",
        "is_valid",
        "created_at",
    }
    assert set(tables["remote_subtitle"].columns.keys()) == {
        "id",
        "cache_job_id",
        "media_id",
        "file_id",
        "pickcode",
        "parent_cid",
        "name",
        "extension",
        "size_bytes",
        "match_score",
        "match_evidence",
        "created_at",
    }
    assert set(tables["cache_job_media_selection"].columns.keys()) == {
        "cache_job_id",
        "sequence_no",
        "media_id",
    }

    path = BACKEND_ROOT / "alembic" / "versions" / "0017_cache_media.py"
    source = path.read_text(encoding="utf-8")
    assert 'revision: str = "0017_cache_media"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0016_cache_offline"'
        in source
    )
    for expected in (
        '"remote_media"',
        '"remote_subtitle"',
        '"cache_job_media_selection"',
        "candidate_id",
        "selection_evidence",
        "fk_remote_subtitle_owned_media",
        "fk_cache_selection_owned_media",
        "trg_cache_job_ready_selection",
    ):
        assert expected in source
