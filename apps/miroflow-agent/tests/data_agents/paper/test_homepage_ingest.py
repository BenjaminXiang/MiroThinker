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

import pytest

from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.paper.homepage_ingest import (
    IngestReport,
    _is_malformed_publication_title,
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
) -> dict:
    return {
        "professor_id": prof_id or str(uuid.uuid4()),
        "canonical_name": name,
        "institution": institution,
        "homepage_url": homepage_url,
        "homepage_page_role": homepage_page_role,
    }


def _pub(
    *,
    clean_title: str = "Deep Learning for Images",
    authors_text: str | None = "A. Smith, J. Doe",
    venue_text: str | None = "NeurIPS",
    year: int | None = 2023,
    pdf_url: str | None = None,
) -> HomepagePublication:
    return HomepagePublication(
        raw_title=f"[1] {clean_title} [J]",
        clean_title=clean_title,
        authors_text=authors_text,
        venue_text=venue_text,
        year=year,
        source_url="https://example.edu/prof/x",
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
        "Xu （学生）, T. Fan, M. Xu, L. Zeng",
        "Bagdi, P. R.; Zhang",
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


def test_resume_skips_already_processed_profs(tmp_path):
    prof1 = _prof_row(prof_id="11111111-1111-1111-1111-111111111111")
    prof2 = _prof_row(prof_id="22222222-2222-2222-2222-222222222222")
    conn = _mock_conn_with_profs([prof1, prof2])

    # Pre-populate checkpoint with prof1.
    checkpoint = tmp_path / "c.jsonl"
    checkpoint.write_text(
        json.dumps(
            {
                "prof_id": prof1["professor_id"],
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


def test_resume_tolerates_corrupted_checkpoint_lines(tmp_path):
    checkpoint = tmp_path / "c.jsonl"
    checkpoint.write_text(
        '{"prof_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "status": "succeeded"}\n'
        "not valid json\n"
        '{"prof_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "status": "succeeded"}\n'
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
