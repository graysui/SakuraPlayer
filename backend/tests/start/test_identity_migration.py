from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_identity_migration_is_linear_and_creates_only_identity_tables() -> None:
    migration_path = BACKEND_ROOT / "alembic" / "versions" / "0002_identity.py"
    source = migration_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    create_tables = [
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

    assert 'revision: str = "0002_identity"' in source
    assert (
        'down_revision: Union[str, Sequence[str], None] = "0001_initial_skeleton"'
        in source
    )
    assert create_tables == ["admin_user", "refresh_session"]
    assert "bootstrap" not in source.lower()
    assert "ck_admin_user_singleton_key" in source
    assert "ck_refresh_session_token_hash_length" in source
    assert "uq_refresh_session_active_client" in source
