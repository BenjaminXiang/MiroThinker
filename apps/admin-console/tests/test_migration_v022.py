"""V022 professor_seed migration checks."""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import (
    _alembic_config,
    _load_alembic,
    _load_postgres_dependencies,
    _psycopg_dsn,
    _raw_database_url,
)


EXPECTED_COLUMNS = [
    "id",
    "school",
    "department",
    "seed_url",
    "last_run_at",
    "last_run_status",
    "created_at",
    "updated_at",
]


@pytest.fixture(scope="session")
def schema_ready() -> str:
    alembic_command, _ = _load_alembic()
    config = _alembic_config()
    pg_dsn = _psycopg_dsn(_raw_database_url())
    alembic_command.upgrade(config, "head")
    try:
        yield pg_dsn
    finally:
        alembic_command.downgrade(config, "base")


def _columns(conn: Any) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'professor_seed'
             ORDER BY ordinal_position
            """
        ).fetchall()
    ]


def test_v022_professor_seed_schema_and_status_check(schema_ready: str) -> None:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(schema_ready) as conn:
        assert _columns(conn) == EXPECTED_COLUMNS
        conn.execute(
            """
            INSERT INTO professor_seed (school, department, seed_url)
            VALUES ('SUSTech', NULL, 'https://example.test/sustech')
            """
        )
        row = conn.execute(
            """
            SELECT last_run_status, created_at IS NOT NULL, updated_at IS NOT NULL
              FROM professor_seed
             WHERE seed_url = 'https://example.test/sustech'
            """
        ).fetchone()
        assert row == ("never_run", True, True)

        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO professor_seed (school, seed_url, last_run_status)
                    VALUES ('SUSTech', 'https://example.test/bad', 'garbage')
                    """
                )


def test_v022_upgrade_and_downgrade_are_reversible(schema_ready: str) -> None:
    alembic_command, _ = _load_alembic()
    config = _alembic_config()
    psycopg, _, _, _ = _load_postgres_dependencies()

    alembic_command.downgrade(config, "V021")
    with psycopg.connect(schema_ready) as conn:
        assert (
            conn.execute("SELECT to_regclass('public.professor_seed')").fetchone()[0]
            is None
        )

    alembic_command.upgrade(config, "V022")
    with psycopg.connect(schema_ready) as conn:
        assert _columns(conn) == EXPECTED_COLUMNS

    alembic_command.downgrade(config, "V021")
    with psycopg.connect(schema_ready) as conn:
        assert (
            conn.execute("SELECT to_regclass('public.professor_seed')").fetchone()[0]
            is None
        )

    alembic_command.upgrade(config, "head")
