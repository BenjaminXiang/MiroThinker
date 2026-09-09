from __future__ import annotations

import os
from pathlib import Path
import socket
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
import pytest
from alembic import command
from alembic.config import Config

from src.data_agents.professor.link_backfill import (
    safe_upsert_professor_company_role,
    upsert_professor_company_role,
)


APP_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = APP_ROOT / "alembic.ini"
DATABASE_URL_SKIP_REASON = "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping Postgres integration tests"
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
_REAL_DB_NAMES = ("miroflow_real",)


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
        try:
            command.downgrade(_alembic_config(), "base")
        finally:
            if original_db_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_db_url


@pytest.fixture()
def pg_conn(pg_migrated, pg_dsn: str):
    del pg_migrated
    conn = psycopg.connect(pg_dsn, row_factory=dict_row)
    conn.execute("BEGIN")
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


class _NoExecuteConn:
    def __init__(self) -> None:
        self.executed = False

    def execute(self, *_args, **_kwargs):  # pragma: no cover - must not be called
        self.executed = True
        raise AssertionError("validation should fail before PG execute")


@pytest.fixture()
def no_execute_conn() -> _NoExecuteConn:
    return _NoExecuteConn()


def _valid_kwargs(**overrides) -> dict[str, object]:
    values: dict[str, object] = {
        "professor_id": "PROF-W13-2",
        "company_id": "COMP-W13-2",
        "role_type": "founder",
        "evidence_source_type": "professor_official_profile",
        "evidence_url": "https://sustech.edu.cn/prof/w13-2",
        "match_reason": "professor profile bio mentions founder role",
        "source_ref": "PROF-W13-2",
    }
    values.update(overrides)
    return values


def _seed_professor(conn, professor_id: str = "PROF-W13-2") -> None:
    conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            aliases,
            discipline_family,
            identity_status
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (professor_id) DO NOTHING
        """,
        (professor_id, "W13 Professor", [], "computer_science", "resolved"),
    )


def _seed_company(conn, company_id: str = "COMP-W13-2") -> None:
    conn.execute(
        """
        INSERT INTO company (
            company_id,
            canonical_name,
            aliases,
            identity_status
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (company_id) DO NOTHING
        """,
        (company_id, "W13 Company", [], "resolved"),
    )


def _role_row(conn, role_id: str) -> dict:
    row = conn.execute(
        "SELECT * FROM professor_company_role WHERE role_id = %s",
        (role_id,),
    ).fetchone()
    assert row is not None
    return row


def test_upsert_professor_company_role_inserts_new_row(pg_conn):
    _seed_professor(pg_conn)
    _seed_company(pg_conn)

    role_id = upsert_professor_company_role(pg_conn, **_valid_kwargs())

    assert str(UUID(role_id)) == role_id
    row = _role_row(pg_conn, role_id)
    assert row["professor_id"] == "PROF-W13-2"
    assert row["company_id"] == "COMP-W13-2"
    assert row["role_type"] == "founder"
    assert row["link_status"] == "candidate"
    assert row["evidence_url"] == "https://sustech.edu.cn/prof/w13-2"


def test_upsert_professor_company_role_is_idempotent_and_updates_evidence(pg_conn):
    _seed_professor(pg_conn)
    _seed_company(pg_conn)

    first_id = upsert_professor_company_role(pg_conn, **_valid_kwargs())
    first_row = _role_row(pg_conn, first_id)
    pg_conn.execute("SELECT pg_sleep(0.01)")

    second_id = upsert_professor_company_role(
        pg_conn,
        **_valid_kwargs(
            evidence_url="https://sustech.edu.cn/prof/w13-2-updated",
            match_reason="updated official profile bio founder evidence",
        ),
    )
    second_row = _role_row(pg_conn, second_id)

    assert second_id == first_id
    assert second_row["role_id"] == first_row["role_id"]
    assert second_row["created_at"] == first_row["created_at"]
    assert second_row["evidence_url"] == "https://sustech.edu.cn/prof/w13-2-updated"
    assert second_row["match_reason"] == "updated official profile bio founder evidence"
    assert second_row["updated_at"] >= first_row["updated_at"]


def test_upsert_rejects_invalid_role_type_before_pg(no_execute_conn):
    with pytest.raises(ValueError, match="role_type"):
        upsert_professor_company_role(no_execute_conn, **_valid_kwargs(role_type="cto"))
    assert not no_execute_conn.executed


def test_upsert_rejects_invalid_evidence_source_type_before_pg(no_execute_conn):
    with pytest.raises(ValueError, match="evidence_source_type"):
        upsert_professor_company_role(
            no_execute_conn,
            **_valid_kwargs(evidence_source_type="unknown"),
        )
    assert not no_execute_conn.executed


def test_upsert_rejects_empty_evidence_url_before_pg(no_execute_conn):
    with pytest.raises(ValueError, match="evidence_url"):
        upsert_professor_company_role(no_execute_conn, **_valid_kwargs(evidence_url=""))
    assert not no_execute_conn.executed


def test_upsert_rejects_empty_match_reason_before_pg(no_execute_conn):
    with pytest.raises(ValueError, match="match_reason"):
        upsert_professor_company_role(no_execute_conn, **_valid_kwargs(match_reason=""))
    assert not no_execute_conn.executed


def test_upsert_verified_state_sets_verified_by_and_verified_at(pg_conn):
    _seed_professor(pg_conn)
    _seed_company(pg_conn)

    role_id = upsert_professor_company_role(
        pg_conn,
        **_valid_kwargs(
            link_status="verified",
            verified_by="llm_auto",
            evidence_source_type="trusted_media",
            evidence_url="https://news.example.com/w13-2",
            match_reason="trusted media confirms professor founder role",
        ),
    )

    row = _role_row(pg_conn, role_id)
    assert row["link_status"] == "verified"
    assert row["verified_by"] == "llm_auto"
    assert row["verified_at"] is not None


def test_safe_upsert_catches_fk_violation_and_writes_pipeline_issue(pg_conn):
    _seed_company(pg_conn, "COMP-W13-2-FK")

    role_id = safe_upsert_professor_company_role(
        pg_conn,
        **_valid_kwargs(
            professor_id="PROF-W13-2-MISSING",
            company_id="COMP-W13-2-FK",
            source_ref="PROF-W13-2-MISSING",
        ),
    )

    assert role_id is None
    issue = pg_conn.execute(
        """
        SELECT stage, severity, description, evidence_snapshot
        FROM pipeline_issue
        WHERE description LIKE %s
        """,
        ("%PROF-W13-2-MISSING -> COMP-W13-2-FK%",),
    ).fetchone()
    assert issue is not None
    assert issue["severity"] == "medium"
    assert issue["stage"] in {"cross_domain_link", "data_quality_flag"}
    assert issue["evidence_snapshot"]["code"] == "pg_link_write_failed"
    assert issue["evidence_snapshot"]["requested_stage"] == "cross_domain_link"
