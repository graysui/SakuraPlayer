from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_secret_migration_is_linear_and_enforces_envelope_invariants() -> None:
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0003_encrypted_settings.py"
    )
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

    assert 'revision: str = "0003_encrypted_settings"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "0002_identity"' in source
    assert create_tables == ["encrypted_setting"]
    assert "ck_encrypted_setting_value_shape" in source
    assert "ck_encrypted_setting_nonce_length" in source
    assert "ck_encrypted_setting_ciphertext_length" in source
    assert "ck_encrypted_setting_version" in source
