from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import CheckConstraint

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog import models as catalog_models
from sakuraplayer.catalog.metadata_state import (
    ALL_STAGES,
    OPTIONAL_STAGES,
    PRIORITY_BY_REASON,
)
from sakuraplayer.discovery import models as discovery_models
from sakuraplayer.events import models as event_models
from sakuraplayer.identity import models as identity_models
from sakuraplayer.identity.models import Base
from sakuraplayer.resources import models as resource_models

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent
TASK_RANGE = "41d8df6^..66e5b2c"
_MODEL_MODULES = (
    catalog_models,
    discovery_models,
    event_models,
    identity_models,
    resource_models,
)


def cleanup_manifest() -> list[str]:
    paths = [BACKEND_ROOT / "alembic" / "env.py"]
    paths.extend((BACKEND_ROOT / "src").rglob("*.py"))
    paths.extend((BACKEND_ROOT / "tests").rglob("*.py"))
    return sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in paths
        if "tests/quality" not in path.relative_to(BACKEND_ROOT).as_posix()
    )


def capture_baseline() -> dict[str, Any]:
    return {
        "migrations": _migration_signature(),
        "openapi": _openapi_signature(),
        "state_machines": _state_machine_signature(),
    }


def compare_baselines(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return [
        key
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    ]


def _migration_signature() -> dict[str, str]:
    versions = BACKEND_ROOT / "alembic" / "versions"
    return {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in sorted(versions.glob("*.py"))
    }


def _openapi_signature() -> dict[str, Any]:
    class InterfaceService:
        def __getattr__(self, name: str) -> Any:
            def unavailable(*args: Any, **kwargs: Any) -> None:
                raise AssertionError(f"interface placeholder invoked: {name}")

            return unavailable

    service = InterfaceService()
    app = create_app(
        readiness_probe=lambda: True,
        identity_service=service,
        identification_service=service,
        movie_source_admin_service=service,
        metadata_admin_service=service,
        catalog_query_service=service,
        search_service=service,
        favorite_service=service,
        ranking_query_service=service,
        event_snapshot_service=service,
        event_log=service,
        settings_service=service,
        diagnostics_service=service,
    )
    return app.openapi()


def _state_machine_signature() -> dict[str, Any]:
    if not _MODEL_MODULES:
        raise AssertionError("model modules were not loaded")
    constraints = []
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        for constraint in sorted(
            (item for item in table.constraints if isinstance(item, CheckConstraint)),
            key=lambda item: item.name or "",
        ):
            constraints.append(
                {
                    "name": constraint.name,
                    "sql": str(constraint.sqltext),
                    "table": table.name,
                }
            )
    return {
        "metadata_stages": list(ALL_STAGES),
        "optional_metadata_stages": list(OPTIONAL_STAGES),
        "priority_by_reason": dict(sorted(PRIORITY_BY_REASON.items())),
        "sql_check_constraints": constraints,
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"baseline must be a JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("manifest")
    capture = subparsers.add_parser("capture")
    capture.add_argument("output", type=Path)
    compare = subparsers.add_parser("compare")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    args = parser.parse_args()

    if args.command == "manifest":
        print("\n".join(cleanup_manifest()))
        return 0
    if args.command == "capture":
        args.output.write_text(
            json.dumps(capture_baseline(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return 0

    differences = compare_baselines(_read_json(args.before), _read_json(args.after))
    if differences:
        print("baseline differences: " + ", ".join(differences))
        return 1
    print("cleanup baselines are equivalent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
