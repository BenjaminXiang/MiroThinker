from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_DB_PATH = str(_REPO_ROOT / "logs" / "data_agents" / "released_objects.db")


@lru_cache(maxsize=1)
def get_sqlite_store() -> SqliteReleasedObjectStore:
    db_path = os.environ.get("ADMIN_DB_PATH", _DEFAULT_DB_PATH)
    return SqliteReleasedObjectStore(db_path)


def get_store() -> SqliteReleasedObjectStore:
    return get_sqlite_store()


@lru_cache(maxsize=1)
def get_pg_pool() -> Any:
    from src.data_agents.storage.postgres.connection import open_pool

    # DATABASE_URL_TEST lets pytest isolate from real data; production reads DATABASE_URL.
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_TEST")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL (or DATABASE_URL_TEST) must be set before starting the admin console."
        )
    return open_pool(dsn)


def get_pg_conn() -> Iterator[Any]:
    pool = get_pg_pool()
    with pool.connection() as conn:
        yield conn
