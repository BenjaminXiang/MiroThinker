from __future__ import annotations

import json
from pathlib import Path

from src.data_agents.professor.core_profile_paper_quality_audit import (
    AuditCaseResult,
    BaselinePaperMetrics,
    BaselineProfessorMetrics,
    DatasetClosureBucketRow,
    _classify_duplicate_paper_bucket,
    _classify_professor_paper_summary_bucket,
    _classify_profile_summary_bucket,
    _classify_research_overview_bucket,
    _load_duplicate_paper_bucket_rows,
    build_core_profile_paper_quality_report,
    build_dataset_closure_bucket_report,
    evaluate_case_definitions,
    format_core_profile_paper_quality_report,
    load_case_definitions,
)


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "core_profile_paper_quality_cases.json"


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _PfedgpaAliasConn:
    def execute(self, sql, params=()):
        compact_sql = " ".join(sql.split())
        assert "paper_merge_alias requested_alias" in compact_sql
        assert params[0] == "PAPER-OLD-PFEDGPA"
        return _Cursor(
            {
                "paper_id": "PAPER-CANON-PFEDGPA",
                "title_clean": (
                    "pFedGPA: Diffusion-based Generative Parameter Aggregation "
                    "for Personalized Federated Learning"
                ),
                "arxiv_id": "2409.05701",
                "quality_status": "partial",
                "canonical_source": "crossref",
                "pdf_url": "https://arxiv.org/pdf/2409.05701v3",
                "alias_target": "PAPER-CANON-PFEDGPA",
            }
        )


class _DuplicateBucketSqlConn:
    def execute(self, sql, params=()):
        compact_sql = " ".join(sql.split())
        assert params == (5,)
        assert "LEFT JOIN paper_merge_alias pma ON pma.old_paper_id = ppl.paper_id" in (
            compact_sql
        )
        assert "COALESCE(pma.canonical_paper_id, ppl.paper_id) AS resolved_paper_id" in (
            compact_sql
        )
        assert "JOIN paper p ON p.paper_id = vl.resolved_paper_id" in compact_sql
        assert "HAVING COUNT(DISTINCT vl.resolved_paper_id) > 1" in compact_sql
        return _CursorList([])


class _CursorList:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


def test_report_flags_professor_and_paper_quality_gaps() -> None:
    report = build_core_profile_paper_quality_report(
        professor_metrics=BaselineProfessorMetrics(
            total=3387,
            ready=1407,
            summary_lt_150=928,
            summary_lt_200=1100,
            ready_summary_lt_200=600,
            has_research_source_label=2379,
            research_overview_storage_available=False,
            missing_research_overview_zh=2379,
            professors_with_verified_papers=2202,
            professors_with_verified_missing_paper_summary=2202,
        ),
        paper_metrics=BaselinePaperMetrics(
            verified_links=49484,
            linked_papers=47853,
            linked_missing_abstract=37403,
            linked_missing_summary_zh=37477,
            linked_with_pdf=492,
            duplicate_title_year_groups=6563,
            duplicate_affected_professors=994,
            duplicate_groups_with_enriched_row=6315,
            canonical_source_distribution={"prof_page_only": 36063, "openalex": 11017},
            quality_status_distribution={"needs_enrichment": 34735, "ready": 9461},
        ),
        cases=[
            AuditCaseResult(
                case_id="ahmed-elazab",
                entity_type="professor",
                status="failing",
                failures=["missing_research_overview_zh", "duplicate_verified_paper"],
                evidence={"professor_id": "PROF-823D4761D493"},
            ),
            AuditCaseResult(
                case_id="pfedgpa",
                entity_type="paper",
                status="failing",
                failures=["missing_arxiv_pdf"],
                evidence={"paper_id": "PAPER-80EC1A859E64"},
            ),
        ],
    )

    assert report.readiness == "blocked"
    assert "ready_summary_lt_200:600" in report.blockers
    assert "missing_research_overview_zh:2379" in report.blockers
    assert "missing_professor_paper_summary:2202" in report.blockers
    assert "duplicate_verified_paper_title_year_groups:6563" in report.blockers
    assert "case_failed:ahmed-elazab" in report.blockers
    assert "case_failed:pfedgpa" in report.blockers


def test_format_report_is_deterministic_json() -> None:
    report = build_core_profile_paper_quality_report(
        professor_metrics=BaselineProfessorMetrics.empty(),
        paper_metrics=BaselinePaperMetrics.empty(),
        cases=[],
    )

    rendered = format_core_profile_paper_quality_report(report)

    assert rendered.endswith("\n")
    assert '"readiness": "ready"' in rendered
    assert rendered.index('"blockers"') < rendered.index('"cases"')
    assert "closure_buckets" not in rendered


