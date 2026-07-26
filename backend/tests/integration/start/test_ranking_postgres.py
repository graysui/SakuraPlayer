from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from sakuraplayer.shared.migration import upgrade_database


pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


@pytest.fixture
def database_url() -> str:
    base_url = make_url(os.environ["SAKURAPLAYER_TEST_DATABASE_URL"])
    password = os.environ.get("SAKURAPLAYER_TEST_DATABASE_PASSWORD")
    if password is not None:
        base_url = base_url.set(password=password)
    database_name = f"task012_migration_{uuid.uuid4().hex}"
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


def test_postgres_upgrades_0011_constraints_and_downgrade(database_url: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "0011_catalog_discovery")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        assert "ranking_snapshot" not in inspect(connection).get_table_names()
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert {
            "ranking_sync_request",
            "ranking_snapshot",
            "ranking_entry",
        } <= set(inspector.get_table_names())
        index_names = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = current_schema()"
                )
            )
        }
        assert {
            "uq_ranking_request_slot",
            "uq_ranking_request_active_scope",
            "uq_ranking_snapshot_current_scope",
            "uq_ranking_entry_number",
        } <= index_names

    now = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO ranking_snapshot "
                "(id, board, year, status, source_synced_at, created_at) "
                "VALUES (:id, 'daily', NULL, 'current', :now, :now)"
            ),
            {"id": uuid.uuid4(), "now": now},
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ranking_snapshot "
                    "(id, board, year, status, source_synced_at, created_at) "
                    "VALUES (:id, 'daily', NULL, 'current', :now, :now)"
                ),
                {"id": uuid.uuid4(), "now": now},
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ranking_snapshot "
                    "(id, board, year, status, source_synced_at, created_at) "
                    "VALUES (:id, 'daily', 2026, 'building', :now, :now)"
                ),
                {"id": uuid.uuid4(), "now": now},
            )
    engine.dispose()

    command.downgrade(config, "0011_catalog_discovery")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        assert not {
            "ranking_sync_request",
            "ranking_snapshot",
            "ranking_entry",
        } & set(inspect(connection).get_table_names())
    engine.dispose()

    upgrade_database(database_url, ALEMBIC_INI)
