"""RED-phase tests for M2.4 Unit 6 — run_homepage_paper_ingest orchestrator.

Hermetic tests — mock psycopg.Connection + the M2.1/M2.2/M2.3 helpers + M2.4's
homepage HTTP. Verify branch logic: skip-via-resume, per-prof savepoint isolation,
pipeline_issue filing, dry-run writes nothing, full-text skip when row exists.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest
from openpyxl import Workbook

from src.data_agents.paper import homepage_ingest
from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.paper.homepage_ingest import (
    IngestReport,
    _extract_publications_from_homepage_source_pages,
    _fetch_professors,
    _file_pipeline_issue,
    _filter_homepage_ingest_professor_rows,
    _find_existing_canonical_homepage_paper,
    _find_existing_linked_paper_for_page_only,
    _extract_publications_from_single_source_page,
    _is_malformed_publication_title,
    _load_resume_set,
    _normalize_homepage_publication_for_ingest,
    run_homepage_paper_ingest,
)
from src.data_agents.paper.title_resolver import ResolvedPaper
from src.data_agents.professor.homepage_source_filter import (
    is_homepage_publication_ingest_url,
)
from src.data_agents.professor.homepage_publications import (
    HomepagePublication,
    extract_publications_from_html,
)


# ---------- Fixtures ---------------------------------------------------------


def _prof_row(
    *,
    prof_id: str | None = None,
    name: str = "Test Prof",
    name_en: str | None = None,
    aliases: list[str] | None = None,
    institution: str = "南方科技大学",
    homepage_url: str = "https://example.edu/prof/x",
    homepage_page_role: str | None = "official_profile",
    homepage_page_id: UUID | None = None,
    profile_raw_text: str | None = None,
) -> dict:
    return {
        "professor_id": prof_id or str(uuid.uuid4()),
        "canonical_name": name,
        "canonical_name_en": name_en,
        "aliases": aliases or [],
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
    source_anchor: str | None = None,
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
        source_anchor=source_anchor,
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


def _resolved_unless_cache_only(*_args, **kwargs) -> ResolvedPaper | None:
    return None if kwargs.get("cache_only") else _resolved()


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


def test_homepage_ingest_filters_non_person_cuhk_mypage_rows_before_fetch():
    rows = [
        _prof_row(
            prof_id="PROF-HIGHLIGHTED-NEWS",
            name="Highlighted News",
            homepage_url="https://mypage.cuhk.edu.cn/academics/noel/index-chs.html",
            homepage_page_role="personal_homepage",
        ),
        _prof_row(
            prof_id="PROF-DEEP-BIT",
            name="Deep Bit lab",
            homepage_url="https://mypage.cuhk.edu.cn/academics/lizhen/",
            homepage_page_role="personal_homepage",
        ),
        _prof_row(
            prof_id="PROF-BRESAR",
            name="BRESAR, Miha",
            homepage_url="https://sites.google.com/view/mihabresar",
            homepage_page_role="personal_homepage",
        ),
    ]

    filtered = _filter_homepage_ingest_professor_rows(rows)

    assert [row["professor_id"] for row in filtered] == ["PROF-BRESAR"]


def test_homepage_ingest_filters_profile_title_publication_body_pollution():
    rows = [
        _prof_row(
            prof_id="PROF-CHEN",
            name="陈刚",
            homepage_url="https://mypage.cuhk.edu.cn/academics/example/",
            homepage_page_role="personal_homepage",
        )
        | {
            "affiliation_title": (
                "Modified Peptide Nucleic Acids And Their Use. Inventors: "
                "1) Gitali DEVI"
            )
        },
        _prof_row(
            prof_id="PROF-BRESAR",
            name="BRESAR, Miha",
            homepage_url="https://sites.google.com/view/mihabresar",
            homepage_page_role="personal_homepage",
        )
        | {"affiliation_title": "助理教授"},
    ]

    filtered = _filter_homepage_ingest_professor_rows(rows)

    assert [row["professor_id"] for row in filtered] == ["PROF-BRESAR"]


class _FetchRows:
    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FetchOne:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


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
                    "https://faculty.sustech.edu.cn/xingxy",
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
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-%E6%9D%9C%E9%B9%A4%E6%B0%91",
                    "official_profile",
                ),
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "http://www.sztu.edu.cn/",
                    "personal_homepage",
                ),
                (
                    "PROF-1",
                    "Test Prof",
                    "南方科技大学",
                    "https://inspirehep.net/authors/1234567",
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
        "https://faculty.sustech.edu.cn/xingxy",
        "https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-%E6%9D%9C%E9%B9%A4%E6%B0%91",
    ]
    assert [row["homepage_page_role"] for row in rows] == [
        "official_profile",
        "official_publication_page",
        "lab_homepage",
        "personal_homepage",
        "personal_homepage",
        "official_profile",
    ]
    assert "owner_scope_ref = p.professor_id::text" in conn.executed[0][0]


def test_fetch_professors_skips_stale_same_host_non_primary_personal_homepages():
    conn = _SelectorConn()

    _fetch_professors(
        conn,
        institution=None,
        limit=None,
        prof_id=None,
        include_owned_homepage_pages=True,
    )

    sql = conn.executed[0][0]
    assert "LEFT JOIN source_page primary_sp" in sql
    assert "sp.page_id = p.primary_official_profile_page_id" in sql
    assert "sp.page_role <> 'personal_homepage'" in sql
    assert "sp.url_host IS DISTINCT FROM primary_sp.url_host" in sql


def test_fetch_professors_skips_known_unproductive_official_page_when_owned_page_exists():
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        (
            "PROF-CSSE-1",
            "尹剑飞",
            "深圳大学",
            uuid.uuid4(),
            "https://csse.szu.edu.cn/pages/user/index?id=554",
            "official_profile",
            "尹剑飞 代表性学术论文：Paper One. Journal, 2024.",
        ),
        (
            "PROF-CSSE-1",
            "尹剑飞",
            "深圳大学",
            uuid.uuid4(),
            "https://bigdata.szu.edu.cn/info/1009/1063.htm",
            "personal_homepage",
            "尹剑飞 代表性学术论文：Paper One. Journal, 2024.",
        ),
        (
            "PROF-CSSE-2",
            "何汝艳",
            "深圳大学",
            uuid.uuid4(),
            "https://csse.szu.edu.cn/pages/user/index?id=1187",
            "official_profile",
            "何汝艳 视觉智能研究中心 遥感图像处理与应用",
        ),
    ]

    rows = _fetch_professors(
        conn,
        institution=None,
        department=None,
        seed_id=5,
        limit=None,
        prof_id=None,
        include_owned_homepage_pages=True,
    )

    assert [row["homepage_url"] for row in rows] == [
        "https://bigdata.szu.edu.cn/info/1009/1063.htm",
        "https://csse.szu.edu.cn/pages/user/index?id=1187",
    ]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://people.example.edu/test-prof", True),
        ("http://zenghp.org/", True),
        ("https://jianwei.cuhk.edu.cn/", True),
        ("http://faculty.sustech.edu.cn/chenxf/", True),
        ("https://faculty.sustech.edu.cn/xingxy", True),
        ("https://faculty.sustech.edu.cn/?tagid=xingxy&iscss=1&snapid=1", True),
        ("https://faculty.sustech.edu.cn/", False),
        ("https://faculty.sustech.edu.cn/?cat=4", False),
        ("https://faculty.sustech.edu.cn/zh", False),
        ("https://faculty.sustech.edu.cn/zh/", False),
        (
            "https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-%E6%9D%9C%E9%B9%A4%E6%B0%91",
            False,
        ),
        ("http://www.sztu.edu.cn/", False),
        ("https://sztu.edu.cn/", False),
        ("https://scholar.google.com/citations?user=abc", False),
        ("https://www.researchgate.net/profile/Beichen-Ding", False),
        ("https://orcid.org/0000-0001-2345-6789", False),
        ("https://dblp.org/pid/12/3456.html", False),
        ("https://inspirehep.net/authors/1234567", False),
        ("ResearchGate https://www.researchgate.net/profile/Beichen-Ding", False),
        ("https://scholar.google.com/citations?user=abc Google Scholar", False),
    ],
)
def test_homepage_publication_ingest_url_filter_keeps_owned_pages_not_roster_noise(
    url,
    expected,
):
    assert is_homepage_publication_ingest_url(url) is expected


def test_fetch_professors_keeps_scoped_official_fragment_with_profile_raw_text():
    conn = MagicMock()
    conn.execute.return_value.fetchall.return_value = [
        (
            "PROF-DESIGN-1",
            "杜鹤民",
            "深圳技术大学",
            uuid.uuid4(),
            "https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-%E6%9D%9C%E9%B9%A4%E6%B0%91",
            "official_profile",
            "杜鹤民 - 教授 代表性论文：Scoped Design Paper. Journal, 2024.",
        )
    ]

    rows = _fetch_professors(
        conn,
        institution=None,
        department=None,
        seed_id=47,
        limit=None,
        prof_id=None,
        include_owned_homepage_pages=True,
    )

    assert [row["professor_id"] for row in rows] == ["PROF-DESIGN-1"]
    assert rows[0]["profile_raw_text"].startswith("杜鹤民 - 教授")


def test_filter_keeps_official_publication_fragment_for_fetch_scope():
    rows = [
        _prof_row(
            prof_id="PROF-DESIGN-FRAGMENT",
            name="刘墨",
            homepage_url=(
                "https://design.sztu.edu.cn/xygk/szdw/jytd.htm"
                "#prof-%E5%88%98%E5%A2%A8"
            ),
            homepage_page_role="official_publication_page",
            profile_raw_text=None,
        )
    ]

    filtered = _filter_homepage_ingest_professor_rows(rows)

    assert [row["professor_id"] for row in filtered] == ["PROF-DESIGN-FRAGMENT"]


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
    assert "(COALESCE(pr.run_scope->>'trigger_mode', '') = 'full') DESC" in sql
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
    assert "(COALESCE(pr.run_scope->>'trigger_mode', '') = 'full') DESC" in sql
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

    pubs = [_pub(clean_title=f"Resolvable Paper Title {i}") for i in range(5)]

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


def test_scoped_fragment_profile_uses_stored_raw_text_without_fetching_whole_page(
    tmp_path,
):
    prof = _prof_row(
        prof_id="PROF-DESIGN-1",
        name="杜鹤民",
        institution="深圳技术大学",
        homepage_url="https://design.sztu.edu.cn/xygk/szdw/jytd.htm#prof-%E6%9D%9C%E9%B9%A4%E6%B0%91",
        homepage_page_role="official_profile",
        profile_raw_text=(
            "杜鹤民 - 教授\n"
            "代表性论文：Scoped Design Paper. Journal of Design, 2024."
        ),
    )
    conn = _mock_conn_with_profs([prof])

    def fake_publication_extractor(html: str, *, page_url: str):
        assert html == prof["profile_raw_text"]
        assert page_url == prof["homepage_url"]
        return [_pub(clean_title="Scoped Design Paper", source_url=page_url)]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run",
        return_value=uuid.uuid4(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html:
        report = run_homepage_paper_ingest(
            conn,
            dry_run=True,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
            external_resolution_max_per_professor=0,
        )

    assert report.profs_processed == 1
    assert report.papers_linked_total == 1
    m_fetch_html.assert_not_called()


def test_scoped_fragment_profile_rejects_raw_text_for_another_professor(
    tmp_path,
):
    prof = _prof_row(
        prof_id="PROF-DESIGN-LIUMO",
        name="刘墨",
        institution="深圳技术大学",
        homepage_url=(
            "https://design.sztu.edu.cn/xygk/szdw/jytd.htm"
            "#prof-%E5%88%98%E5%A2%A8"
        ),
        homepage_page_role="official_profile",
        profile_raw_text=(
            "杜鹤民 - 教授\n"
            "代表性论文：Designing Mediated Social Touch for Mobile Communication: "
            "From Hand Gestures to Touch Signals. International Journal of "
            "Human-Computer Studies, 2026."
        ),
    )
    conn = _mock_conn_with_profs([prof])
    seen: dict[str, str] = {}

    def fake_publication_extractor(html: str, *, page_url: str):
        seen["html"] = html
        seen["page_url"] = page_url
        return []

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run",
        return_value=uuid.uuid4(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value="<div class='team-item'><h3>刘墨</h3><p>交互设计</p></div>",
    ) as m_fetch_html:
        report = run_homepage_paper_ingest(
            conn,
            dry_run=True,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
            external_resolution_max_per_professor=0,
        )

    assert report.profs_processed == 1
    assert report.papers_linked_total == 0
    m_fetch_html.assert_called_once_with(prof["homepage_url"])
    assert "杜鹤民" not in seen["html"]
    assert seen["page_url"] == prof["homepage_url"]


def test_known_unproductive_csse_profile_uses_stored_raw_text_without_fetching(
    tmp_path,
):
    prof = _prof_row(
        prof_id="PROF-CSSE-RAW",
        name="尹剑飞",
        institution="深圳大学",
        homepage_url="https://csse.szu.edu.cn/pages/user/index?id=554",
        homepage_page_role="official_profile",
        profile_raw_text=(
            "尹剑飞\n"
            "代表性学术论文：Wireless Sensor Network Node Localization Algorithm "
            "Based on SDP and ESDP. CECNet, 2013."
        ),
    )
    conn = _mock_conn_with_profs([prof])

    def fake_publication_extractor(html: str, *, page_url: str):
        assert html == prof["profile_raw_text"]
        assert page_url == prof["homepage_url"]
        return [
            _pub(
                clean_title="Wireless Sensor Network Node Localization Algorithm Based on SDP and ESDP",
                source_url=page_url,
            )
        ]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run",
        return_value=uuid.uuid4(),
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html:
        report = run_homepage_paper_ingest(
            conn,
            dry_run=True,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
            external_resolution_max_per_professor=0,
        )

    assert report.profs_processed == 1
    assert report.papers_linked_total == 1
    m_fetch_html.assert_not_called()


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
        prof_id="PROF-PERSONAL-TANGB",
        homepage_url="https://people.example.edu/tangb/",
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
        source_url="https://people.example.edu/tangb/pub.html",
    )

    def fake_publication_extractor(html: str, *, page_url: str):
        if page_url == "https://people.example.edu/tangb/":
            assert html == homepage_html
            return []
        assert page_url == "https://people.example.edu/tangb/pub.html"
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
            "https://people.example.edu/tangb/",
            "https://people.example.edu/tangb/pub.html",
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
            "https://people.example.edu/tangb/pub.html"
        )
        assert m_upsert_source_page.call_args.kwargs["page_role"] == (
            "personal_homepage"
        )
        assert m_upsert_source_page.call_args.kwargs["owner_scope_kind"] == "professor"
        assert m_upsert_source_page.call_args.kwargs["owner_scope_ref"] == (
            "PROF-PERSONAL-TANGB"
        )
        assert m_upsert_source_page.call_args.kwargs["is_official_source"] is False


def test_homepage_ingest_follows_szu_bigdata_publication_info_page(tmp_path):
    second_hop_page_id = UUID("33333333-3333-3333-3333-333333333333")
    prof = _prof_row(
        prof_id="PROF-SZU-BIGDATA",
        name="陈梓楠",
        institution="深圳大学",
        homepage_url="https://bigdata.szu.edu.cn/kycg/lwfb.htm",
        homepage_page_role="personal_homepage",
    )
    conn = _mock_conn_with_profs([prof])
    homepage_html = """
    <html><body>
      <a href="/info/1016/1211.htm" title="2020年代表性论文">2020年代表性论文</a>
      <a href="/info/1001/9999.htm" title="学院新闻">学院新闻</a>
    </body></html>
    """
    publication_html = """
    <html><body>
      <table>
        <tr><th>序号</th><th>论文名称</th><th>期刊</th><th>时间</th><th>作者</th></tr>
        <tr><td>1</td><td>Robust graph analytics for urban big data</td><td>TKDD</td><td>2020</td><td>陈梓楠</td></tr>
      </table>
    </body></html>
    """
    pub = _pub(
        clean_title="Robust graph analytics for urban big data",
        authors_text="陈梓楠",
        source_url="https://bigdata.szu.edu.cn/info/1016/1211.htm",
        year=2020,
    )

    def fake_publication_extractor(html: str, *, page_url: str):
        if page_url == "https://bigdata.szu.edu.cn/kycg/lwfb.htm":
            assert html == homepage_html
            return []
        assert page_url == "https://bigdata.szu.edu.cn/info/1016/1211.htm"
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
        return_value=_resolved(title="Robust graph analytics for urban big data"),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.upsert_source_page_for_url",
        return_value=second_hop_page_id,
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_fetch_html.side_effect = [homepage_html, publication_html]
        m_upsert_paper.return_value = MagicMock(paper_id="paper:title:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
        )

        assert report.papers_linked_total == 1
        assert [call.args[0] for call in m_fetch_html.call_args_list] == [
            "https://bigdata.szu.edu.cn/kycg/lwfb.htm",
            "https://bigdata.szu.edu.cn/info/1016/1211.htm",
        ]
        assert m_upsert_link.call_args.kwargs["evidence_page_id"] == (
            second_hop_page_id
        )


def test_homepage_ingest_follows_all_szu_bigdata_publication_year_pages(tmp_path):
    prof = _prof_row(
        prof_id="PROF-SZU-BIGDATA-MULTIYEAR",
        name="黄哲学",
        name_en="Joshua Zhexue Huang",
        institution="深圳大学",
        homepage_url="https://bigdata.szu.edu.cn/kycg/lwfb.htm",
        homepage_page_role="official_publication_page",
    )
    conn = _mock_conn_with_profs([prof])
    year_urls = [
        "https://bigdata.szu.edu.cn/info/1016/1312.htm",
        "https://bigdata.szu.edu.cn/info/1016/1244.htm",
        "https://bigdata.szu.edu.cn/info/1016/1211.htm",
        "https://bigdata.szu.edu.cn/info/1016/1068.htm",
        "https://bigdata.szu.edu.cn/info/1016/1210.htm",
    ]
    homepage_html = """
    <html><body>
      <a href="/info/1016/1312.htm" title="2023年论文发表情况">2023年论文发表情况</a>
      <a href="/info/1016/1244.htm" title="2022高水平论文">2022高水平论文</a>
      <a href="/info/1016/1211.htm" title="2021年代表性论文">2021年代表性论文</a>
      <a href="/info/1016/1068.htm" title="2020年代表性论文">2020年代表性论文</a>
      <a href="/info/1016/1210.htm" title="2019年代表性论文">2019年代表性论文</a>
    </body></html>
    """
    publications_by_url = {
        url: _pub(
            clean_title=f"Representative BigData Paper {index}",
            authors_text="Joshua Zhexue Huang, Xiaojun Chen",
            source_url=url,
            year=2024 - index,
        )
        for index, url in enumerate(year_urls, start=1)
    }

    def fake_publication_extractor(html: str, *, page_url: str):
        if page_url == "https://bigdata.szu.edu.cn/kycg/lwfb.htm":
            assert html == homepage_html
            return []
        assert html == f"<html><body>{page_url}</body></html>"
        return [publications_by_url[page_url]]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        side_effect=lambda title, **kwargs: _resolved(title=title),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_source_page_for_url",
        return_value=UUID("44444444-4444-4444-4444-444444444444"),
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_fetch_html.side_effect = [
            homepage_html,
            *(f"<html><body>{url}</body></html>" for url in year_urls),
        ]
        m_upsert_paper.side_effect = [
            MagicMock(paper_id=f"paper:title:{index}", is_new=True)
            for index in range(len(year_urls))
        ]

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
        )

        assert report.papers_linked_total == len(year_urls)
        assert [call.args[0] for call in m_fetch_html.call_args_list] == [
            "https://bigdata.szu.edu.cn/kycg/lwfb.htm",
            *year_urls,
        ]


def test_homepage_ingest_filters_szu_bigdata_aggregate_pages_by_author(tmp_path):
    prof = _prof_row(
        prof_id="PROF-SZU-BIGDATA-AGGREGATE",
        name="Muhammad Saqib Nawaz",
        institution="深圳大学",
        homepage_url="https://bigdata.szu.edu.cn/kycg/lwfb.htm",
        homepage_page_role="official_publication_page",
    )
    conn = _mock_conn_with_profs([prof])
    homepage_html = """
    <html><body>
      <a href="/info/1016/1067.htm" title="2018年代表性论文">2018年代表性论文</a>
    </body></html>
    """
    publication_html = "<html><body>aggregate publications</body></html>"
    matching_pub = _pub(
        clean_title="A paper by the current professor",
        authors_text="Muhammad Saqib Nawaz, A. Smith",
        source_url="https://bigdata.szu.edu.cn/info/1016/1067.htm",
        year=2018,
    )
    other_professor_pub = _pub(
        clean_title="A paper by another big data center professor",
        authors_text="Joshua Zhexue Huang, Xiaojun Chen",
        source_url="https://bigdata.szu.edu.cn/info/1016/1067.htm",
        year=2018,
    )

    def fake_publication_extractor(html: str, *, page_url: str):
        if page_url == "https://bigdata.szu.edu.cn/kycg/lwfb.htm":
            assert html == homepage_html
            return []
        assert page_url == "https://bigdata.szu.edu.cn/info/1016/1067.htm"
        assert html == publication_html
        return [matching_pub, other_professor_pub]

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html, patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        side_effect=lambda title, **kwargs: _resolved(title=title),
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.upsert_source_page_for_url",
        return_value=UUID("55555555-5555-5555-5555-555555555555"),
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ):
        m_fetch_html.side_effect = [homepage_html, publication_html]
        m_upsert_paper.return_value = MagicMock(paper_id="paper:title:x", is_new=True)

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "checkpoint.jsonl",
            publication_extractor=fake_publication_extractor,
        )

        assert report.papers_linked_total == 1
        assert m_upsert_link.call_count == 1
        assert m_upsert_paper.call_args.kwargs["title_clean"] == (
            "A paper by the current professor"
        )


def test_szu_bigdata_publication_page_uses_xlsx_attachment_titles(monkeypatch):
    html = """
    <html><body>
      <article>
        <h1>2020年代表性论文</h1>
        <p>2020-12-31 10:34:22 来源：系统管理员</p>
        <p>附件【<a href="/system/_content/download.jsp?wbfileid=abc">
          2020年代表性论文.xlsx
        </a>】已下载 次</p>
      </article>
    </body></html>
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["2020年代表性论文"])
    sheet.append(["序号", "题目", "期刊名", "年份", "作者"])
    sheet.append(
        [
            1,
            "Discriminative Streaming Network Embedding",
            "Knowl. Based Syst.",
            "2020",
            "Qi, Yiyan; Cheng, Jiefeng; Chen, Xiaojun",
        ]
    )
    sheet.append(
        [
            2,
            "Top-k relevant semantic place retrieval on spatiotemporal RDF data",
            "VLDB J.",
            "2020",
            "Dingming Wu, Hao Zhou, Jieming Shi",
        ]
    )
    buffer = BytesIO()
    workbook.save(buffer)

    monkeypatch.setattr(
        homepage_ingest,
        "_fetch_szu_bigdata_attachment_bytes",
        lambda _url, *, referer_url: buffer.getvalue(),
    )

    augmented_html = homepage_ingest._augment_szu_bigdata_publication_attachment_text(
        html,
        page_url="https://bigdata.szu.edu.cn/info/1016/1068.htm",
    )

    publications = extract_publications_from_html(
        augmented_html,
        page_url="https://bigdata.szu.edu.cn/info/1016/1068.htm",
    )

    titles = {publication.clean_title for publication in publications}
    assert "Discriminative Streaming Network Embedding" in titles
    assert (
        "Top-k relevant semantic place retrieval on spatiotemporal RDF data" in titles
    )


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
        homepage_url="https://people.example.edu/tangb/",
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
        source_url="https://people.example.edu/tangb/",
    )

    def fake_publication_extractor(html: str, *, page_url: str):
        assert page_url == "https://people.example.edu/tangb/"
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
            "https://people.example.edu/tangb/",
            "https://people.example.edu/tangb/pub.html",
        ]


