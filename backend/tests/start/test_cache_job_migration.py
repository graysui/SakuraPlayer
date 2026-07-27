from pathlib import Path

from sakuraplayer.cloud_cache.models import CacheJob, CachePlayRequest
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
