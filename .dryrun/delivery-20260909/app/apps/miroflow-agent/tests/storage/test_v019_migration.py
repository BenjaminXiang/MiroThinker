"""V019 quality_status and patent summary migration checks."""

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
    APP_ROOT / "alembic" / "versions" / "V019_add_quality_status_and_patent_summary.py"
)

DATABASE_URL_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)

CANONICAL_TABLES = ("professor", "company", "paper", "patent")
QUALITY_STATUS_VALUES = {
    "needs_review",
    "ready",
    "low_confidence",
    "needs_enrichment",
    "partial",
    "rejected",
}
QUALITY_STATUS_CHECKS = {
    table: f"ck_{table}_quality_status" for table in CANONICAL_TABLES
}
QUALITY_STATUS_INDEXES = {
    table: f"ix_{table}_quality_status" for table in CANONICAL_TABLES
}
PATENT_SUMMARY_COLUMNS = ("summary_text", "summary_text_method")
PATENT_SUMMARY_METHOD_CHECK = "ck_patent_summary_text_method"


def _load_migration():
    spec = importlib.util.spec_from_file_location("v019_migration", _MIGRATION_PATH)
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
        (list(QUALITY_STATUS_INDEXES.values()),),
    ).fetchall()
    return {(row["tablename"], row["indexname"]) for row in rows}


def _check_constraints(conn: psycopg.Connection) -> set[tuple[str, str]]:
    names = list(QUALITY_STATUS_CHECKS.values()) + [PATENT_SUMMARY_METHOD_CHECK]
    rows = conn.execute(
        """
        SELECT table_name, constraint_name
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND constraint_type = 'CHECK'
          AND constraint_name = ANY(%s)
        """,
        (names,),
    ).fetchall()
    return {(row["table_name"], row["constraint_name"]) for row in rows}


