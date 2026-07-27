from pathlib import Path

from sakuraplayer.discovery import models as discovery_models
from sakuraplayer.identity.models import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_catalog_discovery_model_is_registered() -> None:
    assert discovery_models.Favorite.__tablename__ == "favorite"
    assert "favorite" in Base.metadata.tables


def test_catalog_discovery_migration_owns_search_and_favorite_schema() -> None:
    migration = BACKEND_ROOT / "alembic" / "versions" / "0011_catalog_discovery.py"

    assert migration.exists()
    source = migration.read_text(encoding="utf-8")
    assert 'revision: str = "0011_catalog_discovery"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0010_translation"' in source
    )
    for expected in (
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        '"favorite"',
        "uq_favorite_target",
        "ix_movie_title_original_trgm",
        "ix_movie_title_zh_trgm",
        "ix_actor_name_ja_trgm",
        "ix_actor_name_zh_trgm",
        "ix_actor_alias_normalized_trgm",
    ):
        assert expected in source
    assert 'op.drop_table("favorite")' in source
    assert "DROP EXTENSION" not in source


def test_favorite_model_has_single_collection_shape() -> None:
    columns = Base.metadata.tables["favorite"].columns

    assert set(columns.keys()) == {"id", "target_type", "target_id", "created_at"}
