"""V025 professor admin action migration checks."""

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
    APP_ROOT / "alembic" / "versions" / "V025_add_professor_admin_action.py"
)

DATABASE_URL_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v025_migration", _MIGRATION_PATH)
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
    command.upgrade(_alembic_config(), "V025")
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


def test_v025_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V025"
    assert migration.down_revision == "V024"


def test_v025_adds_professor_admin_action_table(migrated_conn) -> None:
    rows = migrated_conn.execute(
        """
        SELECT column_name, is_nullable, data_type
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'professor_admin_action'
           AND column_name IN (
               'action_id',
               'professor_id',
               'action',
               'actor',
               'note',
               'observed_data_updated_at',
               'created_at'
           )
         ORDER BY column_name
        """
    ).fetchall()

    assert [
        (row["column_name"], row["is_nullable"], row["data_type"]) for row in rows
    ] == [
        ("action", "NO", "text"),
        ("action_id", "NO", "uuid"),
        ("actor", "NO", "text"),
        ("created_at", "NO", "timestamp with time zone"),
        ("note", "YES", "text"),
        ("observed_data_updated_at", "NO", "timestamp with time zone"),
        ("professor_id", "YES", "text"),
    ]


def test_v025_action_enum_and_professor_fk(migrated_conn) -> None:
    migrated_conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family
        )
        VALUES (
            'PROF-V025-AUDIT',
            'V025 Audit Professor',
            'computer_science'
        )
        """
    )
    migrated_conn.execute(
        """
        INSERT INTO professor_admin_action (
            professor_id,
            action,
            actor,
            note,
            observed_data_updated_at
        )
        VALUES (
            'PROF-V025-AUDIT',
            'confirm_ready',
            'admin-console',
            'confirmed after review',
            now()
        )
        """
    )

    row = migrated_conn.execute(
        """
        SELECT professor_id, action, actor, note
          FROM professor_admin_action
         WHERE professor_id = 'PROF-V025-AUDIT'
        """
    ).fetchone()
    assert row == {
        "professor_id": "PROF-V025-AUDIT",
        "action": "confirm_ready",
        "actor": "admin-console",
        "note": "confirmed after review",
    }

    with pytest.raises(psycopg.errors.CheckViolation):
        migrated_conn.execute(
            """
            INSERT INTO professor_admin_action (
                professor_id,
                action,
                actor,
                observed_data_updated_at
            )
            VALUES (
                'PROF-V025-AUDIT',
                'set_lifecycle_state',
                'admin-console',
                now()
            )
            """
        )
    migrated_conn.rollback()

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrated_conn.execute(
            """
            INSERT INTO professor_admin_action (
                professor_id,
                action,
                actor,
                observed_data_updated_at
            )
            VALUES (
                'PROF-V025-MISSING',
                'flag_recrawl',
                'admin-console',
                now()
            )
            """
        )


def test_v025_downgrade_drops_admin_action_table(pg_dsn: str) -> None:
    config = _alembic_config()
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_dsn

    try:
        command.upgrade(config, "V025")
        command.downgrade(config, "V024")
        with psycopg.connect(pg_dsn) as conn:
            row = conn.execute(
                "SELECT to_regclass('professor_admin_action')"
            ).fetchone()
        assert row[0] is None
    finally:
        command.downgrade(config, "base")
        if original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_db_url
