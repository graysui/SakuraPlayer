from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from sakuraplayer.catalog import models as catalog_models
from sakuraplayer.discovery import models as discovery_models
from sakuraplayer.events import models as event_models
from sakuraplayer.resources import models as resource_models
from sakuraplayer.shared.redaction import install_redaction_filters


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
    install_redaction_filters()

target_metadata = resource_models.Base.metadata
assert catalog_models.MetadataJob.metadata is target_metadata
assert discovery_models.Favorite.metadata is target_metadata
assert discovery_models.RankingSyncRequest.metadata is target_metadata
assert event_models.DomainEvent.metadata is target_metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
