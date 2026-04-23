"""Dependency factories for the admin console.

Environment variables:
- `ADMIN_DB_PATH`: override the sqlite released-objects database path.
- `DATABASE_URL` / `DATABASE_URL_TEST`: Postgres DSN for app runtime and tests.
- `CHAT_USE_RETRIEVAL_SERVICE`: chat retrieval flag. Defaults on; accepts
  truthy `1/true/yes/on` and falsy `0/false/no/off` values.
- `CHAT_E_WEB_FALLBACK_THRESHOLD`: paper-retrieval confidence threshold for
  E-route web fallback. Defaults to `0.5`.
- `CHAT_MILVUS_URI` / `MILVUS_URI`: Milvus URI for RetrievalService.
  Prefer `CHAT_MILVUS_URI` — pymilvus also reads `MILVUS_URI` globally at
  import, and a milvus-lite path (`./milvus.db`) trips its server-URI
  validator. Defaults to `./milvus.db`.
"""

from __future__ import annotations

import logging
import os
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from src.data_agents.professor.vectorizer import EmbeddingClient
from src.data_agents.providers.local_api_key import load_local_api_key
from src.data_agents.providers.rerank import RerankerClient
from src.data_agents.providers.web_search import WebSearchProvider
from src.data_agents.service.retrieval import RetrievalService
from src.data_agents.storage.sqlite_store import SqliteReleasedObjectStore

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_DB_PATH = str(_REPO_ROOT / "logs" / "data_agents" / "released_objects.db")
_DEFAULT_CHAT_E_WEB_FALLBACK_THRESHOLD = 0.5

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_sqlite_store() -> SqliteReleasedObjectStore:
    db_path = os.environ.get("ADMIN_DB_PATH", _DEFAULT_DB_PATH)
    return SqliteReleasedObjectStore(db_path)


def get_store() -> SqliteReleasedObjectStore:
    return get_sqlite_store()


def chat_use_retrieval_service() -> bool:
    raw = os.environ.get("CHAT_USE_RETRIEVAL_SERVICE")
    if raw is None:
        return True
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return True


def chat_e_web_fallback_threshold() -> float:
    raw = os.environ.get("CHAT_E_WEB_FALLBACK_THRESHOLD")
    if raw is None:
        return _DEFAULT_CHAT_E_WEB_FALLBACK_THRESHOLD
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Malformed CHAT_E_WEB_FALLBACK_THRESHOLD=%r; using default %.1f",
            raw,
            _DEFAULT_CHAT_E_WEB_FALLBACK_THRESHOLD,
        )
        return _DEFAULT_CHAT_E_WEB_FALLBACK_THRESHOLD


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


@lru_cache(maxsize=1)
def _get_milvus_client() -> Any:
    milvus_uri = (
        os.environ.get("CHAT_MILVUS_URI")
        or os.environ.get("MILVUS_URI")
        or "./milvus.db"
    )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
            module="milvus_lite",
        )
        from pymilvus import MilvusClient

    return MilvusClient(uri=milvus_uri)


@lru_cache(maxsize=1)
def _get_embedding_client() -> EmbeddingClient:
    return EmbeddingClient(api_key=load_local_api_key())


@lru_cache(maxsize=1)
def _get_reranker_client() -> RerankerClient:
    return RerankerClient(api_key=load_local_api_key())


@lru_cache(maxsize=1)
def _get_web_search_provider() -> WebSearchProvider:
    return WebSearchProvider()


@lru_cache(maxsize=1)
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(
        pg_conn_factory=get_pg_conn,
        milvus_client=_get_milvus_client(),
        embedding_client=_get_embedding_client(),
        reranker=_get_reranker_client(),
        cache=None,
    )
