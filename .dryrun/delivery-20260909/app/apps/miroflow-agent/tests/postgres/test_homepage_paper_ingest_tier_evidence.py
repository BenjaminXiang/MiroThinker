from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import psycopg
import pytest

from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.paper.homepage_ingest import run_homepage_paper_ingest
from src.data_agents.paper.title_resolver import ResolvedPaper
from src.data_agents.professor.canonical_writer import (
    upsert_source_page_for_url,
    write_professor_bundle,
)
from src.data_agents.professor.homepage_publications import HomepagePublication
from src.data_agents.professor.models import (
    EnrichedProfessorProfile,
    OfficialAnchorProfile,
)


NOW = datetime(2026, 5, 23, tzinfo=timezone.utc)
RUN_ID = "00000000-0000-0000-0000-000000000001"


def _insert_professor_with_homepage(
    conn: psycopg.Connection,
    *,
    professor_id: str,
    page_role: str,
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
            page_role,
            "professor",
            professor_id,
            NOW,
            200,
            page_role == "official_profile",
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


def _publication(
    title: str,
    *,
    pdf_url: str | None = None,
    source_url: str = "https://example.edu/prof",
) -> HomepagePublication:
    return HomepagePublication(
        raw_title=title,
        clean_title=title,
        authors_text="Professor Test",
        venue_text="Example Conference",
        year=2026,
        source_url=source_url,
        source_anchor=None,
        pdf_url=pdf_url,
    )


def _resolved(title: str, doi_suffix: str) -> ResolvedPaper:
    return ResolvedPaper(
        title=title,
        doi=f"10.1000/{doi_suffix}",
        openalex_id=f"W-{doi_suffix}",
        arxiv_id=None,
        abstract="Abstract from resolver.",
        pdf_url=None,
        authors=("Professor Test",),
        year=2026,
        venue="Example Conference",
        match_confidence=0.99,
        match_source="openalex",
    )


@pytest.mark.parametrize(
    ("page_role", "expected_evidence_source"),
    [
        ("official_profile", "prof_homepage_tier2"),
        ("personal_homepage", "prof_homepage_tier3"),
    ],
)
def test_homepage_paper_ingest_writes_tier_evidence_to_postgres(
    pg_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    page_role: str,
    expected_evidence_source: str,
) -> None:
    professor_id = f"PROF-{page_role}"
    title = f"Tier Evidence Paper {page_role}"
    _insert_professor_with_homepage(
        pg_conn,
        professor_id=professor_id,
        page_role=page_role,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        lambda _url: "<html></html>",
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        lambda _html, *, page_url: [_publication(title, source_url=page_url)],
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        lambda *_args, **_kwargs: _resolved(title, page_role),
    )

    report = run_homepage_paper_ingest(pg_conn, prof_id=professor_id)

    assert report.papers_linked_total == 1
    row = pg_conn.execute(
        """
        SELECT ppl.evidence_source_type, p.title_clean, ppl.evidence_page_id, sp.page_id
        FROM professor_paper_link ppl
        JOIN paper p ON p.paper_id = ppl.paper_id
        JOIN source_page sp ON sp.url = %s
        WHERE ppl.professor_id = %s
        """,
        (f"https://example.edu/{professor_id}", professor_id),
    ).fetchone()
    assert row is not None
    assert row[0] == expected_evidence_source
    assert row[1] == title
    assert row[2] == row[3]


def test_canonical_writer_persists_publication_evidence_source_pages(
    pg_conn: psycopg.Connection,
) -> None:
    official_profile_url = "https://www.sustech.edu.cn/zh/faculties/source-plumbing.html"
    official_pub_url = (
        "https://www.sustech.edu.cn/zh/faculties/source-plumbing/publications.html"
    )
    lab_pub_url = "https://lab.example.org/source-plumbing/publications"
    official_page_id = upsert_source_page_for_url(
        pg_conn,
        url=official_profile_url,
        page_role="official_profile",
        owner_scope_kind="professor",
        owner_scope_ref="PROF-SOURCE-PLUMBING",
        fetched_at=NOW,
        is_official_source=True,
        run_id=RUN_ID,
    )
    enriched = EnrichedProfessorProfile(
        name="Source Plumbing",
        institution="南方科技大学",
        department="Computer Science",
        title="Professor",
        homepage="https://lab.example.org/source-plumbing/",
        research_directions=["Systems"],
        publication_evidence_urls=[official_pub_url, lab_pub_url],
        evidence_urls=[official_profile_url],
        field_provenance={
            f"source_page_role:{official_pub_url}": "official_publication_page",
            f"source_page_role:{lab_pub_url}": "lab_homepage",
        },
        profile_url=official_profile_url,
        roster_source="https://www.sustech.edu.cn/zh/faculties/",
        extraction_status="structured",
        official_anchor_profile=OfficialAnchorProfile(
            source_url=official_profile_url,
            bio_text="Source Plumbing is a professor.",
            sparse_anchor=False,
        ),
    )

    report = write_professor_bundle(
        pg_conn,
        enriched=enriched,
        official_profile_page_id=official_page_id,
        run_id=RUN_ID,
    )

    rows = pg_conn.execute(
        """
        SELECT url, page_role, owner_scope_kind, owner_scope_ref, is_official_source
        FROM source_page
        WHERE url IN (%s, %s)
        ORDER BY url
        """,
        (lab_pub_url, official_pub_url),
    ).fetchall()
    assert rows == [
        (lab_pub_url, "lab_homepage", "professor", report.professor_id, False),
        (
            official_pub_url,
            "official_publication_page",
            "professor",
            report.professor_id,
            True,
        ),
    ]


def test_homepage_paper_ingest_files_issue_for_unknown_homepage_tier(
    pg_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    professor_id = "PROF-UNKNOWN-TIER"
    _insert_professor_with_homepage(
        pg_conn,
        professor_id=professor_id,
        page_role="unknown",
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        lambda _url: "<html></html>",
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        lambda _html, *, page_url: [_publication("Unknown Tier Paper")],
    )

    report = run_homepage_paper_ingest(pg_conn, prof_id=professor_id)

    assert report.papers_linked_total == 0
    assert report.pipeline_issues_filed == 1
    assert (
        pg_conn.execute(
            """
            SELECT count(*)
            FROM professor_paper_link
            WHERE professor_id = %s
            """,
            (professor_id,),
        ).fetchone()[0]
        == 0
    )
    issue = pg_conn.execute(
        """
        SELECT stage, evidence_snapshot->>'issue_type'
        FROM pipeline_issue
        WHERE professor_id = %s
        """,
        (professor_id,),
    ).fetchone()
    assert issue == ("paper_attribution", "missing_homepage_tier")


def test_homepage_paper_ingest_attaches_professor_page_pdf_url_to_full_text_fetch(
    pg_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    professor_id = "PROF-PDF-LINK"
    title = "Professor Page Direct PDF Paper"
    pdf_url = "https://example.edu/prof/papers/direct-paper.pdf"
    _insert_professor_with_homepage(
        pg_conn,
        professor_id=professor_id,
        page_role="official_profile",
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        lambda _url: "<html></html>",
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        lambda _html, *, page_url: [_publication(title, pdf_url=pdf_url)],
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        lambda *_args, **_kwargs: _resolved(title, "direct-pdf"),
    )

    seen_pdf_urls: list[str | None] = []

    def fake_fetch_full_text(resolved: ResolvedPaper, *, paper_id: str) -> FullTextExtract:
        seen_pdf_urls.append(resolved.pdf_url)
        return FullTextExtract(
            paper_id=paper_id,
            abstract="Abstract from professor page PDF.",
            intro="Intro from professor page PDF.",
            pdf_url=resolved.pdf_url,
            pdf_sha256=None,
            source="prof_page_pdf",
            fetch_error=None,
        )

    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text",
        fake_fetch_full_text,
    )

    report = run_homepage_paper_ingest(pg_conn, prof_id=professor_id)

    assert report.papers_linked_total == 1
    assert report.full_text_fetched_total == 1
    assert seen_pdf_urls == [pdf_url]
    row = pg_conn.execute(
        """
        SELECT pft.pdf_url, pft.source
        FROM paper_full_text pft
        JOIN paper p ON p.paper_id = pft.paper_id
        WHERE p.title_clean = %s
        """,
        (title,),
    ).fetchone()
    assert row == (pdf_url, "prof_page_pdf")


def test_homepage_paper_ingest_persists_pdf_fetch_cap_issues(
    pg_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    professor_id = "PROF-PDF-CAP"
    publications = [
        _publication(f"Direct PDF Paper {idx}", pdf_url=f"https://example.edu/p{idx}.pdf")
        for idx in range(1, 4)
    ]
    _insert_professor_with_homepage(
        pg_conn,
        professor_id=professor_id,
        page_role="official_profile",
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        lambda _url: "<html></html>",
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        lambda _html, *, page_url: publications,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        lambda title, *_args, **_kwargs: _resolved(
            title,
            title.lower().replace(" ", "-"),
        ),
    )

    seen_pdf_urls: list[str | None] = []

    def fake_fetch_full_text(resolved: ResolvedPaper, *, paper_id: str) -> FullTextExtract:
        seen_pdf_urls.append(resolved.pdf_url)
        return FullTextExtract(
            paper_id=paper_id,
            abstract="Abstract from professor page PDF.",
            intro="Intro from professor page PDF.",
            pdf_url=resolved.pdf_url,
            pdf_sha256=None,
            source="prof_page_pdf",
            fetch_error=None,
        )

    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text",
        fake_fetch_full_text,
    )

    report = run_homepage_paper_ingest(
        pg_conn,
        prof_id=professor_id,
        prof_page_pdf_fetch_cap=1,
    )

    assert report.papers_linked_total == 3
    assert report.full_text_fetched_total == 1
    assert report.pipeline_issues_filed == 2
    assert seen_pdf_urls == ["https://example.edu/p1.pdf"]
    issues = pg_conn.execute(
        """
        SELECT evidence_snapshot->>'issue_type',
               evidence_snapshot->'details'->>'pdf_url'
        FROM pipeline_issue
        WHERE professor_id = %s
        ORDER BY evidence_snapshot->'details'->>'pdf_url'
        """,
        (professor_id,),
    ).fetchall()
    assert issues == [
        ("pdf_fetch_cap_exceeded", "https://example.edu/p2.pdf"),
        ("pdf_fetch_cap_exceeded", "https://example.edu/p3.pdf"),
    ]


def test_homepage_paper_ingest_persists_raw_pdf_blob_once_by_sha(
    pg_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    professor_id = "PROF-PDF-BLOB"
    pdf_bytes = b"%PDF-1.4 duplicate professor page PDF"
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    publications = [
        _publication(f"Blob PDF Paper {idx}", pdf_url=f"https://example.edu/blob{idx}.pdf")
        for idx in range(1, 4)
    ]
    _insert_professor_with_homepage(
        pg_conn,
        professor_id=professor_id,
        page_role="official_profile",
    )
    monkeypatch.setenv("MIROFLOW_RAW_PDF_STORE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        lambda _url: "<html></html>",
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        lambda _html, *, page_url: publications,
    )
    monkeypatch.setattr(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        lambda title, *_args, **_kwargs: _resolved(
            title,
            title.lower().replace(" ", "-"),
        ),
    )
    monkeypatch.setattr(
        "src.data_agents.paper.full_text_fetcher._download_pdf",
        lambda _url, *, http_client: (pdf_bytes, pdf_sha256),
    )
    monkeypatch.setattr(
        "src.data_agents.paper.full_text_fetcher._extract_text_from_pdf_bytes",
        lambda _bytes: (
            "Abstract\nBlob-backed abstract.\n\n"
            "Introduction\nBlob-backed intro.\n\n"
            "Methods\nM."
        ),
    )

    report = run_homepage_paper_ingest(pg_conn, prof_id=professor_id)

    assert report.papers_linked_total == 3
    assert report.full_text_fetched_total == 3
    rows = pg_conn.execute(
        """
        SELECT p.title_clean,
               pft.pdf_sha256,
               pft.pdf_byte_size,
               pft.raw_pdf_storage_ref,
               pft.source
        FROM paper p
        JOIN paper_full_text pft ON pft.paper_id = p.paper_id
        WHERE p.title_clean LIKE 'Blob PDF Paper%'
        ORDER BY p.title_clean
        """
    ).fetchall()
    assert len(rows) == 3
    assert {row[1] for row in rows} == {pdf_sha256}
    assert {row[2] for row in rows} == {len(pdf_bytes)}
    assert {row[4] for row in rows} == {"prof_page_pdf"}
    blob_refs = {row[3] for row in rows}
    assert len(blob_refs) == 1
    assert pdf_sha256 in next(iter(blob_refs))
    stored = list(tmp_path.rglob(f"{pdf_sha256}.pdf"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == pdf_bytes
