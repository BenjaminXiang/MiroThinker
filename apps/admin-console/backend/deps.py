from __future__ import annotations

import os
from functools import lru_cache

from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

_DEFAULT_DB_PATH = "logs/data_agents/released_objects.db"


@lru_cache(maxsize=1)
def get_store() -> SqliteReleasedObjectStore:
    db_path = os.environ.get("ADMIN_DB_PATH", _DEFAULT_DB_PATH)
    return SqliteReleasedObjectStore(db_path)
