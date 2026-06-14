from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import psycopg

from src.data_agents.professor.fact_backfill import (
    ExtractedProfessorFact,
    ProfessorFactPersistenceReport,
    persist_extracted_professor_facts,
)

_LEGACY_RUN_ID = "00000000-0000-0000-0000-000000000001"


def _reset_professor_tables(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        TRUNCATE TABLE
            professor_paper_link,
            paper,
            professor_fact,
            professor_affiliation,
            professor,
            source_page
        RESTART IDENTITY CASCADE
        """
    )


def _insert_source_page(conn: psycopg.Connection, suffix: str) -> UUID:
    row = conn.execute(
        """
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at,
            is_official_source,
            run_id
        )
        VALUES (%s, 'official_profile', 'professor', %s, %s, true, %s)
        RETURNING page_id
        """,
        (
            f"https://example.edu/prof/{suffix}",
            f"PROF-{suffix}",
            datetime(2026, 5, 23, tzinfo=timezone.utc),
            _LEGACY_RUN_ID,
        ),
    ).fetchone()
    assert row is not None
    return row[0]


def _insert_professor(
    conn: psycopg.Connection,
    *,
    professor_id: str,
    page_id: UUID,
) -> None:
    conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family,
            primary_official_profile_page_id,
            profile_raw_text,
            run_id
        )
        VALUES (%s, %s, 'computer_science', %s, %s, %s)
        """,
        (
            professor_id,
            professor_id.replace("-", " "),
            page_id,
            "教育经历：清华大学博士。任 IEEE Fellow。",
            _LEGACY_RUN_ID,
        ),
    )


def _fact(
    *,
    professor_id: str,
    fact_type: str,
    value_raw: str,
    value_normalized: str | None = None,
    evidence_span: str = "evidence",
    confidence: float = 0.91,
) -> ExtractedProfessorFact:
    return ExtractedProfessorFact(
        professor_id=professor_id,
        fact_type=fact_type,
        value_raw=value_raw,
        value_normalized=value_normalized,
        evidence_span=evidence_span,
        confidence=confidence,
        source_profile_raw_text_len=100,
    )


def test_persist_extracted_professor_facts_writes_provenance_and_academic_position(
    pg_conn: psycopg.Connection,
) -> None:
    _reset_professor_tables(pg_conn)
    page_id = _insert_source_page(pg_conn, "A")
    _insert_professor(pg_conn, professor_id="PROF-A", page_id=page_id)

    report = persist_extracted_professor_facts(
        pg_conn,
        facts=(
            _fact(
                professor_id="PROF-A",
                fact_type="education",
                value_raw="清华大学博士",
                value_normalized="清华大学博士",
                evidence_span="教育经历：清华大学博士",
                confidence=0.92,
            ),
            _fact(
                professor_id="PROF-A",
                fact_type="academic_position",
                value_raw="IEEE Fellow",
                evidence_span="任 IEEE Fellow",
                confidence=0.86,
            ),
        ),
        source_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert isinstance(report, ProfessorFactPersistenceReport)
    assert report.facts_written == 2
    assert report.facts_updated == 0

    rows = pg_conn.execute(
        """
        SELECT fact_type, value_raw, value_normalized, source_page_id,
               evidence_span, confidence, status, run_id
          FROM professor_fact
         WHERE professor_id = 'PROF-A'
         ORDER BY fact_type
        """
    ).fetchall()
    assert rows == [
        (
            "academic_position",
            "IEEE Fellow",
            None,
            page_id,
            "任 IEEE Fellow",
            Decimal("0.86"),
            "active",
            UUID(_LEGACY_RUN_ID),
        ),
        (
            "education",
            "清华大学博士",
            "清华大学博士",
            page_id,
            "教育经历：清华大学博士",
            Decimal("0.92"),
            "active",
            UUID(_LEGACY_RUN_ID),
        ),
    ]


def test_persist_extracted_professor_facts_dedupes_by_normalized_key_not_provenance(
    pg_conn: psycopg.Connection,
) -> None:
    _reset_professor_tables(pg_conn)
    page_a = _insert_source_page(pg_conn, "A")
    page_b = _insert_source_page(pg_conn, "B")
    _insert_professor(pg_conn, professor_id="PROF-A", page_id=page_a)

    first = persist_extracted_professor_facts(
        pg_conn,
        facts=(
            _fact(
                professor_id="PROF-A",
                fact_type="award",
                value_raw="国家杰出青年科学基金获得者",
                value_normalized="National Science Fund for Distinguished Young Scholars",
                evidence_span="A 页面证据",
                confidence=0.71,
            ),
        ),
        source_page_id=page_a,
        run_id=_LEGACY_RUN_ID,
    )
    second = persist_extracted_professor_facts(
        pg_conn,
        facts=(
            _fact(
                professor_id="PROF-A",
                fact_type="award",
                value_raw="获国家杰出青年科学基金",
                value_normalized="National Science Fund for Distinguished Young Scholars",
                evidence_span="B 页面证据",
                confidence=0.93,
            ),
        ),
        source_page_id=page_b,
        run_id=_LEGACY_RUN_ID,
    )

    assert first.facts_written == 1
    assert second.facts_written == 0
    assert second.facts_updated == 1

    rows = pg_conn.execute(
        """
        SELECT value_raw, value_normalized, source_page_id,
               evidence_span, confidence
          FROM professor_fact
         WHERE professor_id = 'PROF-A'
           AND fact_type = 'award'
           AND status = 'active'
        """
    ).fetchall()
    assert rows == [
        (
            "获国家杰出青年科学基金",
            "National Science Fund for Distinguished Young Scholars",
            page_b,
            "B 页面证据",
            Decimal("0.93"),
        )
    ]


def test_persist_extracted_professor_facts_dedupes_missing_normalized_value_by_raw_key(
    pg_conn: psycopg.Connection,
) -> None:
    _reset_professor_tables(pg_conn)
    page_id = _insert_source_page(pg_conn, "A")
    _insert_professor(pg_conn, professor_id="PROF-A", page_id=page_id)

    report = persist_extracted_professor_facts(
        pg_conn,
        facts=(
            _fact(
                professor_id="PROF-A",
                fact_type="academic_position",
                value_raw=" IEEE Fellow ",
                evidence_span="first span",
            ),
            _fact(
                professor_id="PROF-A",
                fact_type="academic_position",
                value_raw="ieee   fellow",
                evidence_span="second span",
            ),
        ),
        source_page_id=page_id,
        run_id=_LEGACY_RUN_ID,
    )

    assert report.facts_written == 1
    assert report.facts_updated == 1
    assert (
        pg_conn.execute(
            """
            SELECT count(*)
              FROM professor_fact
             WHERE professor_id = 'PROF-A'
               AND fact_type = 'academic_position'
               AND status = 'active'
            """
        ).fetchone()[0]
        == 1
    )
