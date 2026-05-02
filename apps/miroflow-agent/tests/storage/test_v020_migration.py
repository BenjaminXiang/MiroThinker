"""V020 paper and patent identity_status migration checks."""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
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
    APP_ROOT / "alembic" / "versions" / "V020_add_identity_status_paper_patent.py"
)

DATABASE_URL_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)

IDENTITY_TABLES = ("paper", "patent")
IDENTITY_STATUS_VALUES = {"confirmed", "unverified", "rejected", "merged"}
IDENTITY_STATUS_CHECKS = {
    table: f"ck_{table}_identity_status" for table in IDENTITY_TABLES
}
IDENTITY_STATUS_INDEXES = {
    table: f"ix_{table}_identity_status" for table in IDENTITY_TABLES
}
IDENTITY_STATUS_DEFAULTS = {
    "paper": "unverified",
    "patent": "confirmed",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("v020_migration", _MIGRATION_PATH)
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


def _columns(conn: psycopg.Connection, table_name: str, names: tuple[str, ...]):
    return {
        row["column_name"]: row
        for row in conn.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = ANY(%s)
            """,
            (table_name, list(names)),
        ).fetchall()
    }


def _indexes(conn: psycopg.Connection) -> set[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT tablename, indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = ANY(%s)
        """,
        (list(IDENTITY_STATUS_INDEXES.values()),),
    ).fetchall()
    return {(row["tablename"], row["indexname"]) for row in rows}


def _check_constraints(conn: psycopg.Connection) -> set[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT table_name, constraint_name
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND constraint_type = 'CHECK'
          AND constraint_name = ANY(%s)
        """,
        (list(IDENTITY_STATUS_CHECKS.values()),),
    ).fetchall()
    return {(row["table_name"], row["constraint_name"]) for row in rows}


def _insert_with_identity_status(
    conn: psycopg.Connection, table_name: str, row_id: str, identity_status: str
) -> None:
    if table_name == "paper":
        conn.execute(
            """
            INSERT INTO paper (
                paper_id, title_clean, canonical_source, identity_status
            )
            VALUES (%s, %s, 'openalex', %s)
            """,
            (row_id, f"Paper {row_id}", identity_status),
        )
        return
    if table_name == "patent":
        conn.execute(
            """
            INSERT INTO patent (
                patent_id, patent_number, title_clean, identity_status
            )
            VALUES (%s, %s, %s, %s)
            """,
            (row_id, f"PN-{row_id}", f"Patent {row_id}", identity_status),
        )
        return
    raise AssertionError(f"unexpected table: {table_name}")


def _insert_without_identity_status(
    conn: psycopg.Connection, table_name: str, row_id: str
) -> None:
    if table_name == "paper":
        conn.execute(
            """
            INSERT INTO paper (paper_id, title_clean, canonical_source)
            VALUES (%s, %s, 'openalex')
            """,
            (row_id, f"Paper {row_id}"),
        )
        return
    if table_name == "patent":
        conn.execute(
            """
            INSERT INTO patent (patent_id, patent_number, title_clean)
            VALUES (%s, %s, %s)
            """,
            (row_id, f"PN-{row_id}", f"Patent {row_id}"),
        )
        return
    raise AssertionError(f"unexpected table: {table_name}")


@contextmanager
def _assert_check_violation(conn: psycopg.Connection, constraint_name: str):
    try:
        with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
            yield
        assert constraint_name in str(excinfo.value)
    finally:
        conn.rollback()


def _assert_v020_schema_present(conn: psycopg.Connection) -> None:
    for table in IDENTITY_TABLES:
        columns = _columns(conn, table, ("identity_status",))
        assert set(columns) == {"identity_status"}
        column = columns["identity_status"]
        assert column["data_type"] == "text"
        assert column["is_nullable"] == "NO"
        assert IDENTITY_STATUS_DEFAULTS[table] in column["column_default"]

    assert _indexes(conn) == set(IDENTITY_STATUS_INDEXES.items())
    assert _check_constraints(conn) == set(IDENTITY_STATUS_CHECKS.items())


def test_v020_revision_chain():
    migration = _load_migration()

    assert migration.revision == "V020"
    assert migration.down_revision == "V019"


def test_v020_upgrade_adds_identity_status_columns_with_defaults(pg_conn) -> None:
    _assert_v020_schema_present(pg_conn)


def test_v020_identity_status_defaults_are_domain_specific(pg_conn) -> None:
    for table in IDENTITY_TABLES:
        row_id = f"v020-default-{table}"
        _insert_without_identity_status(pg_conn, table, row_id)

        row = pg_conn.execute(
            f"""
            SELECT identity_status
            FROM {table}
            WHERE {table}_id = %s
            """,
            (row_id,),
        ).fetchone()
        assert row == {"identity_status": IDENTITY_STATUS_DEFAULTS[table]}


def test_v020_identity_status_check_rejects_illegal_values(pg_conn) -> None:
    for table in IDENTITY_TABLES:
        with _assert_check_violation(pg_conn, IDENTITY_STATUS_CHECKS[table]):
            _insert_with_identity_status(
                pg_conn,
                table,
                f"v020-{table}-invalid",
                "invalid",
            )


def test_v020_identity_status_check_allows_declared_values(pg_conn) -> None:
    for value in IDENTITY_STATUS_VALUES:
        row_id = f"v020-identity-{value}"
        _insert_with_identity_status(pg_conn, "paper", row_id, value)

    rows = pg_conn.execute(
        """
        SELECT identity_status
        FROM paper
        WHERE paper_id LIKE 'v020-identity-%'
        """
    ).fetchall()
    assert {row["identity_status"] for row in rows} == IDENTITY_STATUS_VALUES


def test_v020_downgrade_removes_columns_indexes_and_checks(pg_migrated, pg_dsn: str):
    del pg_migrated
    config = _alembic_config()

    try:
        command.downgrade(config, "V019")
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            for table in IDENTITY_TABLES:
                assert _columns(conn, table, ("identity_status",)) == {}
            assert _indexes(conn) == set()
            assert _check_constraints(conn) == set()
    finally:
        command.upgrade(config, "head")

    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        _assert_v020_schema_present(conn)