def test_homepage_source_extraction_reports_second_hop_page_outcomes():
    homepage_html = """
    <html><body>
      <a href="pub.html">Publications</a>
      <a href="empty.html">Selected Publications</a>
      <a href="https://other.example.edu/publications.html">Publications</a>
    </body></html>
    """
    publication_html = "<html><body><h2>Publications</h2></body></html>"
    empty_html = """
    <html><body>
      <h2>Selected Publications</h2>
      <p>Published more than 50 papers and led multiple research projects.</p>
    </body></html>
    """

    def fake_publication_extractor(_html: str, *, page_url: str):
        if page_url.endswith("/pub.html"):
            return [
                _pub(
                    clean_title="Second Hop Publication",
                    source_url="https://people.example.edu/tangb/pub.html",
                )
            ]
        return []

    with patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html:
        m_fetch_html.side_effect = [publication_html, empty_html]

        report = _extract_publications_from_homepage_source_pages(
            homepage_html,
            page_url="https://people.example.edu/tangb/",
            publication_extractor=fake_publication_extractor,
            use_rule_diagnostics=False,
        )

    outcomes = {outcome.page_url: outcome for outcome in report.page_outcomes}
    assert outcomes["https://people.example.edu/tangb/"].status == "processed"
    assert outcomes["https://people.example.edu/tangb/pub.html"].status == "processed"
    assert (
        outcomes["https://people.example.edu/tangb/pub.html"].publications_extracted
        == 1
    )
    assert outcomes["https://people.example.edu/tangb/empty.html"].status == (
        "zero_extraction"
    )
    assert outcomes["https://other.example.edu/publications.html"].status == "skipped"
    assert outcomes[
        "https://other.example.edu/publications.html"
    ].skip_reason == "outside_personal_site_root"


