from __future__ import annotations

import os
from pathlib import Path
import socket
from uuid import UUID

from alembic import command
from alembic.config import Config
import psycopg
from psycopg.rows import dict_row
import pytest

from src.data_agents.professor.fact_extraction import (
    ExtractedProfessorFact,
    FactExtractionError,
    extract_structured_facts,
    normalized_fact_key,
    parse_fact_extraction_response,
    persist_extracted_facts,
    preflight_professor_fact_backfill,
)


APP_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = APP_ROOT / "alembic.ini"
DATABASE_URL_SKIP_REASON = (
    "Neither DATABASE_URL_TEST nor DATABASE_URL set; skipping Postgres integration tests"
)
NETWORK_SKIP_REASON = "Network access blocked; skipping Postgres integration tests"
REAL_DB_NAMES = ("miroflow_real",)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self.content)


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)


class _FakeLLMClient:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)


def _raw_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL_TEST") or os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip(DATABASE_URL_SKIP_REASON)
    if any(name in database_url for name in REAL_DB_NAMES):
        pytest.fail(f"Refusing to run tests against a real-data database: {database_url!r}")
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
    del pg_dsn
    command.upgrade(_alembic_config(), "head")
    try:
        yield
    finally:
        command.downgrade(_alembic_config(), "base")


@pytest.fixture()
def pg_conn(pg_migrated, pg_dsn: str):
    del pg_migrated
    conn = psycopg.connect(pg_dsn, row_factory=dict_row)
    conn.execute("BEGIN")
    conn.execute(
        """
        TRUNCATE TABLE
            professor_admin_action,
            pipeline_issue,
            professor_fact,
            professor_affiliation,
            professor,
            source_page
        RESTART IDENTITY CASCADE
        """
    )
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _insert_pipeline_run(conn: psycopg.Connection, run_id: str) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_run (
            run_id, run_kind, run_scope, status, started_at, triggered_by
        )
        VALUES (%s, 'backfill_real', '{}'::jsonb, 'running', now(), 'test')
        ON CONFLICT (run_id) DO NOTHING
        """,
        (run_id,),
    )


def _insert_source_page(conn: psycopg.Connection, professor_id: str, suffix: str) -> UUID:
    row = conn.execute(
        """
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at,
            is_official_source,
            title
        )
        VALUES (%s, 'official_profile', 'professor', %s, now(), true, %s)
        RETURNING page_id
        """,
        (
            f"https://example.test/{professor_id}/{suffix}",
            professor_id,
            f"{professor_id} {suffix}",
        ),
    ).fetchone()
    assert row is not None
    return row["page_id"]


def _insert_professor(
    conn: psycopg.Connection,
    professor_id: str,
    *,
    raw_text: str | None,
    profile_summary: str | None = None,
    page_id: UUID | None = None,
) -> UUID | None:
    if page_id is None and raw_text is not None:
        page_id = _insert_source_page(conn, professor_id, "profile")
    conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            aliases,
            discipline_family,
            primary_official_profile_page_id,
            identity_status,
            quality_status,
            profile_summary,
            profile_raw_text
        )
        VALUES (%s, %s, %s, 'computer_science', %s, 'resolved',
                'needs_enrichment', %s, %s)
        """,
        (
            professor_id,
            professor_id.replace("-", " "),
            [],
            page_id,
            profile_summary,
            raw_text,
        ),
    )
    return page_id


def test_parse_fact_extraction_response_accepts_all_target_types_and_low_confidence() -> None:
    facts = parse_fact_extraction_response(
        """
        ```json
        {
          "facts": [
            {
              "fact_type": "education",
              "value_raw": "PhD, Example University",
              "value_normalized": "phd example university",
              "evidence_span": "received a PhD from Example University",
              "confidence": 0.91
            },
            {
              "fact_type": "work_experience",
              "value_raw": "Assistant Professor, Example Lab",
              "evidence_span": "Assistant Professor at Example Lab",
              "confidence": 0.72
            },
            {
              "fact_type": "award",
              "value_raw": "Young Scientist Award",
              "value_normalized": "Young Scientist Award",
              "evidence_span": "won the Young Scientist Award",
              "confidence": 0.30
            },
            {
              "fact_type": "academic_position",
              "value_raw": "Professor, SUSTech",
              "evidence_span": "Professor at SUSTech",
              "confidence": 1.0
            }
          ]
        }
        ```
        """
    )

    assert [fact.fact_type for fact in facts] == [
        "education",
        "work_experience",
        "award",
        "academic_position",
    ]
    assert facts[2].confidence == 0.30
    assert facts[0].value_normalized == "phd example university"


def test_parse_fact_extraction_response_rejects_malformed_or_unknown_output() -> None:
    with pytest.raises(FactExtractionError):
        parse_fact_extraction_response("not json")

    with pytest.raises(FactExtractionError):
        parse_fact_extraction_response(
            '{"facts":[{"fact_type":"project","value_raw":"x","evidence_span":"x","confidence":0.8}]}'
        )


