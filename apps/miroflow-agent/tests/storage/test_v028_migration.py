"""V028 paper canonical_source migration checks."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import socket

from alembic import command
from alembic.config import Config
import psycopg
from psycopg.rows import dict_row
import pytest

APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "alembic.ini"
_MIGRATION_PATH = (
    APP_ROOT
    / "alembic"
    / "versions"
    / "V028_extend_paper_canonical_source_page_flow.py"
)

DATABASE_URL_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v028_migration", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _raw_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip(DATABASE_URL_SKIP_REASON)
    if any(name in database_url for name in _REAL_DB_NAMES):
        pytest.fail(
            f"Refusing to run tests against a real-data database: {database_url!r}. "
            "Set DATABASE_URL_TEST to miroflow_test_mock (or similar)."
        )
    return database_url


def _psycopg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _ensure_socket_api_available() -> None:
    try:
        sock = socket.socket()
    except PermissionError:
        pytest.skip(NETWORK_SKIP_REASON)
    else:
        sock.close()


def _alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(APP_ROOT / "alembic"))
    return config


@pytest.fixture()
def pg_dsn() -> str:
    _ensure_socket_api_available()
    return _psycopg_dsn(_raw_database_url())


@pytest.fixture()
def migrated_conn(pg_dsn: str):
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_dsn
    command.upgrade(_alembic_config(), "head")
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        try:
            yield conn
        finally:
            conn.rollback()
    if original_db_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = original_db_url


def test_v028_revision_chain():
    migration = _load_migration()

    assert migration.revision == "V028"
    assert migration.down_revision == "V027"


def test_v028_allows_prof_page_only_and_arxiv_sources(migrated_conn) -> None:
    for source in ("prof_page_only", "arxiv"):
        paper_id = f"v028-{source}"
        migrated_conn.execute(
            """
            INSERT INTO paper (paper_id, title_clean, canonical_source)
            VALUES (%s, %s, %s)
            """,
            (paper_id, f"Paper {source}", source),
        )

    rows = migrated_conn.execute(
        """
        SELECT canonical_source
        FROM paper
        WHERE paper_id IN ('v028-prof_page_only', 'v028-arxiv')
        ORDER BY canonical_source
        """
    ).fetchall()

    assert [row["canonical_source"] for row in rows] == ["arxiv", "prof_page_only"]
