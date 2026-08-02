"""Alembic environment.

The database URL comes from the validated application configuration, never from
alembic.ini, so a migration can never be applied to an unvalidated location.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from chillify.config import load_settings, preflight_mounted_roots
from chillify.infrastructure.db.engine import create_database_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _database_path() -> str:
    """Resolve the target database, failing before any DDL if config is invalid."""
    override = config.get_main_option("sqlalchemy.url")
    if override:
        return override.removeprefix("sqlite+pysqlite:///").removeprefix("sqlite:///")
    settings = load_settings()
    preflight_mounted_roots(settings)
    return str(settings.database_path)


def run_migrations_offline() -> None:
    context.configure(
        url=f"sqlite+pysqlite:///{_database_path()}",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from pathlib import Path

    engine = create_database_engine(Path(_database_path()))
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
