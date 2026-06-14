from __future__ import annotations

from datetime import datetime, timezone

import psycopg

from src.data_agents.patent.homepage_ingest import run_homepage_patent_ingest


NOW = datetime(2026, 5, 23, tzinfo=timezone.utc)


def _insert_professor_with_homepage(
    conn: psycopg.Connection,
    *,
    professor_id: str,
) -> None:
    page_id = conn.execute(
        """
        INSERT INTO source_page (
            url,
            page_role,
            owner_scope_kind,
            owner_scope_ref,
            fetched_at,
            http_status,
            is_official_source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING page_id
        """,
        (
            f"https://example.edu/{professor_id}",
            "personal_homepage",
            "professor",
            professor_id,
            NOW,
            200,
            True,
        ),
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO professor (
            professor_id,
            canonical_name,
            discipline_family,
            primary_official_profile_page_id,
            first_seen_at,
            last_refreshed_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            professor_id,
            f"Professor {professor_id}",
            "computer_science",
            page_id,
            NOW,
            NOW,
        ),
    )
    conn.execute(
        """
        INSERT INTO professor_affiliation (
            professor_id,
            institution,
            department,
            title,
            is_primary,
            is_current,
            source_page_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            professor_id,
            "南方科技大学",
            "Computer Science",
            "Professor",
            True,
            True,
            page_id,
        ),
    )


def test_homepage_patent_ingest_persists_title_only_and_is_idempotent(
    pg_conn: psycopg.Connection,
    monkeypatch,
) -> None:
    professor_id = "PROF-PAT-TITLE-ONLY"
    _insert_professor_with_homepage(pg_conn, professor_id=professor_id)

    html = """
    <html><body>
      <h2>专利</h2>
      <ul>
        <li><a href="/patents/title-only">一种无编号但应保留的方法</a></li>
        <li>一种有编号的方法，专利号 ZL202310012345.6，发明人：Professor PROF-PAT-TITLE-ONLY</li>
      </ul>
    </body></html>
    """
    monkeypatch.setattr(
        "src.data_agents.patent.homepage_ingest.fetch_homepage_html",
        lambda _url: html,
    )

    first = run_homepage_patent_ingest(
        pg_conn,
        prof_id=professor_id,
        dry_run=False,
    )
    second = run_homepage_patent_ingest(
        pg_conn,
        prof_id=professor_id,
        dry_run=False,
    )

    assert first.patents_upserted_total == 2
    assert first.patents_skipped_no_id_total == 0
    assert first.links_written_total == 2
    assert first.pipeline_issues_filed == 0
    assert second.patents_upserted_total == 2
    assert second.patents_skipped_no_id_total == 0
    assert second.links_written_total == 2
    assert second.pipeline_issues_filed == 0

    patents = pg_conn.execute(
        """
        SELECT patent_id, patent_number, title_clean, identity_status, quality_status
          FROM patent
         WHERE title_clean IN (
             '一种无编号但应保留的方法',
             '一种有编号的方法'
         )
         ORDER BY patent_number NULLS FIRST
        """
    ).fetchall()
    assert [
        (
            row[1],
            row[2],
            row[3],
            row[4],
        )
        for row in patents
    ] == [
        (None, "一种无编号但应保留的方法", "unverified", "needs_enrichment"),
        (
            "ZL202310012345.6",
            "一种有编号的方法",
            "unverified",
            "needs_enrichment",
        ),
    ]

    link_rows = pg_conn.execute(
        """
        SELECT
            ppl.link_status,
            ppl.match_reason,
            ppl.evidence_url,
            ppl.evidence_anchor,
            patent.title_clean
          FROM professor_patent_link AS ppl
          JOIN patent ON patent.patent_id = ppl.patent_id
         WHERE ppl.professor_id = %s
         ORDER BY patent.patent_number NULLS FIRST
        """,
        (professor_id,),
    ).fetchall()
    assert link_rows == [
        (
            "verified",
            "prof_page_declaration",
            f"https://example.edu/{professor_id}",
            "https://example.edu/patents/title-only",
            "一种无编号但应保留的方法",
        ),
        (
            "verified",
            "prof_page_declaration",
            f"https://example.edu/{professor_id}",
            None,
            "一种有编号的方法",
        ),
    ]

    issue_count = pg_conn.execute(
        """
        SELECT count(*)
          FROM pipeline_issue
         WHERE professor_id = %s
           AND description LIKE '[patent_missing_registration_number]%%'
        """,
        (professor_id,),
    ).fetchone()[0]
    assert issue_count == 0


def test_homepage_patent_ingest_promotes_title_only_when_number_appears(
    pg_conn: psycopg.Connection,
    monkeypatch,
) -> None:
    professor_id = "PROF-PAT-PROMOTE"
    _insert_professor_with_homepage(pg_conn, professor_id=professor_id)

    title_only_html = """
    <html><body>
      <h2>专利</h2>
      <ul>
        <li><a href="/patents/promote">一种后续补全编号的方法</a></li>
      </ul>
    </body></html>
    """
    numbered_html = """
    <html><body>
      <h2>专利</h2>
      <ul>
        <li><a href="/patents/promote">一种后续补全编号的方法，专利号 ZL202399999999.1</a></li>
      </ul>
    </body></html>
    """
    html_queue = [title_only_html, numbered_html]
    monkeypatch.setattr(
        "src.data_agents.patent.homepage_ingest.fetch_homepage_html",
        lambda _url: html_queue.pop(0),
    )

    first = run_homepage_patent_ingest(
        pg_conn,
        prof_id=professor_id,
        dry_run=False,
    )
    title_only_row = pg_conn.execute(
        """
        SELECT patent_id, patent_number
          FROM patent
         WHERE title_clean = '一种后续补全编号的方法'
        """
    ).fetchone()

    second = run_homepage_patent_ingest(
        pg_conn,
        prof_id=professor_id,
        dry_run=False,
    )

    promoted_rows = pg_conn.execute(
        """
        SELECT patent_id, patent_number, title_clean, quality_status
          FROM patent
         WHERE title_clean = '一种后续补全编号的方法'
         ORDER BY patent_id
        """
    ).fetchall()
    links = pg_conn.execute(
        """
        SELECT patent_id, evidence_url, evidence_anchor
          FROM professor_patent_link
         WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchall()

    assert first.patents_upserted_total == 1
    assert second.patents_upserted_total == 1
    assert title_only_row[1] is None
    assert promoted_rows == [
        (
            title_only_row[0],
            "ZL202399999999.1",
            "一种后续补全编号的方法",
            "needs_enrichment",
        )
    ]
    assert links == [
        (
            title_only_row[0],
            f"https://example.edu/{professor_id}",
            "https://example.edu/patents/promote",
        )
    ]
