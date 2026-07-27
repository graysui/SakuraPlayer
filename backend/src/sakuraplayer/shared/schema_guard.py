from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class SchemaGuardError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SchemaState:
    current_revisions: frozenset[str] | None
    has_user_tables: bool
    version_row_count: int | None = None
    version_table_valid: bool = True


def validate_schema_state(
    state: SchemaState,
    *,
    known_revisions: frozenset[str],
    expected_heads: frozenset[str],
) -> None:
    current = state.current_revisions
    if not state.version_table_valid:
        raise SchemaGuardError("schema_revision_unknown")
    if state.version_row_count is not None and state.version_row_count != len(
        current or ()
    ):
        raise SchemaGuardError("schema_revision_unknown")
    if current is None:
        code = (
            "schema_revision_unknown"
            if state.has_user_tables
            else "schema_migration_required"
        )
        raise SchemaGuardError(code)
    if current == expected_heads and current:
        return
    if not current or len(current) != 1:
        raise SchemaGuardError("schema_revision_unknown")
    if current.issubset(known_revisions):
        raise SchemaGuardError("schema_migration_required")
    raise SchemaGuardError("schema_revision_unknown")


def validate_schema_for_migration(
    state: SchemaState,
    *,
    known_revisions: frozenset[str],
) -> None:
    current = state.current_revisions
    if not state.version_table_valid:
        raise SchemaGuardError("schema_revision_unknown")
    if state.version_row_count is not None and state.version_row_count != len(
        current or ()
    ):
        raise SchemaGuardError("schema_revision_unknown")
    if current is None:
        if state.has_user_tables:
            raise SchemaGuardError("schema_revision_unknown")
        return
    if len(current) != 1:
        raise SchemaGuardError("schema_revision_unknown")
    if not current.issubset(known_revisions):
        raise SchemaGuardError("schema_revision_unknown")


def _load_revision_graph(
    alembic_ini: str | Path,
) -> tuple[frozenset[str], frozenset[str]]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(alembic_ini))
    script = ScriptDirectory.from_config(config)
    known = frozenset(revision.revision for revision in script.walk_revisions())
    heads = frozenset(script.get_heads())
    return known, heads


def _read_schema_state(connection) -> SchemaState:
    from sqlalchemy import String, inspect, text

    inspector = inspect(connection)
    public_tables = set(inspector.get_table_names(schema="public"))
    has_user_objects = bool(
        connection.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_namespace AS namespace
                    WHERE namespace.nspname <> 'public'
                      AND namespace.nspname <> 'information_schema'
                      AND namespace.nspname NOT LIKE 'pg_%'
                    UNION ALL
                    SELECT 1
                    FROM pg_catalog.pg_class AS object
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = object.relnamespace
                    WHERE namespace.nspname <> 'information_schema'
                      AND namespace.nspname NOT LIKE 'pg_%'
                    UNION ALL
                    SELECT 1
                    FROM pg_catalog.pg_proc AS object
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = object.pronamespace
                    WHERE namespace.nspname <> 'information_schema'
                      AND namespace.nspname NOT LIKE 'pg_%'
                    UNION ALL
                    SELECT 1
                    FROM pg_catalog.pg_type AS object
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = object.typnamespace
                    WHERE namespace.nspname <> 'information_schema'
                      AND namespace.nspname NOT LIKE 'pg_%'
                      AND object.typtype IN ('d', 'e', 'm', 'r')
                )
                """
            )
        )
    )
    has_version_table = "alembic_version" in public_tables
    if not has_version_table:
        return SchemaState(
            current_revisions=None,
            has_user_tables=has_user_objects,
        )
    columns = inspector.get_columns("alembic_version", schema="public")
    primary_key = inspector.get_pk_constraint("alembic_version", schema="public")
    version_table_valid = (
        len(columns) == 1
        and columns[0]["name"] == "version_num"
        and isinstance(columns[0]["type"], String)
        and columns[0]["type"].length == 32
        and columns[0]["nullable"] is False
        and primary_key.get("constrained_columns") == ["version_num"]
    )
    if not version_table_valid:
        return SchemaState(
            current_revisions=frozenset(),
            has_user_tables=has_user_objects,
            version_table_valid=False,
        )
    rows = list(
        connection.execute(text("SELECT version_num FROM public.alembic_version"))
    )
    return SchemaState(
        current_revisions=frozenset(row[0] for row in rows),
        has_user_tables=has_user_objects,
        version_row_count=len(rows),
    )


def inspect_schema(database_url: str) -> SchemaState:
    from sqlalchemy import create_engine
    from sqlalchemy.exc import SQLAlchemyError

    try:
        engine = create_engine(database_url, connect_args={"connect_timeout": 3})
        with engine.connect() as connection:
            try:
                return _read_schema_state(connection)
            except SQLAlchemyError:
                raise SchemaGuardError("schema_revision_unknown") from None
    except SchemaGuardError:
        raise
    except SQLAlchemyError:
        raise SchemaGuardError("database_unavailable") from None
    finally:
        if "engine" in locals():
            engine.dispose()


def check_schema(database_url: str, alembic_ini: str | Path) -> None:
    known, heads = _load_revision_graph(alembic_ini)
    validate_schema_state(
        inspect_schema(database_url),
        known_revisions=known,
        expected_heads=heads,
    )
