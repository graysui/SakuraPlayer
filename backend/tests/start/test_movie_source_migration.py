from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_movie_source_migration_creates_labels_and_rejections() -> None:
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "0006_movie_source_management.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0006_movie_source_management"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "0005_resource_import"' in source
    assert '"resource_source_label"' in source
    assert '"source_rejection"' in source
    assert "uq_source_rejection_external" in source
    assert "ck_source_rejection_reason_code" in source
