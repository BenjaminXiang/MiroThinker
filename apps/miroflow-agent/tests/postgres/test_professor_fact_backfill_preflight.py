from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import psycopg

from src.data_agents.professor.fact_backfill import (
    TARGET_FACT_TYPES,
    compute_fact_backfill_preflight,
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
    profile_raw_text: str | None,
    profile_summary: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family,
            primary_official_profile_page_id,
            profile_raw_text,
            profile_summary,
            run_id
        )
        VALUES (%s, %s, 'computer_science', %s, %s, %s, %s)
        """,
        (
            professor_id,
            professor_id.replace("-", " "),
            page_id,
            profile_raw_text,
            profile_summary,
            _LEGACY_RUN_ID,
        ),
    )


def _insert_fact(
    conn: psycopg.Connection,
    *,
    professor_id: str,
    page_id: UUID,
    fact_type: str,
    status: str = "active",
) -> None:
    conn.execute(
        """
        INSERT INTO professor_fact (
            professor_id,
            fact_type,
            value_raw,
            value_normalized,
            source_page_id,
            evidence_span,
            confidence,
            status,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, 0.91, %s, %s)
        """,
        (
            professor_id,
            fact_type,
            f"{fact_type} for {professor_id}",
            f"{fact_type}:{professor_id}",
            page_id,
            f"{fact_type} evidence",
            status,
            _LEGACY_RUN_ID,
        ),
    )


def test_fact_backfill_preflight_counts_eligible_and_missing_fact_gaps(
    pg_conn: psycopg.Connection,
) -> None:
    _reset_professor_tables(pg_conn)
    page_a = _insert_source_page(pg_conn, "A")
    page_b = _insert_source_page(pg_conn, "B")
    page_c = _insert_source_page(pg_conn, "C")
    page_d = _insert_source_page(pg_conn, "D")

    _insert_professor(
        pg_conn,
        professor_id="PROF-A",
        page_id=page_a,
        profile_raw_text="教育经历：清华大学博士。曾任助理教授。",
        profile_summary=None,
    )
    _insert_professor(
        pg_conn,
        professor_id="PROF-B",
        page_id=page_b,
        profile_raw_text="研究方向为人工智能。曾获优秀青年基金。",
        profile_summary="人工智能方向教授。",
    )
    _insert_professor(
        pg_conn,
        professor_id="PROF-C",
        page_id=page_c,
        profile_raw_text=None,
        profile_summary=None,
    )
    _insert_professor(
        pg_conn,
        professor_id="PROF-D",
        page_id=page_d,
        profile_raw_text="   ",
        profile_summary="空 raw text should be skipped",
    )

    _insert_fact(pg_conn, professor_id="PROF-A", page_id=page_a, fact_type="education")
    _insert_fact(
        pg_conn,
        professor_id="PROF-A",
        page_id=page_a,
        fact_type="award",
        status="deprecated",
    )
    for fact_type in TARGET_FACT_TYPES:
        _insert_fact(pg_conn, professor_id="PROF-B", page_id=page_b, fact_type=fact_type)

    report = compute_fact_backfill_preflight(pg_conn)

    assert report.total_professors == 4
    assert report.eligible_professor_count == 2
    assert report.skipped_no_profile_raw_text_count == 2
    assert report.missing_profile_summary_count == 1
    assert report.active_fact_counts == {
        "education": 2,
        "work_experience": 1,
        "award": 1,
        "academic_position": 1,
    }
    assert report.missing_fact_counts == {
        "education": 0,
        "work_experience": 1,
        "award": 1,
        "academic_position": 1,
    }
    assert report.eligible_professor_ids == ("PROF-A", "PROF-B")
