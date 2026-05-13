"""V023 pipeline_issue stage extension for seed adapter_missing reporting."""

from __future__ import annotations

import uuid
from typing import Any

from .conftest import _alembic_config, _load_alembic, _load_postgres_dependencies


def _insert_pipeline_issue(conn: Any, *, stage: str) -> str:
    issue_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO pipeline_issue (
            issue_id, institution, stage, severity, description, reported_by
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            issue_id,
            "SUSTech",
            stage,
            "medium",
            f"seed issue {stage} {issue_id}",
            "test_migration_v023.py",
        ),
    )
    return issue_id


def test_pipeline_issue_accepts_adapter_missing_stage(
    postgres_data_ready: str,
) -> None:
    psycopg, _, _, _ = _load_postgres_dependencies()
    with psycopg.connect(postgres_data_ready) as conn:
        with conn.transaction():
            issue_id = _insert_pipeline_issue(conn, stage="adapter_missing")
            row = conn.execute(
                "SELECT stage FROM pipeline_issue WHERE issue_id=%s",
                (issue_id,),
            ).fetchone()
            conn.execute("DELETE FROM pipeline_issue WHERE issue_id=%s", (issue_id,))
        assert row[0] == "adapter_missing"


def test_v023_downgrade_preserves_adapter_missing_issues_as_discovery(
    postgres_data_ready: str,
) -> None:
    alembic_command, _ = _load_alembic()
    config = _alembic_config()
    psycopg, _, _, _ = _load_postgres_dependencies()

    with psycopg.connect(postgres_data_ready) as conn:
        issue_id = _insert_pipeline_issue(conn, stage="adapter_missing")
        conn.commit()

    alembic_command.downgrade(config, "V022")

    with psycopg.connect(postgres_data_ready) as conn:
        row = conn.execute(
            "SELECT stage, description FROM pipeline_issue WHERE issue_id=%s",
            (issue_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "discovery"
    assert row[1].startswith("adapter_missing downgraded: ")

    alembic_command.upgrade(config, "head")
