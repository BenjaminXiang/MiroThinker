"""V025 professor_admin_action migration tests."""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

import pytest

from .conftest import (
    _alembic_config,
    _load_alembic,
    _load_postgres_dependencies,
    _psycopg_dsn,
    _raw_database_url,
)


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


@pytest.fixture()
def professor_fixture(schema_ready: str) -> str:
    psycopg, _, _, _ = _load_postgres_dependencies()
    professor_id = f"PROF-V025-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(schema_ready) as conn:
        conn.execute(
            """
            INSERT INTO professor (
                professor_id,
                canonical_name,
                discipline_family
            )
            VALUES (%s, %s, %s)
            """,
            (professor_id, "V025 Test Professor", "computer_science"),
        )
        conn.commit()
    try:
        yield professor_id
    finally:
        with psycopg.connect(schema_ready) as conn:
            conn.execute(
                "DELETE FROM professor_admin_action WHERE professor_id = %s",
                (professor_id,),
            )
            conn.execute(
                "DELETE FROM professor WHERE professor_id = %s",
                (professor_id,),
            )
            conn.commit()


def test_professor_admin_action_accepts_valid_actions(
    schema_ready: str,
    professor_fixture: str,
) -> None:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(schema_ready) as conn:
        action_id = str(uuid.uuid4())
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO professor_admin_action (
                    action_id,
                    professor_id,
                    action,
                    actor,
                    note,
                    observed_data_updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    action_id,
                    professor_fixture,
                    "confirm_ready",
                    "test-actor",
                    "confirmed during migration test",
                    datetime(2026, 5, 15, tzinfo=UTC),
                ),
            )
            row = conn.execute(
                """
                SELECT action, actor, note, observed_data_updated_at, created_at
                  FROM professor_admin_action
                 WHERE action_id = %s
                """,
                (action_id,),
            ).fetchone()
            conn.execute(
                "DELETE FROM professor_admin_action WHERE action_id = %s",
                (action_id,),
            )

    assert row[0] == "confirm_ready"
    assert row[1] == "test-actor"
    assert row[2] == "confirmed during migration test"
    assert row[3] == datetime(2026, 5, 15, tzinfo=UTC)
    assert row[4] is not None


def test_professor_admin_action_rejects_unknown_action(
    schema_ready: str,
    professor_fixture: str,
) -> None:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(schema_ready) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO professor_admin_action (
                        professor_id,
                        action,
                        actor,
                        observed_data_updated_at
                    )
                    VALUES (%s, %s, %s, now())
                    """,
                    (professor_fixture, "merge_record", "test-actor"),
                )


def test_professor_admin_action_has_professor_fk(schema_ready: str) -> None:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(schema_ready) as conn:
        row = conn.execute(
            """
            SELECT rc.delete_rule
              FROM information_schema.referential_constraints rc
              JOIN information_schema.table_constraints tc
                ON tc.constraint_catalog = rc.constraint_catalog
               AND tc.constraint_schema = rc.constraint_schema
               AND tc.constraint_name = rc.constraint_name
             WHERE tc.table_name = 'professor_admin_action'
               AND tc.constraint_type = 'FOREIGN KEY'
            """
        ).fetchone()

    assert row is not None
    assert row[0] == "SET NULL"


def test_v025_downgrade_drops_professor_admin_action(schema_ready: str) -> None:
    alembic_command, _ = _load_alembic()
    config = _alembic_config()
    psycopg, _, _, _ = _load_postgres_dependencies()

    with psycopg.connect(schema_ready) as conn:
        existed_before = conn.execute(
            "SELECT to_regclass('professor_admin_action') IS NOT NULL"
        ).fetchone()[0]
    assert existed_before

    alembic_command.downgrade(config, "V024")
    try:
        with psycopg.connect(schema_ready) as conn:
            gone = conn.execute(
                "SELECT to_regclass('professor_admin_action')"
            ).fetchone()[0]
        assert gone is None
    finally:
        alembic_command.upgrade(config, "head")