def test_homepage_source_extraction_reports_second_hop_fetch_failed():
    homepage_html = """
    <html><body>
      <a href="pub.html">Publications</a>
    </body></html>
    """

    def fake_publication_extractor(_html: str, *, page_url: str):
        assert page_url == "https://people.example.edu/tangb/"
        return []

    with patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html"
    ) as m_fetch_html:
        m_fetch_html.side_effect = httpx.ReadError("second hop disconnected")

        report = _extract_publications_from_homepage_source_pages(
            homepage_html,
            page_url="https://people.example.edu/tangb/",
            publication_extractor=fake_publication_extractor,
            use_rule_diagnostics=False,
        )

    outcomes = {outcome.page_url: outcome for outcome in report.page_outcomes}
    assert outcomes["https://people.example.edu/tangb/pub.html"].status == (
        "fetch_failed"
    )
    assert outcomes[
        "https://people.example.edu/tangb/pub.html"
    ].fetch_error_type == "ReadError"


def test_homepage_ingest_dedupes_publications_across_second_hop_pages(tmp_path):
    prof = _prof_row(
        homepage_url="https://people.example.edu/tangb/",
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
        source_url="https://people.example.edu/tangb/",
    )
    second_pub = _pub(
        clean_title="Duplicate Publication Title",
        source_url="https://people.example.edu/tangb/pub.html",
    )

    def fake_publication_extractor(_html: str, *, page_url: str):
        if page_url == "https://people.example.edu/tangb/":
            return [first_pub]
        if page_url == "https://people.example.edu/tangb/pub.html":
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
        homepage_url="https://people.example.edu/tangb/",
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
            "https://people.example.edu/tangb/"
        ]
        m_resolve.assert_not_called()
        m_upsert_paper.assert_not_called()
        m_upsert_link.assert_not_called()


