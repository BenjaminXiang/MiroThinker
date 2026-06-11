"""RED-phase tests for M2.4 Unit 6 — run_homepage_paper_ingest orchestrator.

Hermetic tests — mock psycopg.Connection + the M2.1/M2.2/M2.3 helpers + M2.4's
homepage HTTP. Verify branch logic: skip-via-resume, per-prof savepoint isolation,
pipeline_issue filing, dry-run writes nothing, full-text skip when row exists.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest

from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.paper.homepage_ingest import (
    IngestReport,
    _fetch_professors,
    _is_malformed_publication_title,
    _normalize_homepage_publication_for_ingest,
    run_homepage_paper_ingest,
)
from src.data_agents.paper.title_resolver import ResolvedPaper
from src.data_agents.professor.homepage_publications import HomepagePublication


# ---------- Fixtures ---------------------------------------------------------


def _prof_row(
    *,
    prof_id: str | None = None,
    name: str = "Test Prof",
    institution: str = "南方科技大学",
    homepage_url: str = "https://example.edu/prof/x",
    homepage_page_role: str | None = "official_profile",
    homepage_page_id: UUID | None = None,
    profile_raw_text: str | None = None,
) -> dict:
    return {
        "professor_id": prof_id or str(uuid.uuid4()),
        "canonical_name": name,
        "institution": institution,
        "homepage_url": homepage_url,
        "homepage_page_role": homepage_page_role,
        "homepage_page_id": homepage_page_id,
        "profile_raw_text": profile_raw_text,
    }


def _pub(
    *,
    clean_title: str = "Deep Learning for Images",
    authors_text: str | None = "A. Smith, J. Doe",
    venue_text: str | None = "NeurIPS",
    year: int | None = 2023,
    pdf_url: str | None = None,
    source_url: str = "https://example.edu/prof/x",
) -> HomepagePublication:
    return HomepagePublication(
        raw_title=f"[1] {clean_title} [J]",
        clean_title=clean_title,
        authors_text=authors_text,
        venue_text=venue_text,
        year=year,
        source_url=source_url,
        source_anchor=None,
        pdf_url=pdf_url,
    )


def _resolved(
    title: str = "Deep Learning for Images",
    doi: str = "10.1/x",
) -> ResolvedPaper:
    return ResolvedPaper(
        title=title,
        doi=doi,
        openalex_id="W1",
        arxiv_id="2310.00001",
        abstract="Abstract.",
        pdf_url=None,
        authors=("A. Smith", "J. Doe"),
        year=2023,
        venue="NeurIPS",
        match_confidence=0.93,
        match_source="openalex",
    )


def _full_text() -> FullTextExtract:
    return FullTextExtract(
        paper_id="paper:doi:10.1/x",
        abstract="Abstract.",
        intro="Intro.",
        pdf_url="https://arxiv.org/pdf/2310.00001.pdf",
        pdf_sha256="a" * 64,
        source="arxiv",
        fetch_error=None,
    )


def _mock_conn_with_profs(prof_rows: list[dict]):
    """psycopg.Connection shape: cursor/execute both return something iterable."""
    conn = MagicMock()
    # SELECT query returns prof rows
    cursor = MagicMock()
    cursor.fetchall.return_value = prof_rows
    cursor.fetchone.return_value = None  # default for existence checks
    conn.execute.return_value = cursor

    @contextmanager
    def _fake_transaction(savepoint: bool = False):  # noqa: ARG001
        yield
    conn.transaction.side_effect = lambda **kw: _fake_transaction(**kw)
    return conn


class _FetchRows:
    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class _SelectorConn:
    def __init__(self):
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, query: str, params: tuple):
        self.executed.append((query, params))
        if "owner_scope_kind" not in query:
            return _FetchRows(
                [
                    (
                        "PROF-1",
                        "Test Prof",
                        "南方科技大学",
                        "https://example.edu/prof/official",
                        "official_profile",
                    )
                ]
            )
        return _FetchRows(
            [
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://example.edu/prof/official",
                    "official_profile",
                ),
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://example.edu/prof/publications",
                    "official_publication_page",
                ),
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://lab.example.edu/test-prof",
                    "lab_homepage",
                ),
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://people.example.edu/test-prof",
                    "personal_homepage",
                ),
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://people.example.edu/test-prof/",
                    "personal_homepage",
                ),
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://scholar.google.com/citations?user=test",
                    "personal_homepage",
                ),
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://www.researchgate.net/profile/Test-Prof",
                    "personal_homepage",
                ),
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://chaogou.github.io/cv/联系邮箱：",
                    "personal_homepage",
                ),
            ]
        )


def test_fetch_professors_defaults_to_primary_official_profile_page_only():
    conn = _SelectorConn()

    rows = _fetch_professors(conn, institution=None, limit=None, prof_id=None)

    assert [row["homepage_url"] for row in rows] == [
        "https://example.edu/prof/official"
    ]
    assert "owner_scope_kind" not in conn.executed[0][0]


def test_fetch_professors_can_include_owned_homepage_publication_pages():
    conn = _SelectorConn()

    rows = _fetch_professors(
        conn,
        institution=None,
        limit=None,
        prof_id=None,
        include_owned_homepage_pages=True,
    )

    assert [row["homepage_url"] for row in rows] == [
        "https://example.edu/prof/official",
        "https://example.edu/prof/publications",
        "https://lab.example.edu/test-prof",
        "https://people.example.edu/test-prof",
    ]
    assert [row["homepage_page_role"] for row in rows] == [
        "official_profile",
        "official_publication_page",
        "lab_homepage",
        "personal_homepage",
    ]
    assert "owner_scope_ref = p.professor_id::text" in conn.executed[0][0]


def test_fetch_professors_filters_department_and_seed_via_affiliation_run_scope():
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = []

    rows = _fetch_professors(
        conn,
        institution="电子科技大学（深圳）高等研究院",
        department="计算机技术",
        seed_id=26,
        limit=3,
        prof_id=None,
    )

    assert rows == []
    sql, params = conn.execute.call_args.args
    assert "latest_seed_run AS (" in sql
    assert "seed_professors AS (" in sql
    assert "JOIN latest_seed_run lr ON lr.run_id = pa.run_id" in sql
    assert "JOIN seed_professors seed_scope" in sql
    assert "p.run_id = latest_seed_run.run_id" not in sql
    assert "COALESCE(seed_scope.institution, primary_aff.institution) ILIKE %s" in sql
    assert "COALESCE(seed_scope.department, primary_aff.department) ILIKE %s" in sql
    assert params == (
        "26",
        "%电子科技大学（深圳）高等研究院%",
        "%计算机技术%",
        3,
    )


def test_fetch_professors_applies_department_and_seed_to_owned_page_scope():
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = []

    _fetch_professors(
        conn,
        institution="深圳大学",
        department="机电与控制工程学院",
        seed_id="14",
        limit=None,
        prof_id="PROF-1",
        include_owned_homepage_pages=True,
    )

    sql, params = conn.execute.call_args.args
    assert "WITH latest_seed_run AS (" in sql
    assert "seed_professors AS (" in sql
    assert "selected_professors AS (" in sql
    assert "JOIN seed_professors seed_scope" in sql
    assert "sp.owner_scope_kind = 'professor'" in sql
    assert "COALESCE(seed_scope.department, primary_aff.department) ILIKE %s" in sql
    assert params == (
        "14",
        "%深圳大学%",
        "%机电与控制工程学院%",
        "PROF-1",
        "official_publication_page",
        "personal_homepage",
        "lab_homepage",
    )


# ---------- Happy paths ------------------------------------------------------


def test_happy_path_single_prof_five_pubs_all_resolvable(tmp_path):
    """1 prof, 5 pubs, all resolve → 5 upsert_paper + 5 link + 5 full_text writes."""
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    pubs = [_pub(clean_title=f"Paper {i}") for i in range(5)]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ) as m_open, patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ) as m_close, patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html"
    ) as m_extract, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists"
    ) as m_ft_exists, patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ) as m_fetch_full, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ) as m_upsert_full:
        m_open.return_value = uuid.uuid4()
        m_fetch_html.return_value = "<html></html>"
        m_extract.return_value = pubs
        m_resolve.side_effect = [_resolved(title=p.clean_title) for p in pubs]
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)
        m_ft_exists.return_value = False
        m_fetch_full.return_value = _full_text()

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
        )

        assert isinstance(report, IngestReport)
        assert report.profs_processed == 1
        assert report.papers_linked_total == 5
        assert report.full_text_fetched_total == 5
        assert report.pipeline_issues_filed == 0
        assert m_upsert_paper.call_count == 5
        assert m_upsert_link.call_count == 5
        assert m_upsert_full.call_count == 5
        m_close.assert_called_once()
        assert m_close.call_args.kwargs.get("status") == "succeeded"


def test_checkpoint_append_happens_after_professor_commit(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    commit_counts_at_checkpoint: list[int] = []

    def _record_checkpoint(*_args, **_kwargs):
        commit_counts_at_checkpoint.append(conn.commit.call_count)

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run",
        return_value=uuid.uuid4(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub()],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper",
        return_value=MagicMock(paper_id="paper:doi:x", is_new=True),
    ), patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch(
        "src.data_agents.paper.homepage_ingest._append_checkpoint_line",
        side_effect=_record_checkpoint,
    ):
        run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
        )

    assert commit_counts_at_checkpoint == [2]
    assert conn.commit.call_count == 3


def test_official_page_ingest_does_not_truncate_more_than_five_pubs(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    pubs = [_pub(clean_title=f"Official Paper {index}") for index in range(1, 8)]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=pubs,
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ):
        m_resolve.side_effect = [_resolved(title=pub.clean_title) for pub in pubs]
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
        )

        assert report.papers_linked_total == 7
        assert m_resolve.call_count == 7
        assert m_upsert_paper.call_count == 7
        assert m_upsert_link.call_count == 7
        for call in m_upsert_link.call_args_list:
            assert call.kwargs["link_status"] == "verified"
            assert call.kwargs["is_officially_listed"] is True


def test_homepage_ingest_accepts_publication_extractor_injection(tmp_path):
    prof = _prof_row(homepage_url="https://www.sigs.tsinghua.edu.cn/sample/main.htm")
    conn = _mock_conn_with_profs([prof])
    pubs = [_pub(clean_title="Source Grounded LLM Paper")]
    seen: dict[str, str] = {}

    def fake_publication_extractor(html: str, *, page_url: str):
        seen["html"] = html
        seen["page_url"] = page_url
        return pubs

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html>official page</html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html"
    ) as m_default_extract, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(title="Source Grounded LLM Paper"),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ):
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
        )

        assert report.papers_linked_total == 1
        assert seen == {
            "html": "<html>official page</html>",
            "page_url": "https://www.sigs.tsinghua.edu.cn/sample/main.htm",
        }
        m_default_extract.assert_not_called()
        assert m_upsert_link.called


def test_homepage_ingest_uses_selected_source_page_id_as_relation_evidence(tmp_path):
    page_id = UUID("11111111-1111-1111-1111-111111111111")
    prof = _prof_row(
        homepage_url="https://example.edu/prof/x",
        homepage_page_role="personal_homepage",
        homepage_page_id=page_id,
    )
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub(source_url="https://example.edu/prof/x")],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
        )

    assert report.papers_linked_total == 1
    assert m_upsert_link.call_args.kwargs["evidence_page_id"] == page_id


def test_homepage_ingest_follows_same_root_publication_page(tmp_path):
    second_hop_page_id = UUID("22222222-2222-2222-2222-222222222222")
    prof = _prof_row(
        prof_id="PROF-SUSTECH-TANGB",
        homepage_url="https://faculty.sustech.edu.cn/tangb/",
        homepage_page_role="personal_homepage",
    )
    conn = _mock_conn_with_profs([prof])
    homepage_html = """
    <html><body>
      <a href="pub.html">Publications</a>
      <a href="/other/pub.html">Other publications</a>
      <a href="https://external.example/pub.html">External publications</a>
    </body></html>
    """
    publication_html = """
    <html><body>
      <ul><li>Reliable Publication from Publication Page, Test Journal, 2025.</li></ul>
    </body></html>
    """
    pub = _pub(
        clean_title="Reliable Publication from Publication Page",
        source_url="https://faculty.sustech.edu.cn/tangb/pub.html",
    )

    def fake_publication_extractor(html: str, *, page_url: str):
        if page_url == "https://faculty.sustech.edu.cn/tangb/":
            assert html == homepage_html
            return []
        assert page_url == "https://faculty.sustech.edu.cn/tangb/pub.html"
        assert html == publication_html
        return [pub]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(title="Reliable Publication from Publication Page"),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.upsert_source_page_for_url",
        return_value=second_hop_page_id,
        create=True,
    ) as m_upsert_source_page, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_fetch_html.side_effect = [homepage_html, publication_html]
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
        )

        assert report.papers_linked_total == 1
        assert [call.args[0] for call in m_fetch_html.call_args_list] == [
            "https://faculty.sustech.edu.cn/tangb/",
            "https://faculty.sustech.edu.cn/tangb/pub.html",
        ]
        assert m_upsert_paper.call_args.kwargs["title_clean"] == (
            "Reliable Publication from Publication Page"
        )
        assert m_upsert_link.call_args.kwargs["evidence_source_type"] == (
            "prof_homepage_tier3"
        )
        assert m_upsert_link.call_args.kwargs["evidence_page_id"] == (
            second_hop_page_id
        )
        m_upsert_source_page.assert_called_once()
        assert m_upsert_source_page.call_args.kwargs["url"] == (
            "https://faculty.sustech.edu.cn/tangb/pub.html"
        )
        assert m_upsert_source_page.call_args.kwargs["page_role"] == (
            "personal_homepage"
        )
        assert m_upsert_source_page.call_args.kwargs["owner_scope_kind"] == "professor"
        assert m_upsert_source_page.call_args.kwargs["owner_scope_ref"] == (
            "PROF-SUSTECH-TANGB"
        )
        assert m_upsert_source_page.call_args.kwargs["is_official_source"] is False


def test_homepage_ingest_does_not_follow_second_hop_pdf_pages(tmp_path):
    prof = _prof_row(
        homepage_url="http://zenghp.org/",
        homepage_page_role="personal_homepage",
    )
    conn = _mock_conn_with_profs([prof])
    homepage_html = """
    <html><body>
      <a href="/research/huge/paper.pdf">Publication PDF</a>
      <a href="/publications.html">Publications</a>
    </body></html>
    """
    publication_html = """
    <html><body>
      <ul><li>Reliable Publication from HTML Page, Test Journal, 2025.</li></ul>
    </body></html>
    """
    pub = _pub(
        clean_title="Reliable Publication from HTML Page",
        source_url="http://zenghp.org/publications.html",
    )

    def fake_publication_extractor(html: str, *, page_url: str):
        if page_url == "http://zenghp.org/":
            assert html == homepage_html
            return []
        assert page_url == "http://zenghp.org/publications.html"
        assert html == publication_html
        return [pub]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(title="Reliable Publication from HTML Page"),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_source_page_for_url",
        return_value=UUID("22222222-2222-2222-2222-222222222222"),
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_fetch_html.side_effect = [homepage_html, publication_html]
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
        )

        assert report.papers_linked_total == 1
        assert [call.args[0] for call in m_fetch_html.call_args_list] == [
            "http://zenghp.org/",
            "http://zenghp.org/publications.html",
        ]


def test_homepage_ingest_second_hop_read_error_is_nonfatal(tmp_path):
    prof = _prof_row(
        homepage_url="https://faculty.sustech.edu.cn/tangb/",
        homepage_page_role="personal_homepage",
    )
    conn = _mock_conn_with_profs([prof])
    homepage_html = """
    <html><body>
      <a href="pub.html">Publications</a>
      <p>Profile page content.</p>
    </body></html>
    """
    main_pub = _pub(
        clean_title="Reliable Publication from Profile Page",
        source_url="https://faculty.sustech.edu.cn/tangb/",
    )

    def fake_publication_extractor(html: str, *, page_url: str):
        assert page_url == "https://faculty.sustech.edu.cn/tangb/"
        assert html == homepage_html
        return [main_pub]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(title="Reliable Publication from Profile Page"),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_fetch_html.side_effect = [
            homepage_html,
            httpx.ReadError("second hop disconnected"),
        ]
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
        )

        assert report.papers_linked_total == 1
        assert [call.args[0] for call in m_fetch_html.call_args_list] == [
            "https://faculty.sustech.edu.cn/tangb/",
            "https://faculty.sustech.edu.cn/tangb/pub.html",
        ]


def test_homepage_ingest_dedupes_publications_across_second_hop_pages(tmp_path):
    prof = _prof_row(
        homepage_url="https://faculty.sustech.edu.cn/tangb/",
        homepage_page_role="personal_homepage",
    )
    conn = _mock_conn_with_profs([prof])
    homepage_html = """
    <html><body>
      <a href="pub.html">Publications</a>
    </body></html>
    """
    publication_html = """
    <html><body>
      <ul><li>Duplicate Publication Title, Test Journal, 2025.</li></ul>
    </body></html>
    """
    first_pub = _pub(
        clean_title="Duplicate Publication Title",
        source_url="https://faculty.sustech.edu.cn/tangb/",
    )
    second_pub = _pub(
        clean_title="Duplicate Publication Title",
        source_url="https://faculty.sustech.edu.cn/tangb/pub.html",
    )

    def fake_publication_extractor(_html: str, *, page_url: str):
        if page_url == "https://faculty.sustech.edu.cn/tangb/":
            return [first_pub]
        if page_url == "https://faculty.sustech.edu.cn/tangb/pub.html":
            return [second_pub]
        raise AssertionError(page_url)

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(title="Duplicate Publication Title"),
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_fetch_html.side_effect = [homepage_html, publication_html]
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
        )

        assert report.papers_linked_total == 1
        assert m_resolve.call_count == 1
        assert m_upsert_paper.call_count == 1
        assert m_upsert_link.call_count == 1


def test_homepage_ingest_does_not_follow_cross_root_publication_links(tmp_path):
    prof = _prof_row(
        homepage_url="https://faculty.sustech.edu.cn/tangb/",
        homepage_page_role="personal_homepage",
    )
    conn = _mock_conn_with_profs([prof])
    homepage_html = """
    <html><body>
      <a href="/other/pub.html">Other publications</a>
      <a href="https://example.com/pub.html">External publications</a>
    </body></html>
    """

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_fetch_html.return_value = homepage_html

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=lambda _html, *, page_url: [],
        )

        assert report.papers_linked_total == 0
        assert [call.args[0] for call in m_fetch_html.call_args_list] == [
            "https://faculty.sustech.edu.cn/tangb/"
        ]
        m_resolve.assert_not_called()
        m_upsert_paper.assert_not_called()
        m_upsert_link.assert_not_called()


def test_homepage_ingest_disables_arxiv_title_search_for_bulk_titles(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    pub = _pub(clean_title="Official Homepage Paper")

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[pub],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=None,
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
        )

        assert m_resolve.call_args.kwargs["enable_arxiv_title_search"] is False


def test_malformed_author_list_title_is_blocked_before_resolver(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    malformed_pub = HomepagePublication(
        raw_title=(
            "1- M. Abdelaziz, T. Wang, W. Anwaar, A. Elazab*. Robust attention "
            "transfer neural networks for diagnosis of Alzheimer's disease from "
            "structural magnetic resonance images, Engineering Applications of "
            "Artificial Intelligence, 164, 113260, 2026"
        ),
        clean_title="M. Abdelaziz, T. Wang, W. Anwaar, A. Elazab",
        authors_text=None,
        venue_text=(
            "Robust attention transfer neural networks for diagnosis of Alzheimer's "
            "disease from structural magnetic resonance images"
        ),
        year=2026,
        source_url="https://www.sigs.tsinghua.edu.cn/Ahmed%20Elazab/main.psp",
        source_anchor=None,
    )

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[malformed_pub],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
        )

        assert report.papers_linked_total == 0
        assert report.pipeline_issues_filed >= 1
        issue_types = [call.kwargs["issue_type"] for call in m_issue.call_args_list]
        assert "malformed_publication_title" in issue_types
        m_resolve.assert_not_called()
        m_upsert_paper.assert_not_called()
        m_upsert_link.assert_not_called()


def test_homepage_ingest_normalizes_leading_contribution_marker_before_write(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    marked_pub = _pub(clean_title="** Fair Division with Prioritized Agents")

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[marked_pub],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_resolve.return_value = _resolved(title="Fair Division with Prioritized Agents")
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
        )

        assert report.papers_linked_total == 1
        assert m_resolve.call_args.args[0] == "Fair Division with Prioritized Agents"
        assert m_upsert_paper.call_args.kwargs["title_clean"] == (
            "Fair Division with Prioritized Agents"
        )


def test_homepage_ingest_blocks_publication_marker_legend_before_resolver(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    legend_pub = _pub(
        clean_title=(
            "In publications marked with '**', authors are ordered alphabetically, "
            "or authors beyond the first two are omitted"
        ),
        authors_text=None,
        venue_text=None,
        year=None,
    )

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[legend_pub],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists"
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
        )

        assert report.papers_linked_total == 0
        assert report.pipeline_issues_filed >= 1
        assert "malformed_publication_title" in [
            call.kwargs["issue_type"] for call in m_issue.call_args_list
        ]
        m_resolve.assert_not_called()
        m_upsert_paper.assert_not_called()
        m_upsert_link.assert_not_called()


def test_malformed_guard_allows_valid_comma_title_with_authors():
    publication = _pub(
        clean_title=(
            "Gaussian Universal Features, Canonical Correlations, and Common "
            "Information"
        ),
        authors_text="S.-L. Huang, L. Zheng, G. Wornell",
        year=2018,
    )

    assert not _is_malformed_publication_title(publication)


def test_malformed_guard_blocks_author_list_title_with_context():
    publication = _pub(
        clean_title=(
            "Kevin Cheung, Jennifer Gloeckner Powers, Zhengqiao Zhao, and Gail "
            "Rosen"
        ),
        authors_text=(
            "Cullen CM, Kawalpreet K Aneja, Sinem Beyhan, Clara E. Cho"
        ),
        year=2020,
    )

    assert _is_malformed_publication_title(publication)


def test_malformed_guard_blocks_author_only_titles_without_explicit_punctuation():
    for title in (
        "Yong Tian etc",
        "Mingwang Wang etc",
        "Zhihui Xu and Weiwei Zheng",
        "Sun Wei and Xu Zhihui",
    ):
        publication = _pub(clean_title=title, authors_text=None, year=None)

        assert _is_malformed_publication_title(publication), title


@pytest.mark.parametrize(
    "clean_title",
    [
        "PtolemaiosSarrigiannis",
        "Chen* (2012)",
        "D?bniak T, Duffy DL",
        "andJianan Y. Qu*",
        "Yang iu, Chao lu, Wiliam Wella lu, * Hongmei liu* and Decheng Wu*",
        "Watkins SC, Demetris AJ, Hussey GS, Badylak SF, Turnquist HR",
        "Reichenbach DK",
    ],
)
def test_malformed_guard_blocks_sustech_author_fragment_titles(clean_title):
    publication = _pub(
        clean_title=clean_title,
        authors_text=None,
        venue_text="Journal of Clinical Investigation",
        year=2024,
    )

    assert _is_malformed_publication_title(publication), clean_title


@pytest.mark.parametrize(
    ("clean_title", "venue_text"),
    [
        (
            "Yuchen ji, Xiansong Lai",
            "Fine-detailed Neural Indoor Scene Reconstruction with Multi-level "
            "Hash Grid and Volumetric Features",
        ),
        (
            "xujie zhang, Fuwei Zhao",
            "DreamFit: Garment-Centric Human Generation via a Lightweight "
            "Anything-Dressing Encoder",
        ),
        (
            "Fan Yang and Yuhan Dong",
            "Joint probabilistic shaping and nonlinear compensation for optical "
            "fiber communication systems",
        ),
    ],
)
def test_malformed_guard_blocks_author_list_title_even_with_author_context(
    clean_title,
    venue_text,
):
    publication = _pub(
        clean_title=clean_title,
        authors_text=clean_title,
        venue_text=venue_text,
        year=2024,
    )

    assert _is_malformed_publication_title(publication), clean_title


def test_malformed_guard_blocks_student_marked_author_list_with_mixed_context():
    publication = _pub(
        clean_title="Xu （学生）, T. Fan, M. Xu, L. Zeng",
        authors_text="Y. F",
        venue_text=(
            "SpiderCNN: Deep Learning on Point Sets with Parameterized "
            "Convolutional Filters, ECCV 2018 (全球计算机视觉三大会议之一，谷歌学术引用数 > 800 次)"
        ),
        year=2018,
    )

    assert _is_malformed_publication_title(publication)


@pytest.mark.parametrize(
    "clean_title",
    [
        "Book Chapters",
        "Invited Talks",
        "Manufacturing",
        "Healthcare and Service Systems",
        "Social Networks",
        "Transportation and Disaster Management",
        "Degree Source",
        "In Chinese",
        "SCI JCR Q1",
        "JCR Q2",
        "JCR: Q1/IF:11.446",
        "JCR:Q1/IF:11.7",
        "November 1",
        "Nov. 1",
        "中国注册会计师（内地）",
        "中国香港注册会计师资格考试全科通过（可豁免 ACCA ）",
        "美国注册会计师资格考试全科通过（加州）",
        "年， ISBN 978-7-5608-4835-8 ， Page 164-173",
        "pp. 154-169",
        "38, 1821. [doi]",
        "63, e202 303073",
        "Ed., 2021, 60, 9875-9880",
        "Soc. 2016, 138, 8774–8780",
        "…, Lu, C, …",
        "m resolution land cover mapping",
        "a nd Miao Lixin",
        "In arXiv preprint",
        "In Proceedings of the AAAI Conference on Artificial Intelligence (AAAI), 2025",
        "Proceedings of the European Conference on Computer Vision (ECCV), 2022",
        "In IEEE Transactions on Circuits and Systems for Video Technology (T-CSVT)",
        "In NeuroComputing",
        "an C. Z. Ning",
        "Xu （学生）, T. Fan, M. Xu, L. Zeng",
        "Bagdi, P. R.; Zhang",
        "IJCV * 1, AIJ * 1, TIP * 4, TVCG * 1",
        "Lang S u n",
        "etc. Logical Relation Inference and Multiview Information Interaction "
        "for Domain Adaptation Person Re-Identification",
    ],
)
def test_malformed_guard_blocks_section_headings_and_metadata_labels(clean_title):
    publication = _pub(clean_title=clean_title, authors_text=None, venue_text=None)

    assert _is_malformed_publication_title(publication), clean_title


@pytest.mark.parametrize(
    "clean_title",
    [
        "Personal and Ubiquitous Computing",
        "Angew. Chem",
        "Angew Chem Int Edit",
        "Applied Health Economics and Health Policy",
        "Periodica Polytechnica Architecture",
        "Synfacts highlights",
        "自然 · 通讯",
    ],
)
def test_malformed_guard_blocks_short_venue_only_title(clean_title):
    publication = _pub(
        clean_title=clean_title,
        authors_text="A. Smith, B. Chen",
        venue_text=clean_title,
        year=2024,
    )

    assert _is_malformed_publication_title(publication), clean_title


@pytest.mark.parametrize(
    ("clean_title", "venue_text"),
    [
        ("Personal and Ubiquitous Computing", "2004"),
        ("Applied Health Economics and Health Policy", None),
    ],
)
def test_malformed_guard_blocks_known_venue_only_title_without_matching_venue(
    clean_title,
    venue_text,
):
    publication = _pub(
        clean_title=clean_title,
        authors_text="A. Smith, B. Chen",
        venue_text=venue_text,
        year=2024,
    )

    assert _is_malformed_publication_title(publication), clean_title


@pytest.mark.parametrize(
    "clean_title",
    [
        "况漠, 缪立新, 况达, & 张志贤",
        "况漠, 缪立新, & 林署青",
        "张灿荣, 钟明, & 缪立新",
        "陈进博, 戚铭尧, & 缪立新",
    ],
)
def test_malformed_guard_blocks_chinese_author_list_titles(clean_title):
    publication = _pub(
        clean_title=clean_title,
        authors_text=None,
        venue_text="交通运输系统工程与信息",
        year=2023,
    )

    assert _is_malformed_publication_title(publication), clean_title


def test_malformed_guard_blocks_semicolon_author_fragment_with_author_context():
    publication = _pub(
        clean_title="Bagdi, P. R.; Zhang",
        authors_text="S. Niu, H. Zhang, W. Xu",
        venue_text="G.; Liu, J.; Yang, S.; Fang, X.* Nature Communications 2021",
        year=2021,
    )

    assert _is_malformed_publication_title(publication)


@pytest.mark.parametrize(
    "clean_title,authors_text,venue_text",
    [
        (
            "Virgil, S. C.; Grubbs",
            "X. Y. Xing, C. Xu, B. Chen, C. C. Li",
            "R. H. J. Am Chem. Soc. 2018, 140, 17782-17789",
        ),
        (
            "11, 1158-1166. (equal contribution)",
            "Xiao-Yang Dong, Yu-Feng Zhang, Xin-Yuan Liu. Nat. Chem",
            None,
        ),
    ],
)
def test_malformed_guard_blocks_bibliographic_or_author_tail_fragments(
    clean_title,
    authors_text,
    venue_text,
):
    publication = HomepagePublication(
        raw_title=clean_title,
        clean_title=clean_title,
        authors_text=authors_text,
        venue_text=venue_text,
        year=2019,
        source_url="https://www.sustech.edu.cn/zh/faculties/example.html",
        source_anchor=None,
    )

    assert _is_malformed_publication_title(publication)


def test_malformed_guard_blocks_patent_rows_even_when_title_is_long():
    publication = HomepagePublication(
        raw_title=(
            "Patent: Adaptive quantization device for federated learning, "
            "CN202410123456.7"
        ),
        clean_title="Adaptive quantization device for federated learning",
        authors_text=None,
        venue_text="Patent CN202410123456.7",
        year=2024,
        source_url="https://example.edu/prof/publications",
        source_anchor=None,
    )

    assert _is_malformed_publication_title(publication)


@pytest.mark.parametrize(
    "clean_title",
    [
        "Backtesting",
        "The Collider",
        "Supercool sulfur",
        "Tournaments",
        "Emerging Planetarism",
        "Intelligent Making and Robotic Structure",
    ],
)
def test_malformed_guard_allows_valid_short_titles(clean_title):
    publication = _pub(
        clean_title=clean_title,
        authors_text="A. Smith, B. Chen",
        venue_text="Journal of Applied Research",
        year=2023,
    )

    assert not _is_malformed_publication_title(publication), clean_title


def test_malformed_guard_allows_valid_and_title_with_long_bibliographic_venue():
    publication = _pub(
        clean_title="Intelligent Making and Robotic Structure",
        authors_text="Gao Yan, Guo Xin",
        venue_text=(
            "Periodica Polytechnica Architecture, Published by the Faculty of "
            "Architecture of the Budapest University of Technology and Economics, "
            "ISSN Number: 1789-3437, Budapest, Hungary, 2016"
        ),
        year=2016,
    )

    assert not _is_malformed_publication_title(publication)


def test_reference_style_title_normalization_strips_author_prefix_and_venue_suffix():
    publication = _pub(
        clean_title=(
            "Jiawei Wu, Zhi Jin* Unsupervised Variational Translator for "
            "Bridging Image Restoration and High-Level Vision Tasks European "
            "Conference on Computer Vision(ECCV) 2024. [paper] [code]"
        ),
        authors_text="Jiawei Wu, Zhi Jin",
        venue_text=None,
        year=2024,
    )

    normalized = _normalize_homepage_publication_for_ingest(publication)

    assert normalized.clean_title == (
        "Unsupervised Variational Translator for Bridging Image Restoration "
        "and High-Level Vision Tasks"
    )
    assert not _is_malformed_publication_title(normalized)


def test_official_profile_evidence_source_type_is_tier2(tmp_path):
    """link writer must preserve official profile page evidence as Tier 2."""
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html"
    ) as m_extract, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists"
    ) as m_ft_exists, patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ):
        m_fetch_html.return_value = "<html></html>"
        m_extract.return_value = [_pub()]
        m_resolve.return_value = _resolved()
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)
        m_ft_exists.return_value = True  # skip full text fetch

        run_homepage_paper_ingest(conn, resume_checkpoint_path=tmp_path / "c.jsonl")

        assert m_upsert_link.called
        kwargs = m_upsert_link.call_args.kwargs
        assert kwargs.get("evidence_source_type") == "prof_homepage_tier2"


def test_personal_homepage_evidence_source_type_is_tier3(tmp_path):
    """link writer must preserve personal/lab homepage evidence as Tier 3."""
    prof = _prof_row(homepage_page_role="personal_homepage")
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub()],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ):
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        run_homepage_paper_ingest(conn, resume_checkpoint_path=tmp_path / "c.jsonl")

        assert m_upsert_link.called
        kwargs = m_upsert_link.call_args.kwargs
        assert kwargs.get("evidence_source_type") == "prof_homepage_tier3"


def test_missing_homepage_tier_files_issue_without_generic_link(tmp_path):
    prof = _prof_row(homepage_page_role=None)
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub()],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.papers_linked_total == 0
        assert report.pipeline_issues_filed == 1
        assert m_issue.call_args.kwargs["issue_type"] == "missing_homepage_tier"
        m_resolve.assert_not_called()
        m_upsert_paper.assert_not_called()
        m_upsert_link.assert_not_called()


def test_page_only_publication_initializes_needs_enrichment(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub(clean_title="Unindexed Preprint", authors_text=None)],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=None,
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch("src.data_agents.paper.homepage_ingest._file_pipeline_issue"):
        m_upsert_paper.return_value = MagicMock(
            paper_id="paper:page-only:x",
            is_new=True,
        )

        run_homepage_paper_ingest(conn, resume_checkpoint_path=tmp_path / "c.jsonl")

        assert m_upsert_paper.call_args.kwargs["canonical_source"] == "prof_page_only"
        assert m_upsert_paper.call_args.kwargs["quality_status"] == "needs_enrichment"


def test_cjk_homepage_titles_skip_external_resolution_in_bulk_ingest(tmp_path):
    prof = _prof_row(name="夏文斌")
    conn = _mock_conn_with_profs([prof])
    pubs = [
        _pub(clean_title="提升城市海外影响力让世界更加了解中国", authors_text=None, year=2024),
        _pub(clean_title="共同富裕视角下教育公平问题研究", authors_text=None, year=2024),
        _pub(clean_title="人才培养不能一味强调竞争", authors_text=None, year=2023),
    ]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=pubs,
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_upsert_paper.return_value = MagicMock(
            paper_id="paper:page-only:cjk",
            is_new=True,
        )

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.papers_linked_total == 3
        m_resolve.assert_not_called()
        assert m_upsert_paper.call_count == 3
        assert [
            call.kwargs["canonical_source"] for call in m_upsert_paper.call_args_list
        ] == ["prof_page_only", "prof_page_only", "prof_page_only"]
        m_issue.assert_not_called()


def test_large_homepage_publication_lists_skip_realtime_external_resolution(tmp_path):
    prof = _prof_row(name="肖国芝")
    conn = _mock_conn_with_profs([prof])
    pubs = [
        _pub(
            clean_title=f"Long Official Publication Title {index}",
            authors_text="G. Xiao",
            year=2024,
        )
        for index in range(81)
    ]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=pubs,
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=False,
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ) as m_fetch_full_text, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_upsert_paper.return_value = MagicMock(
            paper_id="paper:page-only:large",
            is_new=True,
        )

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.papers_linked_total == 81
        m_resolve.assert_not_called()
        assert m_upsert_paper.call_count == 81
        assert {
            call.kwargs["canonical_source"] for call in m_upsert_paper.call_args_list
        } == {"prof_page_only"}
        m_fetch_full_text.assert_not_called()
        m_issue.assert_not_called()


def test_homepage_ingest_caps_realtime_external_resolution_per_professor(tmp_path):
    prof = _prof_row(name="高产老师")
    conn = _mock_conn_with_profs([prof])
    pubs = [
        _pub(
            clean_title=f"Moderate Official Publication Title {index}",
            authors_text="A. Gao",
            year=2024,
        )
        for index in range(20)
    ]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=pubs,
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch("src.data_agents.paper.homepage_ingest._file_pipeline_issue"):
        m_upsert_paper.return_value = MagicMock(
            paper_id="paper:budgeted",
            is_new=True,
        )

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.papers_linked_total == 20
        assert m_resolve.call_count == 12
        assert [
            call.kwargs["canonical_source"]
            for call in m_upsert_paper.call_args_list
        ] == ["openalex"] * 12 + ["prof_page_only"] * 8


def test_homepage_ingest_accepts_external_resolution_budget_override(tmp_path):
    prof = _prof_row(name="高产老师")
    conn = _mock_conn_with_profs([prof])
    pubs = [
        _pub(
            clean_title=f"Budget Override Official Publication Title {index}",
            authors_text="A. Gao",
            year=2024,
        )
        for index in range(5)
    ]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=pubs,
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch("src.data_agents.paper.homepage_ingest._file_pipeline_issue"):
        m_upsert_paper.return_value = MagicMock(
            paper_id="paper:budget-override",
            is_new=True,
        )

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
            external_resolution_max_per_professor=2,
        )

        assert report.papers_linked_total == 5
        assert m_resolve.call_count == 2
        assert m_upsert_link.call_count == 5
        assert [
            call.kwargs["canonical_source"]
            for call in m_upsert_paper.call_args_list
        ] == ["openalex"] * 2 + ["prof_page_only"] * 3


def test_homepage_ingest_external_resolution_budget_spans_owned_pages(
    tmp_path,
    monkeypatch,
):
    prof_id = "PROF-BUDGET"
    profs = [
        _prof_row(prof_id=prof_id, homepage_url="https://example.edu/prof/official"),
        _prof_row(
            prof_id=prof_id,
            homepage_url="https://people.example.edu/prof",
            homepage_page_role="personal_homepage",
        ),
    ]
    conn = _mock_conn_with_profs(profs)

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        side_effect=[
            [_pub(clean_title="Budgeted Official Page Paper")],
            [_pub(clean_title="Budgeted Personal Page Paper")],
        ],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch("src.data_agents.paper.homepage_ingest._file_pipeline_issue"):
        m_upsert_paper.return_value = MagicMock(
            paper_id="paper:budgeted-cross-page",
            is_new=True,
        )

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
            external_resolution_max_per_professor=1,
        )

        assert report.papers_linked_total == 2
        assert m_resolve.call_count == 1
        assert [
            call.kwargs["canonical_source"]
            for call in m_upsert_paper.call_args_list
        ] == ["openalex", "prof_page_only"]


def test_homepage_ingest_dedupes_publications_across_owned_pages_for_professor(
    tmp_path,
):
    prof_id = "PROF-DEDUP"
    profs = [
        _prof_row(prof_id=prof_id, homepage_url="https://example.edu/prof/official"),
        _prof_row(
            prof_id=prof_id,
            homepage_url="https://people.example.edu/prof",
            homepage_page_role="personal_homepage",
        ),
    ]
    conn = _mock_conn_with_profs(profs)

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub(clean_title="Duplicate Cross Page Paper", year=2024)],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch("src.data_agents.paper.homepage_ingest._file_pipeline_issue"):
        m_upsert_paper.return_value = MagicMock(
            paper_id="paper:dedup-cross-page",
            is_new=True,
        )

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.papers_linked_total == 1
        assert m_resolve.call_count == 1
        assert m_upsert_paper.call_count == 1
        assert m_upsert_link.call_count == 1


# ---------- Quality gates / pipeline_issue -----------------------------------


def test_publications_under_threshold_files_pipeline_issue(tmp_path):
    """< 3 pubs extracted despite HTML fetched → pipeline_issue filed."""
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html"
    ) as m_extract, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ), patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_fetch_html.return_value = "<html></html>"
        m_extract.return_value = [_pub(), _pub()]  # only 2 pubs (under 3)
        m_resolve.return_value = _resolved()
        report = run_homepage_paper_ingest(
            conn, resume_checkpoint_path=tmp_path / "c.jsonl"
        )

        assert report.pipeline_issues_filed >= 1
        issue_types_filed = [
            c.kwargs.get("issue_type") for c in m_issue.call_args_list
        ]
        assert "publications_under_threshold" in issue_types_filed


def test_all_titles_page_only_files_pipeline_issue(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html"
    ) as m_extract, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=None,  # all external resolvers miss
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_extract.return_value = [_pub(clean_title=f"Obscure {i}") for i in range(5)]
        report = run_homepage_paper_ingest(
            conn, resume_checkpoint_path=tmp_path / "c.jsonl"
        )

        # T3 page-only fallback keeps prof-page declarations as canonical
        # rows/links, while still filing an issue that enrichment is needed.
        assert report.papers_linked_total == 5
        issue_types = [c.kwargs.get("issue_type") for c in m_issue.call_args_list]
        assert "all_titles_unresolvable" in issue_types


def test_homepage_fetch_error_files_pipeline_issue(tmp_path):
    import httpx

    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch, patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_fetch.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        report = run_homepage_paper_ingest(
            conn, resume_checkpoint_path=tmp_path / "c.jsonl"
        )

        assert report.papers_linked_total == 0
        issue_types = [c.kwargs.get("issue_type") for c in m_issue.call_args_list]
        assert "homepage_fetch_error" in issue_types


def test_homepage_fetch_error_can_use_profile_raw_text_as_publication_source(tmp_path):
    import httpx

    raw_text = "Publications\n1. Profile Raw Text Paper, Test Journal, 2024."
    prof = _prof_row(profile_raw_text=raw_text)
    conn = _mock_conn_with_profs([prof])
    extracted_pub = _pub(
        clean_title="Profile Raw Text Paper",
        source_url="https://example.edu/prof/x",
    )
    seen: dict[str, str] = {}

    def fake_publication_extractor(html: str, *, page_url: str):
        seen["html"] = html
        seen["page_url"] = page_url
        return [extracted_pub]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(title="Profile Raw Text Paper"),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_fetch.side_effect = httpx.HTTPStatusError(
            "412", request=MagicMock(), response=MagicMock(status_code=412)
        )
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
            publication_extractor=fake_publication_extractor,
        )

        assert report.papers_linked_total == 1
        assert seen == {
            "html": raw_text,
            "page_url": "https://example.edu/prof/x",
        }
        assert m_upsert_link.call_args.kwargs["evidence_source_type"] == (
            "prof_homepage_tier2"
        )
        issue_types = [c.kwargs.get("issue_type") for c in m_issue.call_args_list]
        assert "homepage_fetch_raw_text_fallback" in issue_types


def test_per_prof_crash_isolated_and_logged(tmp_path):
    """Unexpected exception per prof → pipeline_issue + continue with other profs."""
    profs = [_prof_row(prof_id=str(uuid.uuid4())) for _ in range(3)]
    conn = _mock_conn_with_profs(profs)

    fetch_results: list = [
        RuntimeError("crash in fetch for prof 1"),
        "<html></html>",
        "<html></html>",
    ]
    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ) as m_close, patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub()],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)
        m_fetch_html.side_effect = fetch_results

        report = run_homepage_paper_ingest(
            conn, resume_checkpoint_path=tmp_path / "c.jsonl"
        )

        # Prof 1 crashed, profs 2-3 processed.
        assert report.profs_processed == 3
        assert report.pipeline_issues_filed >= 1
        # Outer run still marked succeeded.
        assert m_close.call_args.kwargs.get("status") == "succeeded"
        issue_types = [c.kwargs.get("issue_type") for c in m_issue.call_args_list]
        assert "prof_processing_crashed" in issue_types


# ---------- Dry-run ----------------------------------------------------------


def test_dry_run_no_writes(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ) as m_open, patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ) as m_close, patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub()],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=False,
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ) as m_upsert_full:
        report = run_homepage_paper_ingest(
            conn,
            dry_run=True,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        # No writes: zero upsert calls.
        m_upsert_paper.assert_not_called()
        m_upsert_link.assert_not_called()
        m_upsert_full.assert_not_called()
        # pipeline_run NOT opened in dry-run.
        m_open.assert_not_called()
        m_close.assert_not_called()
        # Report still has non-zero processed.
        assert report.profs_processed >= 1


# ---------- Full-text skip when already exists -------------------------------


def test_full_text_fetch_skipped_when_row_exists(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub()],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,  # full text already exists
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ) as m_fetch_full, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ) as m_upsert_full:
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn, resume_checkpoint_path=tmp_path / "c.jsonl"
        )

        assert report.papers_linked_total == 1
        assert report.full_text_fetched_total == 0
        m_fetch_full.assert_not_called()
        m_upsert_full.assert_not_called()


def test_professor_page_pdf_link_attached_to_resolved_paper_for_full_text_fetch(
    tmp_path,
):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    pdf_url = "https://example.edu/prof/papers/deep-learning.pdf"

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[_pub(pdf_url=pdf_url)],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=False,
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ) as m_fetch_full, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ):
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)
        m_fetch_full.return_value = _full_text()

        run_homepage_paper_ingest(conn, resume_checkpoint_path=tmp_path / "c.jsonl")

        assert m_fetch_full.called
        resolved_arg = m_fetch_full.call_args.args[0]
        assert resolved_arg.pdf_url == pdf_url


def test_professor_page_pdf_fetch_cap_files_issue_and_skips_extra_fetches(
    tmp_path,
):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    publications = [
        _pub(clean_title=f"Direct PDF Paper {idx}", pdf_url=f"https://example.edu/p{idx}.pdf")
        for idx in range(1, 4)
    ]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=publications,
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        side_effect=[_resolved(title=pub.clean_title) for pub in publications],
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=False,
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text",
        return_value=_full_text(),
    ) as m_fetch_full, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
            prof_page_pdf_fetch_cap=1,
        )

        assert m_fetch_full.call_count == 1
        assert report.full_text_fetched_total == 1
        assert report.pipeline_issues_filed == 2
        assert [call.kwargs["issue_type"] for call in m_issue.call_args_list] == [
            "pdf_fetch_cap_exceeded",
            "pdf_fetch_cap_exceeded",
        ]


def test_professor_page_pdf_cap_violation_files_pipeline_issue(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    publications = [
        _pub(clean_title="Bad Content Type PDF", pdf_url="https://example.edu/html.pdf"),
        _pub(clean_title="Good PDF A", pdf_url="https://example.edu/a.pdf"),
        _pub(clean_title="Good PDF B", pdf_url="https://example.edu/b.pdf"),
    ]
    failed_extract = FullTextExtract(
        paper_id="paper:doi:10.1/x",
        abstract=None,
        intro=None,
        pdf_url="https://example.edu/html.pdf",
        pdf_sha256=None,
        source="failed",
        fetch_error="pdf_content_type_disallowed",
    )

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=publications,
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        side_effect=[_resolved(title=pub.clean_title) for pub in publications],
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=False,
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text",
        side_effect=[failed_extract, _full_text(), _full_text()],
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_upsert_paper.return_value = MagicMock(paper_id="paper:doi:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.full_text_fetched_total == 2
        assert report.pipeline_issues_filed == 1
        assert m_issue.call_args.kwargs["issue_type"] == "pdf_fetch_cap_violation"
        assert m_issue.call_args.kwargs["details"]["fetch_error"] == (
            "pdf_content_type_disallowed"
        )


# ---------- Resume -----------------------------------------------------------


def test_resume_skips_already_processed_homepage_rows(tmp_path):
    prof1 = _prof_row(
        prof_id="11111111-1111-1111-1111-111111111111",
        homepage_url="https://example.edu/prof/one",
    )
    prof2 = _prof_row(prof_id="22222222-2222-2222-2222-222222222222")
    conn = _mock_conn_with_profs([prof1, prof2])

    # Pre-populate checkpoint with prof1's exact homepage row.
    checkpoint = tmp_path / "c.jsonl"
    checkpoint.write_text(
        json.dumps(
            {
                "prof_id": prof1["professor_id"],
                "homepage_url": prof1["homepage_url"],
                "resume_key": f"{prof1['professor_id']}|{prof1['homepage_url']}",
                "status": "succeeded",
                "papers_linked": 3,
                "pipeline_issues": 0,
            }
        )
        + "\n"
    )

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ), patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_and_extract_full_text"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper_full_text"
    ):
        m_fetch_html.return_value = "<html></html>"
        report = run_homepage_paper_ingest(conn, resume_checkpoint_path=checkpoint)

        assert report.profs_skipped == 1
        # Only prof2 was fetched.
        assert m_fetch_html.call_count == 1


def test_resume_does_not_skip_other_homepage_rows_for_same_professor(tmp_path):
    prof_id = "11111111-1111-1111-1111-111111111111"
    profs = [
        _prof_row(
            prof_id=prof_id,
            homepage_url="https://example.edu/prof/official",
        ),
        _prof_row(
            prof_id=prof_id,
            homepage_url="https://people.example.edu/prof",
            homepage_page_role="personal_homepage",
        ),
    ]
    conn = _mock_conn_with_profs(profs)

    checkpoint = tmp_path / "c.jsonl"
    checkpoint.write_text(
        json.dumps(
            {
                "prof_id": prof_id,
                "homepage_url": "https://example.edu/prof/official",
                "resume_key": f"{prof_id}|https://example.edu/prof/official",
                "status": "succeeded",
                "papers_linked": 3,
                "pipeline_issues": 0,
            }
        )
        + "\n"
    )

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[],
    ):
        m_fetch_html.return_value = "<html></html>"
        report = run_homepage_paper_ingest(conn, resume_checkpoint_path=checkpoint)

        assert report.profs_skipped == 1
        assert report.profs_processed == 1
        assert m_fetch_html.call_args.args[0] == "https://people.example.edu/prof"


def test_resume_tolerates_corrupted_checkpoint_lines(tmp_path):
    checkpoint = tmp_path / "c.jsonl"
    checkpoint.write_text(
        '{"prof_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", '
        '"homepage_url": "https://example.edu/a", '
        '"resume_key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa|https://example.edu/a", '
        '"status": "succeeded"}\n'
        "not valid json\n"
        '{"prof_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", '
        '"homepage_url": "https://example.edu/b", '
        '"resume_key": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb|https://example.edu/b", '
        '"status": "succeeded"}\n'
    )
    prof = _prof_row(prof_id="cccccccc-cccc-cccc-cccc-cccccccccccc")  # not in checkpoint
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[],
    ):
        # Should not raise on bad JSON line; should process prof.
        report = run_homepage_paper_ingest(conn, resume_checkpoint_path=checkpoint)
        assert report.profs_processed == 1


def test_resume_missing_file_treated_as_no_resume(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    missing_path = tmp_path / "does_not_exist.jsonl"

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<html></html>",
    ), patch(
        "src.data_agents.paper.homepage_ingest.extract_publications_from_html",
        return_value=[],
    ):
        report = run_homepage_paper_ingest(conn, resume_checkpoint_path=missing_path)
        assert report.profs_skipped == 0
        assert report.profs_processed == 1


# ---------- Cancellation -----------------------------------------------------


def test_keyboard_interrupt_closes_run_as_failed(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ) as m_close, patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html:
        m_fetch_html.side_effect = KeyboardInterrupt()
        with pytest.raises(KeyboardInterrupt):
            run_homepage_paper_ingest(conn, resume_checkpoint_path=tmp_path / "c.jsonl")
        # close_pipeline_run uses a legal terminal status from V001/V007.
        m_close.assert_called_once()
        assert m_close.call_args.kwargs.get("status") == "failed"


# ---------- IngestReport contract -------------------------------------------


def test_ingest_report_is_frozen_dataclass():
    report = IngestReport(
        run_id=UUID("00000000-0000-0000-0000-000000000000"),
        profs_total=10,
        profs_processed=8,
        profs_skipped=2,
        papers_linked_total=42,
        full_text_fetched_total=30,
        pipeline_issues_filed=3,
        run_duration_seconds=123.4,
    )
    with pytest.raises((AttributeError, TypeError, Exception)):
        report.profs_total = 99
