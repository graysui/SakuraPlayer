from pathlib import Path

from sakuraplayer.catalog.models import MetadataWorkerControl
from sakuraplayer.identity.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_metadata_worker_control_model_is_a_separate_singleton() -> None:
    assert MetadataWorkerControl.__tablename__ == "metadata_worker_control"
    assert MetadataWorkerControl.metadata is Base.metadata
    assert set(Base.metadata.tables["metadata_worker_control"].columns.keys()) == {
        "singleton_key",
        "paused",
        "updated_at",
    }


def test_metadata_worker_control_migration_is_linear_and_reversible() -> None:
    path = BACKEND_ROOT / "alembic" / "versions" / "0021_metadata_worker_control.py"
    source = path.read_text(encoding="utf-8")

    assert 'revision: str = "0021_metadata_worker_control"' in source
    assert (
        "down_revision: Union[str, Sequence[str], None] = "
        '"0020_cache_events_notifications"'
    ) in source
    assert "op.create_table(" in source
    assert '"metadata_worker_control"' in source
    assert "ck_metadata_worker_control_singleton" in source
    assert 'op.drop_table("metadata_worker_control")' in source