def test_extract_structured_facts_uses_injected_llm_client() -> None:
    client = _FakeLLMClient(
        '{"facts":[{"fact_type":"education","value_raw":"PhD, Example University",'
        '"evidence_span":"PhD, Example University","confidence":0.9}]}'
    )

    facts = extract_structured_facts(
        "Biography text with PhD, Example University.",
        professor_name="Example Professor",
        llm_client=client,
        llm_model="mock-model",
        extra_body={"mock": True},
    )

    assert facts == [
        ExtractedProfessorFact(
            fact_type="education",
            value_raw="PhD, Example University",
            value_normalized=None,
            evidence_span="PhD, Example University",
            confidence=0.9,
        )
    ]
    call = client.chat.completions.calls[0]
    assert call["model"] == "mock-model"
    assert call["extra_body"] == {"mock": True}
    assert "Example Professor" in call["messages"][1]["content"]


def test_preflight_counts_eligible_rows_and_missing_fact_types(
    pg_conn: psycopg.Connection,
) -> None:
    run_id = "11111111-1111-1111-1111-111111111111"
    _insert_pipeline_run(pg_conn, run_id)
    first_page = _insert_professor(
        pg_conn,
        "PROF-FACT-1",
        raw_text="Professor has a PhD and several awards.",
        profile_summary=None,
    )
    _insert_professor(
        pg_conn,
        "PROF-FACT-2",
        raw_text="Professor has a position but no summary.",
        profile_summary="Existing summary",
    )
    _insert_professor(pg_conn, "PROF-NO-RAW", raw_text=None)
    pg_conn.execute(
        """
        INSERT INTO professor_fact (
            professor_id,
            fact_type,
            value_raw,
            value_normalized,
            source_page_id,
            evidence_span,
            confidence,
            run_id
        )
        VALUES (%s, 'education', 'PhD, Example University',
                'phd example university', %s, 'PhD, Example University', 0.90, %s)
        """,
        ("PROF-FACT-1", first_page, run_id),
    )

    report = preflight_professor_fact_backfill(pg_conn)

    assert report.total_professors == 3
    assert report.eligible_count == 2
    assert report.skipped_missing_profile_raw_text == 1
    assert report.missing_profile_summary_count == 1
    assert report.existing_active_fact_counts["education"] == 1
    assert report.missing_fact_counts["education"] == 1
    assert report.missing_fact_counts["award"] == 2


def test_persist_extracted_facts_is_idempotent_by_normalized_fact_key(
    pg_conn: psycopg.Connection,
) -> None:
    run_id = "22222222-2222-2222-2222-222222222222"
    _insert_pipeline_run(pg_conn, run_id)
    first_page = _insert_professor(
        pg_conn,
        "PROF-IDEMPOTENT",
        raw_text="Won the National Science Fund for Distinguished Young Scholars.",
    )
    second_page = _insert_source_page(pg_conn, "PROF-IDEMPOTENT", "secondary")

    first_report = persist_extracted_facts(
        pg_conn,
        professor_id="PROF-IDEMPOTENT",
        source_page_id=first_page,
        run_id=run_id,
        facts=[
            ExtractedProfessorFact(
                fact_type="award",
                value_raw="National Science Fund for Distinguished Young Scholars",
                value_normalized="National Science Fund for Distinguished Young Scholars",
                evidence_span="won the National Science Fund",
                confidence=0.87,
            )
        ],
    )
    second_report = persist_extracted_facts(
        pg_conn,
        professor_id="PROF-IDEMPOTENT",
        source_page_id=second_page,
        run_id=run_id,
        facts=[
            ExtractedProfessorFact(
                fact_type="award",
                value_raw=" National   Science Fund for Distinguished Young Scholars ",
                value_normalized="national science fund for distinguished young scholars",
                evidence_span="listed again in another paragraph",
                confidence=0.93,
            )
        ],
    )

    rows = pg_conn.execute(
        """
        SELECT fact_type, value_raw, value_normalized, source_page_id,
               evidence_span, confidence, status, run_id
          FROM professor_fact
         WHERE professor_id = 'PROF-IDEMPOTENT'
           AND fact_type = 'award'
           AND status = 'active'
        """
    ).fetchall()
    assert first_report.inserted == 1
    assert first_report.updated == 0
    assert second_report.inserted == 0
    assert second_report.updated == 1
    assert len(rows) == 1
    assert normalized_fact_key(rows[0]["value_raw"], rows[0]["value_normalized"]) == (
        "national science fund for distinguished young scholars"
    )
    assert rows[0]["source_page_id"] == second_page
    assert rows[0]["evidence_span"] == "listed again in another paragraph"
