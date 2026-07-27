from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_catalog_metadata_migration_extends_movie_and_creates_relations() -> None:
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "0008_catalog_metadata.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0008_catalog_metadata"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0007_metadata_queue"'
        in source
    )
    for column in (
        "javdb_id",
        "title_original",
        "release_date",
        "maker",
        "series",
        "director",
        "description_original",
        "score",
        "metadata_updated_at",
    ):
        assert f'"{column}"' in source
    for table in (
        "actor",
        "actor_alias",
        "movie_actor",
        "tag",
        "movie_tag",
        "catalog_image",
    ):
        assert f'"{table}"' in source


def test_catalog_metadata_migration_has_image_and_identity_guards() -> None:
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "0008_catalog_metadata.py"
    ).read_text(encoding="utf-8")

    for guard in (
        "uq_movie_javdb_id",
        "uq_actor_javdb_id",
        "ck_actor_gender",
        "ck_actor_alias_authority",
        "ck_catalog_image_owner_type",
        "ck_catalog_image_kind",
        "ck_catalog_image_cover_position",
        "ck_catalog_image_status",
        "ck_catalog_image_ready_shape",
        "ck_catalog_image_relative_path",
        "ck_catalog_image_sha256",
        "ck_catalog_image_sha256_format",
        "uq_catalog_image_owner_kind_position",
    ):
        assert guard in source
    assert 'op.drop_table("catalog_image")' in source
    assert 'op.drop_column("movie", "javdb_id")' in source
