"""V022 professor_seed migration contract tests."""

from __future__ import annotations

from .conftest import _alembic_config, _load_alembic, _load_postgres_dependencies


def _professor_seed_columns(conn: object) -> list[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'professor_seed'
        ORDER BY ordinal_position
        """
    ).fetchall()
    return [row[0] for row in rows]


def test_v022_professor_seed_upgrade_downgrade_upgrade_is_idempotent(
    postgres_data_ready: str,
) -> None:
    alembic_command, _ = _load_alembic()
    config = _alembic_config()
    psycopg, _, _, _ = _load_postgres_dependencies()

    with psycopg.connect(postgres_data_ready) as conn:
        assert (
            conn.execute("SELECT to_regclass('professor_seed')").fetchone()[0]
            == "professor_seed"
        )
        assert _professor_seed_columns(conn) == [
            "id",
            "school",
            "department",
            "seed_url",
            "last_run_at",
            "last_run_status",
            "created_at",
            "updated_at",
        ]

    alembic_command.downgrade(config, "V021")

    with psycopg.connect(postgres_data_ready) as conn:
        assert conn.execute("SELECT to_regclass('professor_seed')").fetchone()[0] is None

    alembic_command.upgrade(config, "head")

    with psycopg.connect(postgres_data_ready) as conn:
        assert (
            conn.execute("SELECT to_regclass('professor_seed')").fetchone()[0]
            == "professor_seed"
        )


def test_v022_professor_seed_status_constraint_and_indexes(
    postgres_data_ready: str,
) -> None:
    psycopg, _, _, _ = _load_postgres_dependencies()

    with psycopg.connect(postgres_data_ready) as conn:
        constraints = {
            row[0]
            for row in conn.execute(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = 'professor_seed'::regclass
                """
            ).fetchall()
        }
        indexes = {
            row[0]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'professor_seed'
                """
            ).fetchall()
        }

        assert "ck_professor_seed_last_run_status" in constraints
        assert "ix_professor_seed_last_run_status" in indexes
        assert "ix_professor_seed_school" in indexes
        assert "uq_professor_seed_url" in indexes

        with conn.transaction():
            conn.execute(
                """
                INSERT INTO professor_seed (school, department, seed_url)
                VALUES (%s, %s, %s)
                """,
                (
                    "SUSTech",
                    None,
                    "https://example.com/professor-seed-v022-valid",
                ),
            )

        with conn.transaction():
            row = conn.execute(
                """
                SELECT last_run_status
                FROM professor_seed
                WHERE seed_url = %s
                """,
                ("https://example.com/professor-seed-v022-valid",),
            ).fetchone()
            assert row[0] == "never_run"

        try:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO professor_seed (
                        school, department, seed_url, last_run_status
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        "SUSTech",
                        None,
                        "https://example.com/professor-seed-v022-invalid",
                        "not_a_status",
                    ),
                )
        except psycopg.errors.CheckViolation:
            pass
        else:  # pragma: no cover - assertion path
            raise AssertionError("professor_seed must reject unknown run statuses")
