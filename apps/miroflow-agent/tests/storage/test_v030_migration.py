"""V030 professor lifecycle state migration checks."""

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
    APP_ROOT / "alembic" / "versions" / "V030_add_professor_lifecycle_state.py"
)

DATABASE_URL_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping"
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)


def _load_migration():
    spec = importlib.util.spec_from_file_location("v030_migration", _MIGRATION_PATH)
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


def test_v030_revision_chain() -> None:
    migration = _load_migration()

    assert migration.revision == "V030"
    assert migration.down_revision == "V029"


def test_v030_adds_professor_lifecycle_columns(migrated_conn) -> None:
    rows = migrated_conn.execute(
        """
        SELECT column_name, is_nullable, data_type, column_default
          FROM information_schema.columns
         WHERE table_name = 'professor'
           AND column_name IN ('lifecycle_state', 'lifecycle_merged_into_id')
         ORDER BY column_name
        """
    ).fetchall()

    assert [
        (
            row["column_name"],
            row["is_nullable"],
            row["data_type"],
            row["column_default"],
        )
        for row in rows
    ] == [
        ("lifecycle_merged_into_id", "YES", "text", None),
        ("lifecycle_state", "NO", "text", "'active'::text"),
    ]


def test_v030_lifecycle_constraints_and_defaults(migrated_conn) -> None:
    migrated_conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family
        )
        VALUES (
            'PROF-V030-ACTIVE',
            'V030 Active Professor',
            'computer_science'
        )
        """
    )
    active_row = migrated_conn.execute(
        """
        SELECT lifecycle_state, lifecycle_merged_into_id
          FROM professor
         WHERE professor_id = 'PROF-V030-ACTIVE'
        """
    ).fetchone()
    assert active_row == {
        "lifecycle_state": "active",
        "lifecycle_merged_into_id": None,
    }

    migrated_conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family,
            lifecycle_state
        )
        VALUES (
            'PROF-V030-ARCHIVED',
            'V030 Archived Professor',
            'computer_science',
            'archived'
        )
        """
    )

    migrated_conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family,
            lifecycle_state,
            lifecycle_merged_into_id
        )
        VALUES (
            'PROF-V030-MERGED',
            'V030 Merged Professor',
            'computer_science',
            'merged_to_other_school',
            'PROF-V030-ACTIVE'
        )
        """
    )

    with pytest.raises(psycopg.errors.CheckViolation):
        migrated_conn.execute(
            """
            INSERT INTO professor (
                professor_id,
                canonical_name,
                discipline_family,
                lifecycle_state
            )
            VALUES (
                'PROF-V030-BAD',
                'V030 Invalid Professor',
                'computer_science',
                'retired'
            )
            """
        )


def test_v030_lifecycle_merge_target_fk(migrated_conn) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrated_conn.execute(
            """
            INSERT INTO professor (
                professor_id,
                canonical_name,
                discipline_family,
                lifecycle_state,
                lifecycle_merged_into_id
            )
            VALUES (
                'PROF-V030-MISSING-TARGET',
                'V030 Missing Target Professor',
                'computer_science',
                'merged_to_other_school',
                'PROF-V030-NOPE'
            )
            """
        )


def test_v030_allows_lifecycle_admin_action_audit(migrated_conn) -> None:
    migrated_conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family
        )
        VALUES (
            'PROF-V030-AUDIT',
            'V030 Audit Professor',
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
            'PROF-V030-AUDIT',
            'set_lifecycle_state',
            'ops',
            'archived after manual verification',
            now()
        )
        """
    )

    row = migrated_conn.execute(
        """
        SELECT action, actor, note
          FROM professor_admin_action
         WHERE professor_id = 'PROF-V030-AUDIT'
        """
    ).fetchone()

    assert row == {
        "action": "set_lifecycle_state",
        "actor": "ops",
        "note": "archived after manual verification",
    }