def test_format_report_can_include_dataset_closure_buckets() -> None:
    report = build_core_profile_paper_quality_report(
        professor_metrics=BaselineProfessorMetrics(
            total=10,
            ready=4,
            summary_lt_150=1,
            summary_lt_200=2,
            ready_summary_lt_200=1,
            has_research_source_label=3,
            research_overview_storage_available=True,
            missing_research_overview_zh=2,
            professors_with_verified_papers=5,
            professors_with_verified_missing_paper_summary=1,
        ),
        paper_metrics=BaselinePaperMetrics(
            verified_links=9,
            linked_papers=8,
            linked_missing_abstract=1,
            linked_missing_summary_zh=1,
            linked_with_pdf=1,
            duplicate_title_year_groups=1,
            duplicate_affected_professors=1,
            duplicate_groups_with_enriched_row=1,
            canonical_source_distribution={},
            quality_status_distribution={},
        ),
        cases=[],
    )
    buckets = build_dataset_closure_bucket_report(
        professor_metrics=report.professor_metrics,
        paper_metrics=report.paper_metrics,
        bucket_limit=5,
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-1",
                current_status="ready",
                automatic_eligibility=True,
                skip_reason=None,
                source_page_id="PAGE-1",
                source_url="https://example.edu/prof",
                evidence={"profile_summary_length": 120},
            ),
            DatasetClosureBucketRow(
                blocker_type="duplicate_verified_paper_title_year_groups",
                entity_type="paper_group",
                remediation_lane="duplicate_paper_merge",
                professor_id="PROF-2",
                duplicate_group_id="PROF-2:2024:exampletitle",
                current_status="verified_duplicate",
                automatic_eligibility=False,
                skip_reason="ambiguous_fuzzy_match",
                evidence={"paper_ids": ["PAPER-1", "PAPER-2"]},
            ),
        ],
    )

    rendered = format_core_profile_paper_quality_report(
        report,
        closure_buckets=buckets,
    )
    payload = json.loads(rendered)

    assert payload["closure_buckets"]["bucket_limit"] == 5
    assert payload["closure_buckets"]["summary"]["ready_summary_lt_200"] == {
        "total": 1,
        "sampled": 1,
        "truncated": False,
        "remediation_lane": "profile_summary_repair",
    }
    assert payload["closure_buckets"]["summary"][
        "duplicate_verified_paper_title_year_groups"
    ]["total"] == 1
    assert payload["closure_buckets"]["rows"][0]["professor_id"] == "PROF-1"
    assert payload["closure_buckets"]["rows"][0]["source_page_id"] == "PAGE-1"
    assert (
        payload["closure_buckets"]["rows"][1]["skip_reason"]
        == "ambiguous_fuzzy_match"
    )


def test_dataset_closure_bucket_classifiers_are_stable() -> None:
    assert _classify_profile_summary_bucket(
        has_grounded_facts=True,
        has_profile_raw_text=False,
    ) == (True, None)
    assert _classify_profile_summary_bucket(
        has_grounded_facts=False,
        has_profile_raw_text=False,
    ) == (False, "missing_grounded_profile_inputs")

    assert _classify_research_overview_bucket("研究方向：人工智能。") == (
        True,
        None,
        "zh",
    )
    assert _classify_research_overview_bucket("Research interests: AI.") == (
        True,
        None,
        "en",
    )
    assert _classify_research_overview_bucket("  ") == (
        False,
        "missing_official_source_text",
        None,
    )

    assert _classify_professor_paper_summary_bucket(
        duplicate_group_count=0,
    ) == (True, None)
    assert _classify_professor_paper_summary_bucket(
        duplicate_group_count=2,
    ) == (False, "duplicate_verified_paper_links")

    assert _classify_duplicate_paper_bucket(
        has_enriched_row=True,
        doi_count=1,
        arxiv_count=0,
    ) == (True, None)
    assert _classify_duplicate_paper_bucket(
        has_enriched_row=False,
        doi_count=1,
        arxiv_count=0,
    ) == (False, "ambiguous_fuzzy_match")
    assert _classify_duplicate_paper_bucket(
        has_enriched_row=True,
        doi_count=0,
        arxiv_count=0,
    ) == (False, "ambiguous_fuzzy_match")


def test_duplicate_paper_bucket_loader_resolves_merge_aliases_before_grouping() -> None:
    assert _load_duplicate_paper_bucket_rows(
        _DuplicateBucketSqlConn(),
        bucket_limit=5,
    ) == []


def test_case_fixture_covers_required_badcases() -> None:
    cases = load_case_definitions(_FIXTURE_PATH)
    by_id = {case["case_id"]: case for case in cases}

    assert {"ahmed-elazab", "ding-wenbo", "pfedgpa"} <= set(by_id)
    assert by_id["ahmed-elazab"]["expected_failures"] == [
        "missing_research_overview_zh",
        "duplicate_verified_paper",
        "missing_paper_summary",
    ]
    assert by_id["ding-wenbo"]["professor_core_readiness_excludes"] == [
        "hidden_company_roles"
    ]
    assert by_id["pfedgpa"]["expected_external_identifier"] == "arxiv:2409.05701"

    # Keep the fixture valid JSON because it is also used as run evidence.
    assert json.loads(_FIXTURE_PATH.read_text(encoding="utf-8")) == cases


def test_pfedgpa_case_evaluates_canonical_alias_target() -> None:
    results = evaluate_case_definitions(
        _PfedgpaAliasConn(),
        [
            {
                "case_id": "pfedgpa",
                "entity_type": "paper",
                "paper_id": "PAPER-OLD-PFEDGPA",
                "title": (
                    "pFedGPA: Diffusion-based Generative Parameter Aggregation "
                    "for Personalized Federated Learning"
                ),
                "expected_external_identifier": "arxiv:2409.05701",
            }
        ],
    )

    assert len(results) == 1
    case = results[0]
    assert case.status == "passing"
    assert case.failures == []
    assert case.evidence["paper_id"] == "PAPER-CANON-PFEDGPA"
    assert case.evidence["expected_route"] == "/paper/PAPER-CANON-PFEDGPA"
    assert case.evidence["merged_from_paper_id"] == "PAPER-OLD-PFEDGPA"
