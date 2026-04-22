"""RED-phase tests for M2.4 Unit 6 — run_homepage_paper_ingest orchestrator.

Hermetic tests — mock psycopg.Connection + the M2.1/M2.2/M2.3 helpers + M2.4's
homepage HTTP. Verify branch logic: skip-via-resume, per-prof savepoint isolation,
pipeline_issue filing, dry-run writes nothing, full-text skip when row exists.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from src.data_agents.paper.full_text_fetcher import FullTextExtract
from src.data_agents.paper.homepage_ingest import (
    IngestReport,
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
) -> dict:
    return {
        "professor_id": prof_id or str(uuid.uuid4()),
        "canonical_name": name,
        "institution": institution,
        "homepage_url": homepage_url,
    }


def _pub(
    *,
    clean_title: str = "Deep Learning for Images",
    authors_text: str | None = "A. Smith, J. Doe",
    year: int | None = 2023,
) -> HomepagePublication:
    return HomepagePublication(
        raw_title=f"[1] {clean_title} [J]",
        clean_title=clean_title,
        authors_text=authors_text,
        venue_text="NeurIPS",
        year=year,
        source_url="https://example.edu/prof/x",
        source_anchor=None,
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


def test_happy_path_evidence_source_type_is_personal_homepage(tmp_path):
    """link writer must receive evidence_source_type='personal_homepage'."""
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
        assert kwargs.get("evidence_source_type") == "personal_homepage"


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


def test_all_titles_unresolvable_files_pipeline_issue(tmp_path):
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
        return_value=None,  # all unresolvable
    ), patch(
        "src.data_agents.paper.homepage_ingest._file_pipeline_issue"
    ) as m_issue:
        m_extract.return_value = [_pub(clean_title=f"Obscure {i}") for i in range(5)]
        report = run_homepage_paper_ingest(
            conn, resume_checkpoint_path=tmp_path / "c.jsonl"
        )

        assert report.papers_linked_total == 0
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


def test_keyboard_interrupt_closes_run_as_cancelled(tmp_path):
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
        # close_pipeline_run called with status="cancelled"
        m_close.assert_called_once()
        assert m_close.call_args.kwargs.get("status") == "cancelled"


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
