"""V032 professor-patent evidence URL migration checks."""

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
    / "V032_add_professor_patent_link_evidence_url.py"
)

DATABASE_URL_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v032_migration", _MIGRATION_PATH)
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
    command.downgrade(_alembic_config(), "base")
    if original_db_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = original_db_url


def _columns(conn: psycopg.Connection):
    rows = conn.execute(
        """
        SELECT column_name, is_nullable, data_type
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'professor_patent_link'
           AND column_name IN ('evidence_url', 'evidence_anchor')
         ORDER BY column_name
        """
    ).fetchall()
    return rows


def test_v032_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V032"
    assert migration.down_revision == "V031"


def test_v032_adds_professor_patent_link_evidence_columns(
    migrated_conn,
) -> None:
    assert _columns(migrated_conn) == [
        {"column_name": "evidence_anchor", "is_nullable": "YES", "data_type": "text"},
        {"column_name": "evidence_url", "is_nullable": "YES", "data_type": "text"},
    ]