def test_homepage_ingest_uses_full_title_cascade_for_homepage_titles(tmp_path):
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

        assert m_resolve.call_args.kwargs["enable_arxiv_title_search"] is True


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
        "A representative result of my works is the article Planar Carrollean dynamics",
        "Highlighted in SUSTech News",
        "Highlighted in X-MOL",
        "Associate Editor",
    ],
)
def test_malformed_guard_blocks_homepage_prose_and_highlight_noise(clean_title):
    publication = _pub(clean_title=clean_title, authors_text=None, year=None)

    assert _is_malformed_publication_title(publication), clean_title


@pytest.mark.parametrize(
    "clean_title",
    [
        "30万元, 在研, 主持",
        "2022中国博士后科学基金会博士后国际交流引进计划",
        "国家重点研发计划：服务机器人云服务平台，任务负责人",
        "2023年，入选CCF Fellow",
        "山东省重点研发计划：智能装卸车机器人系统关键技术研究与应用，项目负责人",
    ],
)
def test_malformed_guard_blocks_suat_project_honor_and_talent_plan_noise(
    clean_title,
):
    publication = _pub(clean_title=clean_title, authors_text=None, year=None)

    assert _is_malformed_publication_title(publication), clean_title


@pytest.mark.parametrize(
    "clean_title",
    [
        "近五年的研究工作集中在协作与人机交互方面",
        "创意向善 设计为众/Innovation for good - Design for all",
        "当前研究兴趣主要集中在数据驱动设计、人工智能辅助设计和可持续设计方面",
        "International Journal of Human-Computer Studies",
        "International Journal of Human–Computer Studies",
        "ACM Transactions on Evolutionary Learning and Optimization",
        "The Waterfront of Toronto, Canada",
        "ICML/NeurIPS/ICLR",
    ],
)
def test_malformed_guard_blocks_seed47_profile_pollution_titles(clean_title):
    publication = _pub(clean_title=clean_title, authors_text=None, year=None)

    assert _is_malformed_publication_title(publication), clean_title


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
        "2019年代表性论文序号论文名称期刊时间作者 1 A distributed data "
        "management system to support large-scale data analysis The Journal "
        "of Systems & Software 2019 黄哲学",
    ],
)
def test_malformed_guard_blocks_section_headings_and_metadata_labels(clean_title):
    publication = _pub(clean_title=clean_title, authors_text=None, venue_text=None)

    assert _is_malformed_publication_title(publication), clean_title


