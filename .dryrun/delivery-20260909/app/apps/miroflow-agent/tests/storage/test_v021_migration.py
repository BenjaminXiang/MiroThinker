"""V021 company aliases JSONB migration checks."""

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
_MIGRATION_PATH = APP_ROOT / "alembic" / "versions" / "V021_add_company_aliases.py"

DATABASE_URL_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)

ALIASES_INDEX = "ix_company_aliases_gin"


def _load_migration():
    spec = importlib.util.spec_from_file_location("v021_migration", _MIGRATION_PATH)
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


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    _ensure_socket_api_available()
    return _psycopg_dsn(_raw_database_url())


@pytest.fixture(scope="session")
def pg_migrated(pg_dsn: str):
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_dsn
    command.upgrade(_alembic_config(), "head")
    try:
        yield
    finally:
        if original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_db_url


@pytest.fixture()
def pg_conn(pg_migrated, pg_dsn: str):
    del pg_migrated
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        try:
            yield conn
        finally:
            conn.rollback()


def _columns(conn: psycopg.Connection, names: tuple[str, ...]):
    return {
        row["column_name"]: row
        for row in conn.execute(
            """
            SELECT column_name, data_type, udt_name, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'company'
              AND column_name = ANY(%s)
            """,
            (list(names),),
        ).fetchall()
    }


def _index_defs(conn: psycopg.Connection) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'company'
          AND indexname = %s
        """,
        (ALIASES_INDEX,),
    ).fetchall()
    return {row["indexname"]: row["indexdef"] for row in rows}


def _assert_v021_schema_present(conn: psycopg.Connection) -> None:
    columns = _columns(conn, ("aliases",))
    assert set(columns) == {"aliases"}
    column = columns["aliases"]
    assert column["data_type"] == "jsonb"
    assert column["is_nullable"] == "NO"
    assert "'[]'::jsonb" in column["column_default"]

    index_def = _index_defs(conn)[ALIASES_INDEX]
    assert "USING gin" in index_def
    assert "(aliases)" in index_def


def _assert_v020_alias_schema_present(conn: psycopg.Connection) -> None:
    columns = _columns(conn, ("aliases",))
    assert set(columns) == {"aliases"}
    column = columns["aliases"]
    assert column["data_type"] == "ARRAY"
    assert column["udt_name"] == "_text"
    assert column["is_nullable"] == "NO"
    assert "'{}'::text[]" in column["column_default"]
    assert _index_defs(conn) == {}


def test_v021_revision_chain():
    migration = _load_migration()

    assert migration.revision == "V021"
    assert migration.down_revision == "V020"


def test_v021_upgrade_converts_company_aliases_to_jsonb_with_gin_index(pg_conn) -> None:
    _assert_v021_schema_present(pg_conn)


def test_v021_company_aliases_default_to_empty_json_array(pg_conn) -> None:
    row_id = "v021-default-company"
    pg_conn.execute(
        """
        INSERT INTO company (company_id, canonical_name)
        VALUES (%s, %s)
        ON CONFLICT (company_id) DO UPDATE
        SET aliases = EXCLUDED.aliases
        """,
        (row_id, "V021 Default Company"),
    )

    row = pg_conn.execute(
        """
        SELECT aliases = '[]'::jsonb AS aliases_is_empty_json_array,
               jsonb_typeof(aliases) AS aliases_type
        FROM company
        WHERE company_id = %s
        """,
        (row_id,),
    ).fetchone()
    assert row == {
        "aliases_is_empty_json_array": True,
        "aliases_type": "array",
    }


def test_v021_company_aliases_support_jsonb_containment(pg_conn) -> None:
    row_id = "v021-alias-company"
    pg_conn.execute(
        """
        INSERT INTO company (company_id, canonical_name, aliases)
        VALUES (%s, %s, '["广和通", "Fibocom"]'::jsonb)
        ON CONFLICT (company_id) DO UPDATE
        SET aliases = EXCLUDED.aliases
        """,
        (row_id, "广和通"),
    )

    row = pg_conn.execute(
        """
        SELECT aliases @> '["广和通"]'::jsonb AS has_chinese_alias,
               aliases @> '["Fibocom"]'::jsonb AS has_english_alias
        FROM company
        WHERE company_id = %s
        """,
        (row_id,),
    ).fetchone()
    assert row == {
        "has_chinese_alias": True,
        "has_english_alias": True,
    }


def test_v021_downgrade_restores_company_aliases_text_array(pg_migrated, pg_dsn: str):
    del pg_migrated
    config = _alembic_config()

    try:
        command.downgrade(config, "V020")
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            _assert_v020_alias_schema_present(conn)
    finally:
        command.upgrade(config, "head")

    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        _assert_v021_schema_present(conn)
