from __future__ import annotations

import os
from pathlib import Path
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from sakuraplayer.shared.migration import upgrade_database
from sakuraplayer.shared.schema_guard import SchemaGuardError, check_schema


pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task001_{uuid.uuid4().hex}"
    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()

    test_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    try:
        yield test_url
    finally:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin_engine.dispose()


def test_empty_database_requires_explicit_migration(database_url: str) -> None:
    with pytest.raises(SchemaGuardError) as error:
        check_schema(database_url, ALEMBIC_INI)

    assert error.value.code == "schema_migration_required"


def test_nonempty_unversioned_database_is_not_adopted(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE legacy_media (id integer primary key)"))
    engine.dispose()

    with pytest.raises(SchemaGuardError) as error:
        upgrade_database(database_url, ALEMBIC_INI)

    assert error.value.code == "schema_revision_unknown"


def test_nonpublic_user_schema_is_not_adopted(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA legacy"))
        connection.execute(text("CREATE TABLE legacy.media (id integer primary key)"))
    engine.dispose()

    with pytest.raises(SchemaGuardError) as error:
        upgrade_database(database_url, ALEMBIC_INI)

    assert error.value.code == "schema_revision_unknown"


@pytest.mark.parametrize(
    "object_ddl",
    [
        "CREATE VIEW legacy_view AS SELECT 1 AS id",
        "CREATE VIEW alembic_version AS SELECT 'fake'::text AS version_num",
        "CREATE SEQUENCE legacy_sequence",
        "CREATE SEQUENCE alembic_version",
        "CREATE TYPE legacy_status AS ENUM ('legacy')",
        (
            "CREATE FUNCTION legacy_function() RETURNS integer "
            "LANGUAGE SQL AS 'SELECT 1'"
        ),
    ],
)
def test_nonempty_unversioned_database_with_user_object_is_not_adopted(
    database_url: str,
    object_ddl: str,
) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(object_ddl))
    engine.dispose()

    with pytest.raises(SchemaGuardError) as error:
        upgrade_database(database_url, ALEMBIC_INI)

    assert error.value.code == "schema_revision_unknown"


def test_upgrade_to_head_is_idempotent_and_creates_identity_tables(
    database_url: str,
) -> None:
    upgrade_database(database_url, ALEMBIC_INI)
    upgrade_database(database_url, ALEMBIC_INI)
    check_schema(database_url, ALEMBIC_INI)

    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert sorted(inspect(connection).get_table_names()) == [
            "admin_user",
            "alembic_version",
            "refresh_session",
        ]
    engine.dispose()


def test_known_initial_revision_requires_identity_migration(database_url: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "0001_initial_skeleton")

    with pytest.raises(SchemaGuardError) as error:
        check_schema(database_url, ALEMBIC_INI)

    assert error.value.code == "schema_migration_required"
    upgrade_database(database_url, ALEMBIC_INI)
    check_schema(database_url, ALEMBIC_INI)


def test_unknown_revision_is_rejected_without_leaking_revision(
    database_url: str,
) -> None:
    upgrade_database(database_url, ALEMBIC_INI)
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num = 'unexpected_revision'")
        )
    engine.dispose()

    with pytest.raises(SchemaGuardError) as error:
        check_schema(database_url, ALEMBIC_INI)

    assert error.value.code == "schema_revision_unknown"
    assert "unexpected_revision" not in str(error.value)


def test_malformed_version_table_is_schema_unknown(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (wrong_name text)"))
    engine.dispose()

    with pytest.raises(SchemaGuardError) as error:
        check_schema(database_url, ALEMBIC_INI)

    assert error.value.code == "schema_revision_unknown"


def test_version_table_without_alembic_constraints_is_schema_unknown(
    database_url: str,
) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num text)"))
        connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES ('0001_initial_skeleton')"
            )
        )
    engine.dispose()

    with pytest.raises(SchemaGuardError) as error:
        check_schema(database_url, ALEMBIC_INI)

    assert error.value.code == "schema_revision_unknown"


def test_duplicate_version_rows_are_schema_unknown(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num text)"))
        connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) VALUES "
                "('0001_initial_skeleton'), ('0001_initial_skeleton')"
            )
        )
    engine.dispose()

    with pytest.raises(SchemaGuardError) as error:
        check_schema(database_url, ALEMBIC_INI)

    assert error.value.code == "schema_revision_unknown"