@pytest.mark.parametrize(
    "clean_title",
    [
        "Best Paper",
        "TPC Co-Chair",
        "更新时间：2024-03-19",
    ],
)
def test_malformed_guard_blocks_szu_seed18_award_role_and_update_metadata(
    clean_title,
):
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


def test_malformed_guard_blocks_us_patent_publication_record():
    publication = HomepagePublication(
        raw_title=(
            "Techniques for current sensing for single-inductor multiple-output "
            "(simo) regulators” US Patent 16,553,759"
        ),
        clean_title=(
            "Techniques for current sensing for single-inductor multiple-output "
            "(simo) regulators” US Patent 16,553,759"
        ),
        authors_text=None,
        venue_text=None,
        year=2024,
        source_url="https://mypage.cuhk.edu.cn/academics/example/",
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


def test_malformed_guard_allows_context_supported_page_only_short_title():
    publication = _pub(
        clean_title="Unindexed Preprint",
        authors_text=None,
        venue_text="Working paper",
        year=2024,
    )

    assert not _is_malformed_publication_title(publication)


def test_malformed_guard_blocks_site_footer_navigation_tail():
    title = (
        "人才培养对外合作文化建设招贤纳士版权所有© 2013-2020："
        "深圳大学南校区计算机与软件学院粤ICP备12345号分享关注官微"
        "更多大数据内容 0755-26530821 23123122"
    )
    publication = _pub(clean_title=title, authors_text=None, venue_text=None, year=None)

    assert _is_malformed_publication_title(publication)


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


def test_page_only_publication_reuses_existing_same_title_year_link(tmp_path):
    prof = _prof_row(prof_id="PROF-DUP")

    class _DuplicateReuseConn:
        def __init__(self):
            self.executed: list[tuple[str, tuple]] = []

        def execute(self, query: str, params: tuple = ()):
            self.executed.append((query, params))
            if "SELECT p.professor_id" in query:
                return _FetchRows([prof])
            if "FROM professor_paper_link" in query:
                return _FetchOne({"paper_id": "PAPER-IDENTIFIED"})
            return _FetchOne(None)

        @contextmanager
        def transaction(self, savepoint: bool = False):  # noqa: ARG002
            yield

    conn = _DuplicateReuseConn()
    publication = _pub(
        clean_title="Graph Neural Networks for Materials Discovery",
        authors_text=None,
        year=2023,
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
        return_value=[publication],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=None,
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch("src.data_agents.paper.homepage_ingest._file_pipeline_issue"):
        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

    assert report.papers_linked_total == 1
    m_upsert_paper.assert_not_called()
    assert m_upsert_link.call_args.kwargs["paper_id"] == "PAPER-IDENTIFIED"
    assert m_upsert_link.call_args.kwargs["evidence_source_type"] == "prof_homepage_tier2"
    assert m_upsert_link.call_args.kwargs["is_officially_listed"] is True
    assert any("FROM professor_paper_link" in sql for sql, _ in conn.executed)
    assert any("ppl.link_status = 'verified'" in sql for sql, _ in conn.executed)


def test_page_only_publication_reuses_existing_canonical_title_year(tmp_path):
    prof = _prof_row(prof_id="PROF-GLOBAL-CANON")

    class _CanonicalReuseConn:
        def __init__(self):
            self.executed: list[tuple[str, tuple]] = []

        def execute(self, query: str, params: tuple = ()):
            self.executed.append((query, params))
            if "SELECT p.professor_id" in query:
                return _FetchRows([prof])
            if "FROM professor_paper_link" in query:
                return _FetchOne(None)
            if "FROM paper p" in query and "regexp_replace" in query:
                return _FetchOne({"paper_id": "PAPER-CANON"})
            return _FetchOne(None)

        @contextmanager
        def transaction(self, savepoint: bool = False):  # noqa: ARG002
            yield

    conn = _CanonicalReuseConn()
    publication = _pub(
        clean_title="Graph Neural Networks for Materials Discovery",
        authors_text="A. Smith, B. Chen",
        year=2023,
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
        return_value=[publication],
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=None,
    ), patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch("src.data_agents.paper.homepage_ingest._file_pipeline_issue"):
        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

    assert report.papers_linked_total == 1
    m_upsert_paper.assert_not_called()
    assert m_upsert_link.call_args.kwargs["paper_id"] == "PAPER-CANON"
    assert any("regexp_replace" in sql for sql, _ in conn.executed)
    assert not any("authors_display" in sql for sql, _ in conn.executed)


@pytest.mark.parametrize(
    ("kwargs", "expected_sql", "expected_param"),
    [
        (
            {"doi": "10.1016/J.NEUCOM.2018.01.001", "arxiv_id": None},
            "lower(p.doi) = %s",
            "10.1016/j.neucom.2018.01.001",
        ),
        (
            {"doi": None, "arxiv_id": "2409.05701"},
            "lower(p.arxiv_id) = %s",
            "2409.05701",
        ),
    ],
)
def test_find_existing_canonical_homepage_paper_uses_identifier_keys(
    kwargs: dict[str, str | None],
    expected_sql: str,
    expected_param: str,
) -> None:
    class _IdentifierLookupConn:
        def __init__(self) -> None:
            self.executed: list[tuple[str, tuple]] = []

        def execute(self, query: str, params: tuple = ()):
            self.executed.append((query, params))
            return _FetchOne({"paper_id": "PAPER-CANON"})

    conn = _IdentifierLookupConn()

    paper_id = _find_existing_canonical_homepage_paper(
        conn,
        clean_title="pFedGPA",
        year=2024,
        authors=(),
        **kwargs,
    )

    assert paper_id == "PAPER-CANON"
    sql, params = conn.executed[0]
    assert expected_sql in sql
    assert expected_param in params


def test_page_only_existing_paper_lookup_resolves_merge_alias() -> None:
    class _AliasLookupConn:
        def __init__(self) -> None:
            self.executed: list[tuple[str, tuple]] = []

        def execute(self, query: str, params: tuple = ()):
            self.executed.append((query, params))
            return _FetchOne({"paper_id": "PAPER-CANON"})

    conn = _AliasLookupConn()

    paper_id = _find_existing_linked_paper_for_page_only(
        conn,
        professor_id="PROF-AHMED",
        clean_title="Improved Alzheimer's disease diagnosis",
        year=2018,
    )

    assert paper_id == "PAPER-CANON"
    sql = " ".join(conn.executed[0][0].split()).lower()
    assert "paper_merge_alias" in sql
    assert "coalesce(pma.canonical_paper_id, p.paper_id) as paper_id" in sql


def test_cjk_homepage_titles_use_shared_external_resolution(tmp_path):
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
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        side_effect=_resolved_unless_cache_only,
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
        assert m_resolve.call_count == 3
        assert m_upsert_paper.call_count == 3
        assert [
            call.kwargs["canonical_source"] for call in m_upsert_paper.call_args_list
        ] == ["openalex", "openalex", "openalex"]
        m_issue.assert_not_called()


def test_large_homepage_publication_lists_use_shared_external_resolution_by_default(
    tmp_path,
):
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
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title",
        return_value=_resolved(),
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ), patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
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
        assert m_resolve.call_count == 81
        assert m_upsert_paper.call_count == 81
        assert {
            call.kwargs["canonical_source"] for call in m_upsert_paper.call_args_list
        } == {"openalex"}
        m_fetch_full_text.assert_not_called()
        m_issue.assert_not_called()


def test_homepage_ingest_does_not_cap_realtime_external_resolution_by_default(tmp_path):
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
        assert m_resolve.call_count == 20
        assert [
            call.kwargs["canonical_source"]
            for call in m_upsert_paper.call_args_list
        ] == ["openalex"] * 20


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
        side_effect=_resolved_unless_cache_only,
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
        assert m_resolve.call_count == 5
        assert [
            call.kwargs["cache_only"] for call in m_resolve.call_args_list
        ] == [False, False, True, True, True]
        assert m_upsert_link.call_count == 5
        assert [
            call.kwargs["canonical_source"]
            for call in m_upsert_paper.call_args_list
        ] == ["openalex"] * 2 + ["prof_page_only"] * 3


def test_homepage_ingest_resolution_budget_zero_still_uses_cache(tmp_path):
    prof = _prof_row(name="缓存老师")
    conn = _mock_conn_with_profs([prof])
    pubs = [_pub(clean_title="Cached Official Publication Title")]
    cached_resolution = _resolved(title="Cached Official Publication Title")

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
        return_value=cached_resolution,
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest.paper_full_text_exists",
        return_value=True,
    ), patch("src.data_agents.paper.homepage_ingest._file_pipeline_issue"):
        m_upsert_paper.return_value = MagicMock(
            paper_id="paper:cached",
            is_new=True,
        )

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
            external_resolution_max_per_professor=0,
        )

        assert report.papers_linked_total == 1
        assert m_resolve.call_count == 1
        assert m_resolve.call_args.kwargs["cache_only"] is True
        assert m_upsert_paper.call_args.kwargs["canonical_source"] == "openalex"
        assert m_upsert_link.call_count == 1


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
        side_effect=_resolved_unless_cache_only,
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
        assert m_resolve.call_count == 2
        assert [call.kwargs["cache_only"] for call in m_resolve.call_args_list] == [
            False,
            True,
        ]
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


