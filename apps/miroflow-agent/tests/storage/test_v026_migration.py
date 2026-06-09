"""V026 page-only patent-number migration checks."""

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
    APP_ROOT / "alembic" / "versions" / "V026_allow_page_only_patent_number.py"
)

DATABASE_URL_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v026_migration", _MIGRATION_PATH)
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


def _patent_number_column(conn: psycopg.Connection):
    row = conn.execute(
        """
        SELECT column_name, is_nullable, data_type
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'patent'
           AND column_name = 'patent_number'
        """
    ).fetchone()
    assert row is not None
    return row


def test_v026_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V026"
    assert migration.down_revision == "V025"


def test_v026_allows_page_only_patents_without_number(migrated_conn) -> None:
    column = _patent_number_column(migrated_conn)
    assert column == {
        "column_name": "patent_number",
        "is_nullable": "YES",
        "data_type": "text",
    }

    for patent_id in ("PAT-V026-PAGE-ONLY-1", "PAT-V026-PAGE-ONLY-2"):
        migrated_conn.execute(
            """
            INSERT INTO patent (
                patent_id,
                patent_number,
                title_clean,
                identity_status,
                quality_status
            )
            VALUES (%s, NULL, %s, 'unverified', 'needs_enrichment')
            """,
            (patent_id, f"Title-only patent {patent_id}"),
        )

    rows = migrated_conn.execute(
        """
        SELECT patent_id, patent_number, quality_status
          FROM patent
         WHERE patent_id LIKE 'PAT-V026-PAGE-ONLY-%'
         ORDER BY patent_id
        """
    ).fetchall()

    assert rows == [
        {
            "patent_id": "PAT-V026-PAGE-ONLY-1",
            "patent_number": None,
            "quality_status": "needs_enrichment",
        },
        {
            "patent_id": "PAT-V026-PAGE-ONLY-2",
            "patent_number": None,
            "quality_status": "needs_enrichment",
        },
    ]


def test_v026_keeps_numbered_patent_uniqueness(migrated_conn) -> None:
    migrated_conn.execute(
        """
        INSERT INTO patent (
            patent_id,
            patent_number,
            title_clean,
            identity_status,
            quality_status
        )
        VALUES (
            'PAT-V026-NUMBERED-1',
            'CN-V026-0001',
            'Numbered patent 1',
            'unverified',
            'needs_enrichment'
        )
        """
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        migrated_conn.execute(
            """
            INSERT INTO patent (
                patent_id,
                patent_number,
                title_clean,
                identity_status,
                quality_status
            )
            VALUES (
                'PAT-V026-NUMBERED-2',
                'CN-V026-0001',
                'Numbered patent duplicate',
                'unverified',
                'needs_enrichment'
            )
            """
        )


def test_v026_downgrade_backfills_null_numbers_before_not_null(
    pg_dsn: str,
) -> None:
    config = _alembic_config()
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_dsn

    try:
        command.upgrade(config, "head")
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            conn.execute(
                """
                INSERT INTO patent (
                    patent_id,
                    patent_number,
                    title_clean,
                    identity_status,
                    quality_status
                )
                VALUES (
                    'PAT-V026-DOWNGRADE',
                    NULL,
                    'Downgrade-safe title-only patent',
                    'unverified',
                    'needs_enrichment'
                )
                """
            )
            conn.commit()

        command.downgrade(config, "V025")

        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            column = _patent_number_column(conn)
            row = conn.execute(
                """
                SELECT patent_id, patent_number
                  FROM patent
                 WHERE patent_id = 'PAT-V026-DOWNGRADE'
                """
            ).fetchone()

        assert column["is_nullable"] == "NO"
        assert row == {
            "patent_id": "PAT-V026-DOWNGRADE",
            "patent_number": "PAT-V026-DOWNGRADE",
        }
    finally:
        command.downgrade(config, "base")
        if original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_db_url