def _insert_with_quality_status(
    conn: psycopg.Connection, table_name: str, row_id: str, quality_status: str
) -> None:
    if table_name == "professor":
        conn.execute(
            """
            INSERT INTO professor (
                professor_id, canonical_name, discipline_family, quality_status
            )
            VALUES (%s, %s, 'computer_science', %s)
            """,
            (row_id, f"Professor {row_id}", quality_status),
        )
        return
    if table_name == "company":
        conn.execute(
            """
            INSERT INTO company (company_id, canonical_name, quality_status)
            VALUES (%s, %s, %s)
            """,
            (row_id, f"Company {row_id}", quality_status),
        )
        return
    if table_name == "paper":
        conn.execute(
            """
            INSERT INTO paper (
                paper_id, title_clean, canonical_source, quality_status
            )
            VALUES (%s, %s, 'openalex', %s)
            """,
            (row_id, f"Paper {row_id}", quality_status),
        )
        return
    if table_name == "patent":
        conn.execute(
            """
            INSERT INTO patent (
                patent_id, patent_number, title_clean, quality_status
            )
            VALUES (%s, %s, %s, %s)
            """,
            (row_id, f"PN-{row_id}", f"Patent {row_id}", quality_status),
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


def _assert_v019_schema_present(conn: psycopg.Connection) -> None:
    for table in CANONICAL_TABLES:
        columns = _columns(conn, table, ("quality_status",))
        assert set(columns) == {"quality_status"}
        column = columns["quality_status"]
        assert column["data_type"] == "text"
        assert column["is_nullable"] == "NO"
        assert "needs_review" in column["column_default"]

    patent_columns = _columns(conn, "patent", PATENT_SUMMARY_COLUMNS)
    assert set(patent_columns) == set(PATENT_SUMMARY_COLUMNS)
    assert {row["is_nullable"] for row in patent_columns.values()} == {"YES"}
    assert {row["data_type"] for row in patent_columns.values()} == {"text"}

    assert _indexes(conn) == set(QUALITY_STATUS_INDEXES.items())
    expected_checks = {
        (table, constraint_name)
        for table, constraint_name in QUALITY_STATUS_CHECKS.items()
    }
    expected_checks.add(("patent", PATENT_SUMMARY_METHOD_CHECK))
    assert _check_constraints(conn) == expected_checks


def test_v019_revision_chain():
    migration = _load_migration()

    assert migration.revision == "V019"
    assert migration.down_revision == "V018"


def test_v019_upgrade_adds_quality_status_columns_with_default(pg_conn) -> None:
    for table in CANONICAL_TABLES:
        columns = _columns(pg_conn, table, ("quality_status",))
        assert set(columns) == {"quality_status"}
        column = columns["quality_status"]
        assert column["data_type"] == "text"
        assert column["is_nullable"] == "NO"
        assert "needs_review" in column["column_default"]


def test_v019_quality_status_check_rejects_illegal_values(pg_conn) -> None:
    invalid_values = ("invalid", "pending", "invalid", "pending")

    for table, invalid_value in zip(CANONICAL_TABLES, invalid_values, strict=True):
        with _assert_check_violation(pg_conn, QUALITY_STATUS_CHECKS[table]):
            _insert_with_quality_status(
                pg_conn,
                table,
                f"v019-{table}-{invalid_value}",
                invalid_value,
            )


def test_v019_quality_status_check_allows_declared_values(pg_conn) -> None:
    for value in QUALITY_STATUS_VALUES:
        row_id = f"v019-quality-{value}"
        _insert_with_quality_status(pg_conn, "paper", row_id, value)

    rows = pg_conn.execute(
        """
        SELECT quality_status
        FROM paper
        WHERE paper_id LIKE 'v019-quality-%'
        """
    ).fetchall()
    assert {row["quality_status"] for row in rows} == QUALITY_STATUS_VALUES


def test_v019_patent_summary_columns_are_nullable(pg_conn) -> None:
    columns = _columns(pg_conn, "patent", PATENT_SUMMARY_COLUMNS)

    assert set(columns) == set(PATENT_SUMMARY_COLUMNS)
    assert {row["is_nullable"] for row in columns.values()} == {"YES"}
    assert {row["data_type"] for row in columns.values()} == {"text"}


def test_v019_patent_summary_method_check_rejects_illegal_values(pg_conn) -> None:
    for method in ("gpt", "manual"):
        with _assert_check_violation(pg_conn, PATENT_SUMMARY_METHOD_CHECK):
            pg_conn.execute(
                """
                INSERT INTO patent (
                    patent_id,
                    patent_number,
                    title_clean,
                    summary_text,
                    summary_text_method
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    f"v019-summary-method-{method}",
                    f"PN-v019-summary-method-{method}",
                    f"Patent {method}",
                    "summary",
                    method,
                ),
            )


def test_v019_patent_summary_method_allows_null(pg_conn) -> None:
    pg_conn.execute(
        """
        INSERT INTO patent (
            patent_id,
            patent_number,
            title_clean,
            summary_text,
            summary_text_method
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            "v019-summary-method-null",
            "PN-v019-summary-method-null",
            "Patent nullable summary method",
            "summary",
            None,
        ),
    )

    row = pg_conn.execute(
        """
        SELECT summary_text, summary_text_method
        FROM patent
        WHERE patent_id = 'v019-summary-method-null'
        """
    ).fetchone()
    assert row == {"summary_text": "summary", "summary_text_method": None}


def test_v019_downgrade_removes_columns_indexes_and_checks(pg_migrated, pg_dsn: str):
    del pg_migrated
    config = _alembic_config()

    try:
        command.downgrade(config, "V018")
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            for table in CANONICAL_TABLES:
                assert _columns(conn, table, ("quality_status",)) == {}
            assert _columns(conn, "patent", PATENT_SUMMARY_COLUMNS) == {}
            assert _indexes(conn) == set()
            assert _check_constraints(conn) == set()
    finally:
        command.upgrade(config, "head")

    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        _assert_v019_schema_present(conn)
