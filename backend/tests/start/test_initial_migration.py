from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_initial_migration_is_an_empty_business_baseline() -> None:
    migration_path = BACKEND_ROOT / "alembic" / "versions" / "0001_initial_skeleton.py"
    source = migration_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    operation_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "op"
    ]

    assert operation_calls == []
    assert 'revision: str = "0001_initial_skeleton"' in source
