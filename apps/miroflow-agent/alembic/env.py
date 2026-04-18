"""Alembic environment for the knowledge graph Postgres store.

Reads DATABASE_URL from the environment. Does not use an ORM Metadata object
(we manage DDL explicitly in each revision via op.create_table / op.execute),
so `target_metadata` stays None.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No SQLAlchemy ORM metadata — migrations use explicit op.* calls.
target_metadata = None


def _resolve_url() -> str:
    # DATABASE_URL is the canonical name (real-data runs and ad-hoc use).
    # DATABASE_URL_TEST is the test-only override that keeps pytest isolated
    # from real data. See docs/plans/2026-04-18-002-real-data-e2e-and-db-
    # separation.md §4.
    url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not url:
        raise RuntimeError(
            "DATABASE_URL (or DATABASE_URL_TEST) is required. "
            "Example: postgresql+psycopg://user:pass@localhost:5432/miroflow"
        )
    # SQLAlchemy needs the '+psycopg' driver marker; bare 'postgresql://' would
    # fall back to psycopg2 (which is intentionally NOT installed).
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of connecting to a database."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the configured database and run migrations."""
    cfg_section = config.get_section(config.config_ini_section) or {}
    cfg_section["sqlalchemy.url"] = _resolve_url()

    connectable = engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
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
