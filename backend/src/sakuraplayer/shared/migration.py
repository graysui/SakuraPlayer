from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command
from sakuraplayer.shared.config import load_settings
from sakuraplayer.shared.runtime import guarded_main
from sakuraplayer.shared.schema_guard import (
    _load_revision_graph,
    inspect_schema,
    validate_schema_for_migration,
)


def upgrade_database(database_url: str, alembic_ini: str | Path) -> None:
    known, _ = _load_revision_graph(alembic_ini)
    validate_schema_for_migration(
        inspect_schema(database_url),
        known_revisions=known,
    )
    config = Config(str(alembic_ini))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def main() -> None:
    settings = load_settings()
    ini_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    upgrade_database(settings.database_url, ini_path)


if __name__ == "__main__":
    guarded_main("migrate", main)