def test_zero_publications_with_detected_section_files_pipeline_issue(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    html = """
    <html><body>
      <h2>Publications</h2>
      <p>Published more than 50 papers and led multiple research projects.</p>
    </body></html>
    """

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value=html,
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.papers_linked_total == 0
        assert report.pipeline_issues_filed >= 1
        issue_types = [c.kwargs.get("issue_type") for c in m_issue.call_args_list]
        assert "publication_section_zero_extraction" in issue_types
        issue_details = [
            c.kwargs.get("details")
            for c in m_issue.call_args_list
            if c.kwargs.get("issue_type") == "publication_section_zero_extraction"
        ][0]
        assert issue_details["pages"][0]["page_url"] == prof["homepage_url"]
        assert issue_details["pages"][0]["sections_detected"] == 1


def test_count_only_publication_claim_files_sparse_source_issue_without_papers(
    tmp_path,
):
    prof = _prof_row(
        name="夏林中",
        institution="深圳信息职业技术大学",
        homepage_url="https://zd.suit-sz.edu.cn/info/1013/2674.htm",
    )
    conn = _mock_conn_with_profs([prof])
    html = """
    <html><body>
      <div class="v_news_content">
        <p>夏林中，男，博士，教授。本人先后承担国家基金委、
        省基金委等教科研项目10余项，在国内外期刊发表高水平论文60余篇，
        申请专利17项，软件著作权10项。</p>
      </div>
    </body></html>
    """

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value=html,
    ), patch(
        "src.data_agents.paper.homepage_ingest.resolve_paper_by_title"
    ) as m_resolve, patch(
        "src.data_agents.paper.homepage_ingest.upsert_paper"
    ) as m_upsert_paper, patch(
        "src.data_agents.paper.homepage_ingest._upsert_professor_paper_link"
    ) as m_upsert_link, patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.papers_linked_total == 0
        assert report.pipeline_issues_filed == 1
        issue_types = [c.kwargs.get("issue_type") for c in m_issue.call_args_list]
        assert "publication_source_sparse_count_only" in issue_types
        issue_details = [
            c.kwargs.get("details")
            for c in m_issue.call_args_list
            if c.kwargs.get("issue_type") == "publication_source_sparse_count_only"
        ][0]
        assert issue_details["homepage_url"] == prof["homepage_url"]
        assert "发表高水平论文60余篇" in issue_details["claim_snippet"]
        m_resolve.assert_not_called()
        m_upsert_paper.assert_not_called()
        m_upsert_link.assert_not_called()


