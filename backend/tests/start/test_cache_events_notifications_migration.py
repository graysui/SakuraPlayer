from pathlib import Path

from sakuraplayer.cloud_cache.models import CacheJob, Notification
from sakuraplayer.identity.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_task_112_models_register_notification_and_recovery_fields() -> None:
    assert Notification.__tablename__ == "notification"
    assert Notification.metadata is CacheJob.metadata is Base.metadata
    assert set(Base.metadata.tables["notification"].columns.keys()) == {
        "id",
        "type",
        "resource_id",
        "error_code",
        "dedupe_key",
        "created_at",
        "read_at",
    }
    cache_columns = Base.metadata.tables["cache_job"].columns
    assert "cleanup_reason" in cache_columns
    assert "failure_stage" in cache_columns


def test_task_112_migration_is_linear_and_owns_notification_schema() -> None:
    path = BACKEND_ROOT / "alembic" / "versions" / "0020_cache_events_notifications.py"
    source = path.read_text(encoding="utf-8")

    assert 'revision: str = "0020_cache_events_notifications"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0019_playback_progress"'
        in source
    )
    for expected in (
        '"notification"',
        '"cleanup_reason"',
        '"failure_stage"',
        "uq_notification_dedupe_key",
        "ix_notification_unread",
    ):
        assert expected in source
