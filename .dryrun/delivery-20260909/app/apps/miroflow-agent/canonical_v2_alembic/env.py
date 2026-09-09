"""Alembic environment for the clean Canonical V2 migration history."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.data_agents.canonical_v2.rebuild_write_gate import (
    require_accepted_backup_gate,
    resolve_backup_gate_root,
)
from src.data_agents.storage.database_target import (
    DestructiveDatabaseTarget,
    resolve_destructive_database_target,
)


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None
VERSION_TABLE = "canonical_v2_alembic_version"


def _resolve_target() -> DestructiveDatabaseTarget:
    return resolve_destructive_database_target(config, os.environ)


def _verify_backup_admission() -> None:
    evidence_root = resolve_backup_gate_root(config, os.environ)
    require_accepted_backup_gate(evidence_root)


def run_migrations_offline() -> None:
    """Emit SQL only after resolving the same explicit target and evidence gate."""
    target = _resolve_target()
    _verify_backup_admission()
    context.configure(
        url=target.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
        version_table_schema=None,
        version_table_pk=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Verify evidence, then target identity, before running Canonical V2 DDL."""
    target = _resolve_target()
    _verify_backup_admission()
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = target.url
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        target.verify_connected_database(connection)
        connection.rollback()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
            version_table_schema=None,
            version_table_pk=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
