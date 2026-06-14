from __future__ import annotations

from types import SimpleNamespace

import psycopg

from src.data_agents.professor.output_summaries import (
    run_output_summary_backfill,
    select_professors_for_research_vector_refresh,
)

_LEGACY_RUN_ID = "00000000-0000-0000-0000-000000000001"


class FakeLLMClient:
    def __init__(self, content: str):
        self.content = content
        self.calls = 0
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **_kwargs):
        self.calls += 1
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


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


def _insert_verified_paper(conn: psycopg.Connection, professor_id: str) -> None:
    conn.execute(
        """
        INSERT INTO paper (
            paper_id,
            title_clean,
            year,
            venue,
            abstract_clean,
            canonical_source,
            identity_status,
            run_id
        )
        VALUES (
            'PAPER-BACKFILL',
            'Backfill Paper',
            2026,
            'TestConf',
            'Paper abstract.',
            'openalex',
            'confirmed',
            %s
        )
        """,
        (_LEGACY_RUN_ID,),
    )
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
            'PAPER-BACKFILL',
            'verified',
            'official_publication_page',
            'listed on official profile',
            0.99,
            true,
            'rule_auto',
            %s
        )
        """,
        (professor_id, _LEGACY_RUN_ID),
    )


def _insert_verified_patent(conn: psycopg.Connection, professor_id: str) -> None:
    conn.execute(
        """
        INSERT INTO patent (
            patent_id,
            patent_number,
            title_clean,
            abstract_clean,
            technology_effect,
            ipc_codes,
            identity_status,
            run_id
        )
        VALUES (
            'PAT-BACKFILL',
            'CN202610099999A',
            'Backfill Patent',
            'Patent abstract.',
            'Improves robotic control.',
            ARRAY['G06N'],
            'confirmed',
            %s
        )
        """,
        (_LEGACY_RUN_ID,),
    )
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
            'PAT-BACKFILL',
            'inventor',
            'verified',
            'personal_homepage',
            'listed on official profile',
            'rule_auto'
        )
        """,
        (professor_id,),
    )


def test_output_summary_backfill_dry_run_reports_without_writing(
    pg_conn: psycopg.Connection,
) -> None:
    _reset_tables(pg_conn)
    _insert_professor(pg_conn, "PROF-BACKFILL")
    _insert_verified_paper(pg_conn, "PROF-BACKFILL")
    _insert_verified_patent(pg_conn, "PROF-BACKFILL")
    llm = FakeLLMClient(
        '{"paper_summary":"Paper dry-run summary.","patent_summary":"Patent dry-run summary."}'
    )

    report = run_output_summary_backfill(
        pg_conn,
        run_id=_LEGACY_RUN_ID,
        llm_client=llm,
        llm_model="test-model",
        dry_run=True,
        limit=1,
    )

    assert report.processed == 1
    assert report.skipped == 0
    assert report.failed == 0
    assert report.paper_summaries_written == 1
    assert report.patent_summaries_written == 1
    assert report.refresh_professor_ids == ()
    assert llm.calls == 1
    row = pg_conn.execute(
        """
        SELECT paper_summary, patent_summary
          FROM professor
         WHERE professor_id = 'PROF-BACKFILL'
        """
    ).fetchone()
    assert row == (None, None)


def test_output_summary_backfill_persists_changes_and_refresh_signal(
    pg_conn: psycopg.Connection,
) -> None:
    _reset_tables(pg_conn)
    _insert_professor(pg_conn, "PROF-BACKFILL")
    _insert_professor(pg_conn, "PROF-NO-LINKS")
    _insert_verified_paper(pg_conn, "PROF-BACKFILL")
    _insert_verified_patent(pg_conn, "PROF-BACKFILL")
    llm = FakeLLMClient(
        '{"paper_summary":"Paper persisted summary.","patent_summary":"Patent persisted summary."}'
    )

    report = run_output_summary_backfill(
        pg_conn,
        run_id=_LEGACY_RUN_ID,
        llm_client=llm,
        llm_model="test-model",
        dry_run=False,
        limit=10,
    )

    assert report.eligible == 1
    assert report.processed == 1
    assert report.failed == 0
    assert report.paper_summaries_written == 1
    assert report.patent_summaries_written == 1
    assert report.refresh_professor_ids == ("PROF-BACKFILL",)
    row = pg_conn.execute(
        """
        SELECT paper_summary, patent_summary
          FROM professor
         WHERE professor_id = 'PROF-BACKFILL'
        """
    ).fetchone()
    assert row == ("Paper persisted summary.", "Patent persisted summary.")
    assert select_professors_for_research_vector_refresh(
        pg_conn,
        run_id=_LEGACY_RUN_ID,
    ) == ("PROF-BACKFILL",)
