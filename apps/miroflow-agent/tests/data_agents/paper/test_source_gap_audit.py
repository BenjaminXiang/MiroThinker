from __future__ import annotations

from src.data_agents.paper.source_gap_audit import (
    PaperSourceGapLane,
    build_source_gap_audit_report,
    classify_source_gap_row,
    selection_hash_for_lane,
)


def _row(**overrides):
    base = {
        "paper_id": "PAPER-1",
        "title_clean": "Trustworthy Medical Image Analysis",
        "canonical_source": "crossref",
        "identity_status": "unverified",
        "quality_status": "needs_enrichment",
        "summary_zh": None,
        "abstract_clean": None,
        "full_text_abstract": None,
        "full_text_intro": None,
        "pdf_url": None,
        "doi": None,
        "arxiv_id": None,
        "openalex_id": None,
    }
    base.update(overrides)
    return base


def test_existing_source_text_wins_before_identifier_metadata_lane() -> None:
    result = classify_source_gap_row(
        _row(
            abstract_clean=(
                "This paper studies trustworthy artificial intelligence for "
                "medical imaging and evaluates robust diagnosis models."
            ),
            doi="10.1000/example",
        )
    )

    assert result.primary_lane == "existing_source_summary_fast_path"
    assert result.eligible_for_summary is True
    assert result.source_text_field == "abstract_clean"
    assert "identifier_metadata_enrichment" in result.secondary_lanes


def test_intro_only_with_existing_summary_is_not_summary_fast_path() -> None:
    result = classify_source_gap_row(
        _row(
            summary_zh="这篇论文已有中文摘要，因此 intro 不能再作为缺失 abstract_clean 的补写来源。",
            abstract_clean=None,
            full_text_intro=(
                "This introduction explains the broader motivation and related "
                "technical context, but it is not an abstract that can safely "
                "backfill abstract_clean."
            ),
            pdf_url="https://example.edu/paper.pdf",
            openalex_id="W123",
        )
    )

    assert result.primary_lane == "identifier_metadata_enrichment"
    assert result.eligible_for_summary is False
    assert result.source_text_field is None
    assert "professor_page_full_text_acquisition" in result.secondary_lanes


def test_full_text_abstract_with_existing_summary_is_fast_path_for_abstract_backfill() -> None:
    result = classify_source_gap_row(
        _row(
            summary_zh="这篇论文已有中文摘要，但 abstract_clean 仍然缺失。",
            abstract_clean=None,
            full_text_abstract=(
                "This full text abstract provides the paper objective, method, "
                "experimental setup, and main result in a source-grounded form."
            ),
            pdf_url="https://example.edu/paper.pdf",
        )
    )

    assert result.primary_lane == "existing_source_summary_fast_path"
    assert result.eligible_for_summary is False
    assert result.source_text_field == "full_text_abstract"


def test_identifier_metadata_lane_requires_identifier_without_source_text() -> None:
    result = classify_source_gap_row(_row(openalex_id="W123"))

    assert result.primary_lane == "identifier_metadata_enrichment"
    assert result.eligible_for_summary is False
    assert result.skip_reason == "missing_usable_source_text"


def test_citation_metadata_abstract_is_not_existing_source_fast_path() -> None:
    result = classify_source_gap_row(
        _row(
            abstract_clean=(
                "Xiaozhi Wang, Hao Peng, Yong Guan, Kaisheng Zeng. "
                "Proceedings of the 62nd Annual Meeting of the Association "
                "for Computational Linguistics (Volume 1: Long Papers). 2024."
            ),
            openalex_id="W123",
        )
    )

    assert result.primary_lane == "identifier_metadata_enrichment"
    assert result.eligible_for_summary is False
    assert result.source_text_field is None


def test_full_text_pdf_lane_precedes_prof_page_title_cleanup() -> None:
    result = classify_source_gap_row(
        _row(canonical_source="prof_page_only", pdf_url="https://example.edu/a.pdf")
    )

    assert result.primary_lane == "professor_page_full_text_acquisition"
    assert result.secondary_lanes == ("prof_page_only_title_parser_cleanup",)


def test_prof_page_only_without_identifier_or_source_stays_parser_residual() -> None:
    result = classify_source_gap_row(_row(canonical_source="prof_page_only"))

    assert result.primary_lane == "prof_page_only_title_parser_cleanup"
    assert result.eligible_for_summary is False
    assert result.skip_reason == "prof_page_only_missing_identifier_or_source"


def test_terminal_paper_state_is_unsafe_before_other_lanes() -> None:
    result = classify_source_gap_row(
        _row(
            identity_status="merged",
            abstract_clean="This abstract is long enough to otherwise be summarized.",
        )
    )

    assert result.primary_lane == "unsafe_row"
    assert result.skip_reason == "terminal_identity_status"


def test_report_counts_samples_and_selection_hashes_are_deterministic() -> None:
    rows = [
        _row(
            paper_id="PAPER-A",
            abstract_clean=(
                "This paper studies trustworthy artificial intelligence for "
                "medical imaging and evaluates robust diagnosis models."
            ),
        ),
        _row(paper_id="PAPER-B", openalex_id="W123"),
        _row(paper_id="PAPER-C", canonical_source="prof_page_only"),
        _row(paper_id="PAPER-D", quality_status="rejected"),
    ]

    report = build_source_gap_audit_report(rows, sample_limit=2)

    assert report.total_rows == 4
    assert report.lane_counts == {
        "existing_source_summary_fast_path": 1,
        "identifier_metadata_enrichment": 1,
        "prof_page_only_title_parser_cleanup": 1,
        "unsafe_row": 1,
    }
    assert report.source_buckets == {
        "crossref": 3,
        "prof_page_only": 1,
    }
    assert report.lanes["existing_source_summary_fast_path"].sample_paper_ids == (
        "PAPER-A",
    )
    assert report.lanes["existing_source_summary_fast_path"].selection_hash == (
        selection_hash_for_lane(
            PaperSourceGapLane.EXISTING_SOURCE_SUMMARY_FAST_PATH,
            ["PAPER-A"],
        )
    )
    assert report.lanes["identifier_metadata_enrichment"].selection_hash == (
        selection_hash_for_lane(
            PaperSourceGapLane.IDENTIFIER_METADATA_ENRICHMENT,
            ["PAPER-B"],
        )
    )
