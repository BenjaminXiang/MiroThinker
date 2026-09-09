from __future__ import annotations

import os
from pathlib import Path
import socket

import psycopg
import pytest
from alembic import command
from alembic.config import Config


APP_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = APP_ROOT / "alembic.ini"
DATABASE_URL_SKIP_REASON = (
    "Neither DATABASE_URL_TEST nor DATABASE_URL set; "
    "skipping Postgres integration tests"
)
NETWORK_SKIP_REASON = (
    "Network access blocked; skipping Postgres integration tests"
)
# Mock/real separation: tests must never touch real data. Prefer DATABASE_URL_TEST
# (pointing at miroflow_test_mock). Fall back to DATABASE_URL only for legacy
# invocations; CI sets DATABASE_URL_TEST explicitly and omits DATABASE_URL.
# See docs/plans/2026-04-18-002-real-data-e2e-and-db-separation.md §4.
_REAL_DB_NAMES = ("miroflow_real",)


def _raw_database_url() -> str:
    database_url = (
        os.environ.get("DATABASE_URL_TEST")
        or os.environ.get("DATABASE_URL")
    )
    if not database_url:
        pytest.skip(DATABASE_URL_SKIP_REASON)
    # Safety guard: refuse to run destructive migration cycles against the real db.
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


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    # These tests share one real database and run destructive migration cycles.
    return 0


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    cycle_tests = [
        item
        for item in items
        if item.name == "test_upgrade_downgrade_upgrade_cycle"
    ]
    other_tests = [
        item
        for item in items
        if item.name != "test_upgrade_downgrade_upgrade_cycle"
    ]
    items[:] = other_tests + cycle_tests


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """Read DATABASE_URL from env. If missing, pytest.skip the whole module."""
    _ensure_socket_api_available()
    return _psycopg_dsn(_raw_database_url())


@pytest.fixture(scope="session")
def pg_migrated(pg_dsn: str):
    """Run Alembic upgrade/downgrade around the test session.

    Alembic's env.py reads DATABASE_URL; if only DATABASE_URL_TEST is set,
    bridge it into DATABASE_URL for the duration of the session.
    """
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_dsn  # bridge: psycopg form works for both
    config = _alembic_config()
    command.upgrade(config, "head")
    try:
        yield
    finally:
        try:
            command.downgrade(config, "base")
        finally:
            if original_db_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_db_url


@pytest.fixture()
def pg_conn(pg_migrated, pg_dsn: str):
    """Yield a psycopg3 connection wrapped in a rollback-only transaction."""
    del pg_migrated
    conn = psycopg.connect(pg_dsn)
    conn.execute("BEGIN")
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
