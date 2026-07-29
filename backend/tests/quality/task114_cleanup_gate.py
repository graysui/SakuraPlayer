from __future__ import annotations

import argparse
import ast
import inspect
import json
import re
from dataclasses import fields, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import CheckConstraint

from sakuraplayer.api.app import create_app
from sakuraplayer.catalog import models as catalog_models
from sakuraplayer.cloud_cache import models as cloud_cache_models
from sakuraplayer.cloud_cache.domain import cache_job as cache_job_domain
from sakuraplayer.cloud_cache.ports import cloud115 as cloud115_port
from sakuraplayer.discovery import models as discovery_models
from sakuraplayer.events import models as event_models
from sakuraplayer.identity import models as identity_models
from sakuraplayer.identity.models import Base
from sakuraplayer.playback import models as playback_models
from sakuraplayer.resources import models as resource_models

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent
TASK_RANGE = "eb280ab^..baf218b"
MANIFEST_FILE = Path(__file__).with_name("task114_cleanup_manifest.txt")
MYPY_FILE = Path(__file__).with_name("task114_mypy_files.txt")
_STABLE_CODE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_MODEL_MODULES = (
    catalog_models,
    cloud_cache_models,
    discovery_models,
    event_models,
    identity_models,
    playback_models,
    resource_models,
)
_SERVICE_NAMES = (
    "identity_service",
    "identification_service",
    "movie_source_admin_service",
    "metadata_admin_service",
    "catalog_query_service",
    "search_service",
    "favorite_service",
    "ranking_query_service",
    "event_snapshot_service",
    "event_log",
    "settings_service",
    "diagnostics_service",
    "cloud115_binding_service",
    "cloud115_qr_service",
    "cache_service",
    "cache_cleanup_service",
    "cache_cancellation_service",
    "notification_service",
    "playback_session_service",
    "playback_stream_resolver",
    "subtitle_download_service",
    "playback_progress_service",
    "playback_heartbeat_service",
)
_GUARD_FILES = (
    ".dockerignore",
    "backend/pyproject.toml",
    "backend/src/sakuraplayer/cloud_cache/infrastructure/cloud115/NOTICE.md",
    "backend/tests/real115/README.md",
    "backend/tests/real115/conftest.py",
    "backend/tests/real115/test_protocol_smoke.py",
    "backend/tests/unit/cloud115/test_protocol_fixtures.py",
)


def cleanup_manifest() -> list[str]:
    return _read_lines(MANIFEST_FILE)


def mypy_files() -> list[str]:
    return _read_lines(MYPY_FILE)


def capture_baseline() -> dict[str, Any]:
    return {
        "cloud115_interface": _cloud115_interface_signature(),
        "guard_files": _file_digests(_GUARD_FILES),
        "manifest": cleanup_manifest(),
        "migrations": _migration_signature(),
        "module_constants": _module_constant_signature(),
        "openapi": _openapi_signature(),
        "stable_error_codes": _stable_error_codes(),
        "state_machines": _state_machine_signature(),
    }


def compare_baselines(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return [
        key
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    ]


def _read_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


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
    services = {name: service for name in _SERVICE_NAMES}
    app = create_app(readiness_probe=lambda: True, **services)  # type: ignore[arg-type]
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
    transitions = {
        source.value: sorted(target.value for target in targets)
        for source, targets in sorted(
            cache_job_domain._LEGAL_TRANSITIONS.items(),
            key=lambda item: item[0].value,
        )
    }
    capacity = {
        status.value: value.value
        for status, value in sorted(
            cache_job_domain._CAPACITY_BY_STATUS.items(),
            key=lambda item: item[0].value,
        )
    }
    return {
        "cache_capacity_by_status": capacity,
        "cache_statuses": [item.value for item in cache_job_domain.CacheJobStatus],
        "cache_transitions": transitions,
        "sql_check_constraints": constraints,
    }


def _cloud115_interface_signature() -> dict[str, Any]:
    methods = {
        name: str(inspect.signature(member))
        for name, member in inspect.getmembers(
            cloud115_port.Cloud115Port, inspect.isfunction
        )
        if not name.startswith("_")
    }
    values: dict[str, Any] = {}
    for name in cloud115_port.__all__:
        member = getattr(cloud115_port, name)
        if isinstance(member, type) and issubclass(member, Enum):
            values[name] = [item.value for item in member]
        elif isinstance(member, type) and is_dataclass(member):
            values[name] = [
                {"name": field.name, "type": str(field.type)}
                for field in fields(member)
            ]
    return {"methods": methods, "values": values}


def _module_constant_signature() -> dict[str, dict[str, str]]:
    signature: dict[str, dict[str, str]] = {}
    for relative in cleanup_manifest():
        if not relative.startswith("backend/src/"):
            continue
        path = REPOSITORY_ROOT / relative
        constants: dict[str, str] = {}
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id.lstrip("_").isupper():
                    constants[target.id] = ast.dump(value, include_attributes=False)
        if constants:
            signature[relative] = dict(sorted(constants.items()))
    return signature


def _stable_error_codes() -> list[str]:
    codes: set[str] = set()
    for relative in cleanup_manifest():
        if not relative.startswith("backend/src/"):
            continue
        path = REPOSITORY_ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                if _STABLE_CODE.fullmatch(value) and (
                    value.startswith(
                        ("cache_", "cloud115_", "credential_", "playback_")
                    )
                    or value
                    in {"resource_not_found", "state_conflict", "validation_failed"}
                ):
                    codes.add(value)
    return sorted(codes)


def _file_digests(paths: tuple[str, ...]) -> dict[str, str]:
    return {
        relative: sha256((REPOSITORY_ROOT / relative).read_bytes()).hexdigest()
        for relative in paths
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
    subparsers.add_parser("mypy-files")
    capture = subparsers.add_parser("capture")
    capture.add_argument("output", type=Path)
    compare = subparsers.add_parser("compare")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    args = parser.parse_args()

    if args.command == "manifest":
        print("\n".join(cleanup_manifest()))
        return 0
    if args.command == "mypy-files":
        print("\n".join(mypy_files()))
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
