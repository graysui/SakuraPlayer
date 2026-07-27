from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_resource_import_migration_creates_movie_and_source_tables() -> None:
    migration_path = BACKEND_ROOT / "alembic" / "versions" / "0005_resource_import.py"
    source = migration_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert 'revision: str = "0005_resource_import"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "0004_avdb_sync"' in source
    assert 'op.create_table(\n        "movie"' in source
    assert 'op.create_table(\n        "resource_source"' in source
    assert "uq_movie_normalized_number" in source
    assert "uq_resource_source_external" in source
    assert "ck_resource_source_section" in source
    assert "ck_resource_source_identification" in source
    assert "ck_resource_source_rejected_secret" in source
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "downgrade"
        for node in tree.body
    )
