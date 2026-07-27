from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from alembic import command
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
    database_name = f"task011_migration_{uuid.uuid4().hex}"
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


def test_postgres_upgrades_0010_and_empty_database_to_catalog_discovery(
    database_url: str,
) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "0010_translation")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        assert "favorite" not in inspect(connection).get_table_names()
    engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert "favorite" in inspector.get_table_names()
        assert connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_trgm')")
        )
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
            "ix_movie_title_original_trgm",
            "ix_movie_title_zh_trgm",
            "ix_actor_name_ja_trgm",
            "ix_actor_name_zh_trgm",
            "ix_actor_alias_normalized_trgm",
            "ix_favorite_target_created",
            "uq_favorite_target",
        } <= index_names
    engine.dispose()

    command.downgrade(config, "0010_translation")
    engine = create_engine(database_url, hide_parameters=True)
    with engine.connect() as connection:
        assert "favorite" not in inspect(connection).get_table_names()
        remaining = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = current_schema()"
                )
            )
        }
        assert (
            not {
                "ix_movie_title_original_trgm",
                "ix_actor_alias_normalized_trgm",
            }
            & remaining
        )
    engine.dispose()

    upgrade_database(database_url, ALEMBIC_INI)