def test_count_only_publication_claim_ignores_sziit_sidebar_template_counts(
    tmp_path,
):
    prof = _prof_row(
        name="郭婷",
        institution="深圳信息职业技术大学",
        homepage_url="https://zd.suit-sz.edu.cn/info/1013/1273.htm",
    )
    conn = _mock_conn_with_profs([prof])
    html = """
    <html><body>
      <div class="leftwrap">
        <p>夏林中，男，博士，教授。在国内外期刊发表高水平论文60余篇，
        申请专利17项，软件著作权10项。</p>
      </div>
      <div class="v_news_content">
        <p>郭婷，中德学院工业机器人技术专业教师。近年来参与欧洲第五框架下
        2项欧盟项目，1项市级教研课题。</p>
      </div>
    </body></html>
    """

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value=html,
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.papers_linked_total == 0
        assert report.pipeline_issues_filed == 0
        m_issue.assert_not_called()


def test_custom_zero_publication_extractor_preserves_rule_diagnostics(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])

    html = """
    <html><body>
      <h2>Publications</h2>
      <p>Published more than 50 papers and led multiple research projects.</p>
    </body></html>
    """

    with patch(
        "src.data_agents.paper.homepage_ingest.open_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.close_pipeline_run"
    ), patch(
        "src.data_agents.paper.homepage_ingest.fetch_homepage_html",
        return_value=html,
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
            publication_extractor=lambda _html, *, page_url: [],
        )

        assert report.papers_linked_total == 0
        assert report.pipeline_issues_filed >= 1
        issue_types = [c.kwargs.get("issue_type") for c in m_issue.call_args_list]
        assert "publication_section_zero_extraction" in issue_types


