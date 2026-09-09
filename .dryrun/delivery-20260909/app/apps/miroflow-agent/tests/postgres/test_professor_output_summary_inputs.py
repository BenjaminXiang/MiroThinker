from __future__ import annotations

import psycopg

from src.data_agents.professor.output_summaries import (
    select_eligible_paper_summary_inputs,
    select_eligible_patent_summary_inputs,
)

_LEGACY_RUN_ID = "00000000-0000-0000-0000-000000000001"


def _reset_tables(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        TRUNCATE TABLE
            professor_patent_link,
            professor_paper_link,
            patent,
            paper,
            professor
        RESTART IDENTITY CASCADE
        """
    )


def _insert_professor(conn: psycopg.Connection, professor_id: str) -> None:
    conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family,
            run_id
        )
        VALUES (%s, %s, 'computer_science', %s)
        """,
        (professor_id, professor_id.replace("-", " "), _LEGACY_RUN_ID),
    )


def _insert_paper(
    conn: psycopg.Connection,
    *,
    paper_id: str,
    title: str,
    year: int,
) -> None:
    conn.execute(
        """
        INSERT INTO paper (
            paper_id,
            title_clean,
            year,
            venue,
            abstract_clean,
            summary_zh,
            authors_display,
            canonical_source,
            identity_status,
            run_id
        )
        VALUES (%s, %s, %s, 'TestConf', %s, %s, 'A. Author', 'openalex', 'confirmed', %s)
        """,
        (
            paper_id,
            title,
            year,
            f"Abstract for {title}",
            f"Summary for {title}",
            _LEGACY_RUN_ID,
        ),
    )


def _link_paper(
    conn: psycopg.Connection,
    *,
    professor_id: str,
    paper_id: str,
    link_status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO professor_paper_link (
            professor_id,
            paper_id,
            link_status,
            evidence_source_type,
            match_reason,
            author_name_match_score,
            is_officially_listed,
            verified_by,
            run_id
        )
        VALUES (
            %s,
            %s,
            %s,
            'official_publication_page',
            'listed on official profile',
            0.99,
            true,
            CASE WHEN %s = 'verified' THEN 'rule_auto' ELSE NULL END,
            %s
        )
        """,
        (professor_id, paper_id, link_status, link_status, _LEGACY_RUN_ID),
    )


def _insert_patent(
    conn: psycopg.Connection,
    *,
    patent_id: str,
    patent_number: str,
    title: str,
) -> None:
    conn.execute(
        """
        INSERT INTO patent (
            patent_id,
            patent_number,
            title_clean,
            abstract_clean,
            technology_effect,
            ipc_codes,
            summary_text,
            summary_text_method,
            identity_status,
            run_id
        )
        VALUES (%s, %s, %s, %s, %s, ARRAY['G06N'], %s, 'fallback_template', 'confirmed', %s)
        """,
        (
            patent_id,
            patent_number,
            title,
            f"Abstract for {title}",
            f"Effect for {title}",
            f"Summary for {title}",
            _LEGACY_RUN_ID,
        ),
    )


def _link_patent(
    conn: psycopg.Connection,
    *,
    professor_id: str,
    patent_id: str,
    link_status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO professor_patent_link (
            professor_id,
            patent_id,
            link_role,
            link_status,
            evidence_source_type,
            match_reason,
            verified_by
        )
        VALUES (
            %s,
            %s,
            'inventor',
            %s,
            'personal_homepage',
            'listed on official profile',
            CASE WHEN %s = 'verified' THEN 'rule_auto' ELSE NULL END
        )
        """,
        (professor_id, patent_id, link_status, link_status),
    )


def test_select_eligible_paper_summary_inputs_uses_verified_links_only(
    pg_conn: psycopg.Connection,
) -> None:
    _reset_tables(pg_conn)
    _insert_professor(pg_conn, "PROF-T2")
    _insert_professor(pg_conn, "PROF-OTHER")
    _insert_paper(pg_conn, paper_id="PAPER-ACCEPTED", title="Accepted Paper", year=2025)
    _insert_paper(pg_conn, paper_id="PAPER-CANDIDATE", title="Candidate Paper", year=2024)
    _insert_paper(pg_conn, paper_id="PAPER-REJECTED", title="Rejected Paper", year=2023)
    _insert_paper(pg_conn, paper_id="PAPER-OTHER", title="Other Professor Paper", year=2026)
    _link_paper(
        pg_conn,
        professor_id="PROF-T2",
        paper_id="PAPER-ACCEPTED",
        link_status="verified",
    )
    _link_paper(
        pg_conn,
        professor_id="PROF-T2",
        paper_id="PAPER-CANDIDATE",
        link_status="candidate",
    )
    _link_paper(
        pg_conn,
        professor_id="PROF-T2",
        paper_id="PAPER-REJECTED",
        link_status="rejected",
    )
    _link_paper(
        pg_conn,
        professor_id="PROF-OTHER",
        paper_id="PAPER-OTHER",
        link_status="verified",
    )

    inputs = select_eligible_paper_summary_inputs(pg_conn, professor_id="PROF-T2")

    assert [(item.paper_id, item.title, item.year, item.link_status) for item in inputs] == [
        ("PAPER-ACCEPTED", "Accepted Paper", 2025, "verified")
    ]
    assert inputs[0].summary_zh == "Summary for Accepted Paper"
    assert inputs[0].abstract_clean == "Abstract for Accepted Paper"


def test_select_eligible_patent_summary_inputs_uses_verified_links_only(
    pg_conn: psycopg.Connection,
) -> None:
    _reset_tables(pg_conn)
    _insert_professor(pg_conn, "PROF-T2")
    _insert_professor(pg_conn, "PROF-OTHER")
    _insert_patent(
        pg_conn,
        patent_id="PAT-ACCEPTED",
        patent_number="CN202610000001A",
        title="Accepted Patent",
    )
    _insert_patent(
        pg_conn,
        patent_id="PAT-CANDIDATE",
        patent_number="CN202610000002A",
        title="Candidate Patent",
    )
    _insert_patent(
        pg_conn,
        patent_id="PAT-REJECTED",
        patent_number="CN202610000003A",
        title="Rejected Patent",
    )
    _insert_patent(
        pg_conn,
        patent_id="PAT-OTHER",
        patent_number="CN202610000004A",
        title="Other Professor Patent",
    )
    _link_patent(
        pg_conn,
        professor_id="PROF-T2",
        patent_id="PAT-ACCEPTED",
        link_status="verified",
    )
    _link_patent(
        pg_conn,
        professor_id="PROF-T2",
        patent_id="PAT-CANDIDATE",
        link_status="candidate",
    )
    _link_patent(
        pg_conn,
        professor_id="PROF-T2",
        patent_id="PAT-REJECTED",
        link_status="rejected",
    )
    _link_patent(
        pg_conn,
        professor_id="PROF-OTHER",
        patent_id="PAT-OTHER",
        link_status="verified",
    )

    inputs = select_eligible_patent_summary_inputs(pg_conn, professor_id="PROF-T2")

    assert [
        (item.patent_id, item.patent_number, item.title, item.link_status)
        for item in inputs
    ] == [("PAT-ACCEPTED", "CN202610000001A", "Accepted Patent", "verified")]
    assert inputs[0].summary_text == "Summary for Accepted Patent"
    assert inputs[0].technology_effect == "Effect for Accepted Patent"
