from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_avdb_sync_migration_is_linear_and_creates_sync_tables() -> None:
    path = BACKEND_ROOT / "alembic" / "versions" / "0004_avdb_sync.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    tables = [
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
        and node.func.attr == "create_table"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    ]

    assert 'revision: str = "0004_avdb_sync"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "0003_encrypted_settings"' in source
    assert tables == ["avdb_sync_request", "avdb_sync_run", "avdb_asset"]
    assert "uq_avdb_sync_request_slot" in source
    assert "uq_avdb_sync_run_release" in source
    assert "ck_avdb_sync_run_state" in source
    assert "ck_avdb_asset_digest" in source


def test_alembic_metadata_registers_resource_models() -> None:
    source = (BACKEND_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")

    assert "from sakuraplayer.resources import models as resource_models" in source
    assert "target_metadata = resource_models.Base.metadata" in source
