"""psycopg3 connection helpers.

Per ADR-001 we use psycopg3 with [binary,pool] extras. Alembic uses its own
env.py-driven connection; this module is for application code (repos,
importers, dashboards).

DSN handling: callers may pass either the bare psycopg form
`postgresql://u:p@h:port/db` or the SQLAlchemy form
`postgresql+psycopg://...`. The latter is stripped to the former before
handing to psycopg.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


_SQLALCHEMY_PREFIX = "postgresql+psycopg://"
_PG_PREFIX = "postgresql://"


def _normalize_dsn(dsn: str) -> str:
    """Strip SQLAlchemy's `+psycopg` driver marker so psycopg can parse the URL."""
    if dsn.startswith(_SQLALCHEMY_PREFIX):
        return _PG_PREFIX + dsn[len(_SQLALCHEMY_PREFIX) :]
    return dsn


def resolve_dsn(dsn: str | None = None) -> str:
    """Return a normalized DSN.

    Precedence: explicit `dsn` arg > `DATABASE_URL` env var.
    Raises `RuntimeError` if neither source provides a DSN.
    """
    raw = dsn or os.environ.get("DATABASE_URL")
    if not raw:
        raise RuntimeError(
            "DATABASE_URL is required. "
            "Example: postgresql+psycopg://user:pass@localhost:5432/miroflow"
        )
    return _normalize_dsn(raw)


@contextmanager
def connect(
    dsn: str | None = None, *, row_factory=dict_row, autocommit: bool = False
) -> Iterator[Connection]:
    """Context-managed psycopg3 connection.

    Defaults: `dict_row` row factory and `autocommit=False` so callers get
    transactional semantics by default. Explicit `autocommit=True` is useful
    for DDL-like statements outside of a transaction.
    """
    resolved = resolve_dsn(dsn)
    with psycopg.connect(
        resolved, row_factory=row_factory, autocommit=autocommit
    ) as conn:
        yield conn


def open_pool(
    dsn: str | None = None,
    *,
    min_size: int = 2,
    max_size: int = 10,
    timeout: float = 30.0,
) -> ConnectionPool:
    """Return a lazily-initialized connection pool.

    Callers are responsible for `pool.close()` at shutdown (typically in an
    ASGI lifespan or CLI finally block).
    """
    resolved = resolve_dsn(dsn)
    pool = ConnectionPool(
        conninfo=resolved,
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        timeout=timeout,
    )
    return pool
