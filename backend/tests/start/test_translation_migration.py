from pathlib import Path

from sakuraplayer.catalog import models as catalog_models
from sakuraplayer.identity.models import Base


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_translation_model_is_registered() -> None:
    assert catalog_models.TranslationRecord.__tablename__ == "translation_record"
    assert "translation_record" in Base.metadata.tables


def test_translation_migration_creates_paid_dispatch_facts() -> None:
    migration = BACKEND_ROOT / "alembic" / "versions" / "0010_translation.py"

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")
    assert 'revision: str = "0010_translation"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = '
        '"0009_provider_snapshots"' in source
    )
    assert '"translation_record"' in source
    assert '"bio_zh_source"' in source
    for guard in (
        "ck_translation_record_owner_type",
        "ck_translation_record_source_hash",
        "ck_translation_record_status",
        "ck_translation_record_state",
        "uq_translation_record_business_key",
        "trg_translation_record_dispatch_immutable",
        "ck_actor_bio_zh_source",
    ):
        assert guard in source
    assert 'op.drop_table("translation_record")' in source
    assert 'op.drop_column("actor", "bio_zh_source")' in source
    assert "translation business key is immutable" in source
    assert "dispatched translation is immutable while in flight" in source


def test_translation_model_exposes_dispatch_columns() -> None:
    columns = Base.metadata.tables["translation_record"].columns

    assert {
        "owner_type",
        "owner_id",
        "source_text",
        "source_hash",
        "translated_text",
        "model",
        "prompt_version",
        "status",
        "claim_token",
        "claim_expires_at",
        "dispatch_started_at",
        "failure_code",
        "created_at",
        "updated_at",
    } == set(columns.keys()) - {"id"}
