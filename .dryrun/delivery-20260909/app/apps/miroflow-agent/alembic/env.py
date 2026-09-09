"""Alembic environment for the knowledge graph Postgres store.

Destructive migration targets use a dedicated, fail-closed target contract.
The migrations manage DDL explicitly, so ``target_metadata`` stays ``None``.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.data_agents.storage.database_target import (
    DestructiveDatabaseTarget,
    resolve_destructive_database_target,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No SQLAlchemy ORM metadata — migrations use explicit op.* calls.
target_metadata = None


def _resolve_target() -> DestructiveDatabaseTarget:
    return resolve_destructive_database_target(config, os.environ)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of connecting to a database."""
    target = _resolve_target()
    context.configure(
        url=target.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the configured database and run migrations."""
    target = _resolve_target()
    cfg_section = config.get_section(config.config_ini_section) or {}
    cfg_section["sqlalchemy.url"] = target.url

    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        target.verify_connected_database(connection)
        # The identity SELECT starts SQLAlchemy's implicit transaction. End that
        # read-only transaction so Alembic owns and commits the migration one.
        connection.rollback()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