def test_custom_zero_publication_extractor_falls_back_to_rule_publications():
    html = """
    <html><body>
      <h2>Publications</h2>
      <ol>
        <li>Rule Fallback Paper for Mechanical Systems. Journal of Mechanical Systems, 2024.</li>
      </ol>
    </body></html>
    """

    publications, zero_pages = _extract_publications_from_single_source_page(
        html,
        page_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc/dsgrjj/20492?yxsh=28",
        publication_extractor=lambda _html, *, page_url: [],
        use_rule_diagnostics=False,
    )

    assert [pub.clean_title for pub in publications] == [
        "Rule Fallback Paper for Mechanical Systems"
    ]
    assert zero_pages == []


def test_file_pipeline_issue_refreshes_existing_open_issue_evidence():
    conn = MagicMock()
    select_result = MagicMock()
    select_result.fetchone.return_value = ("existing-issue-id",)
    conn.execute.return_value = select_result

    _file_pipeline_issue(
        conn,
        run_id=UUID("11111111-1111-1111-1111-111111111111"),
        issue_type="publication_section_zero_extraction",
        professor_id="PROF-1",
        message="Detected publication section but extracted zero publication records",
        details={"homepage_url": "https://example.edu/prof"},
    )

    assert conn.execute.call_count == 2
    assert "SELECT issue_id" in conn.execute.call_args_list[0].args[0]
    update_sql = conn.execute.call_args_list[1].args[0]
    assert "UPDATE pipeline_issue" in update_sql
    assert "evidence_snapshot" in update_sql


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


def test_page_only_publication_preserves_doi_source_anchor(tmp_path):
    prof = _prof_row()
    conn = _mock_conn_with_profs([prof])
    publication = _pub(
        clean_title=(
            "Root hair developmental regulators orchestrate synthetic biology "
            "circuits in plants"
        ),
        source_anchor="https://doi.org/10.1038/s41467-024-54417-5",
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
        return_value=[publication],
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
            paper_id="paper:doi:10.1038/s41467-024-54417-5",
            is_new=True,
        )

        report = run_homepage_paper_ingest(
            conn,
            resume_checkpoint_path=tmp_path / "c.jsonl",
        )

        assert report.papers_linked_total == 1
        assert m_upsert_paper.call_args.kwargs["doi"] == (
            "10.1038/s41467-024-54417-5"
        )
        assert m_upsert_paper.call_args.kwargs["canonical_source"] == "prof_page_only"


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


def test_resume_set_excludes_zero_link_success_without_pipeline_issues(tmp_path):
    checkpoint = tmp_path / "c.jsonl"
    checkpoint.write_text(
        json.dumps(
            {
                "prof_id": "11111111-1111-1111-1111-111111111111",
                "homepage_url": "https://example.edu/prof/zero",
                "resume_key": (
                    "11111111-1111-1111-1111-111111111111|"
                    "https://example.edu/prof/zero"
                ),
                "status": "succeeded",
                "papers_linked": 0,
                "pipeline_issues": 0,
            }
        )
        + "\n"
    )

    assert _load_resume_set(checkpoint) == set()


def test_resume_set_keeps_success_with_linked_papers(tmp_path):
    checkpoint = tmp_path / "c.jsonl"
    resume_key = (
        "11111111-1111-1111-1111-111111111111|https://example.edu/prof/linked"
    )
    checkpoint.write_text(
        json.dumps(
            {
                "prof_id": "11111111-1111-1111-1111-111111111111",
                "homepage_url": "https://example.edu/prof/linked",
                "resume_key": resume_key,
                "status": "succeeded",
                "papers_linked": 2,
                "pipeline_issues": 0,
            }
        )
        + "\n"
    )

    assert _load_resume_set(checkpoint) == {resume_key}


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
