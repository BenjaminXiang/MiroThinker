from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

from src.data_agents.professor.core_profile_paper_quality_audit import (
    AuditCaseResult,
    BaselinePaperMetrics,
    BaselineProfessorMetrics,
    CoreProfilePaperQualityAuditInputs,
    DatasetClosureBucketRow,
    DatasetClosureBuckets,
)


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "run_professor_core_profile_paper_quality_audit.py"
)


def _import_cli():
    spec = importlib.util.spec_from_file_location(
        "run_professor_core_profile_paper_quality_audit",
        _SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cli_run_prints_read_only_baseline_report(monkeypatch) -> None:
    cli = _import_cli()

    def fake_load_inputs(conn, *, cases_path=None):
        assert conn == "CONN"
        assert cases_path is None
        return CoreProfilePaperQualityAuditInputs(
            professor_metrics=BaselineProfessorMetrics(
                total=1,
                ready=1,
                summary_lt_150=0,
                summary_lt_200=1,
                ready_summary_lt_200=1,
                has_research_source_label=1,
                research_overview_storage_available=False,
                missing_research_overview_zh=1,
                professors_with_verified_papers=1,
                professors_with_verified_missing_paper_summary=1,
            ),
            paper_metrics=BaselinePaperMetrics(
                verified_links=2,
                linked_papers=2,
                linked_missing_abstract=1,
                linked_missing_summary_zh=1,
                linked_with_pdf=0,
                duplicate_title_year_groups=1,
                duplicate_affected_professors=1,
                duplicate_groups_with_enriched_row=1,
                canonical_source_distribution={"prof_page_only": 1, "crossref": 1},
                quality_status_distribution={"needs_enrichment": 2},
            ),
            cases=[
                AuditCaseResult(
                    case_id="ahmed-elazab",
                    entity_type="professor",
                    status="failing",
                    failures=["duplicate_verified_paper"],
                    evidence={"professor_id": "PROF-823D4761D493"},
                )
            ],
        )

    monkeypatch.setattr(cli, "load_audit_inputs", fake_load_inputs)
    output = io.StringIO()

    exit_code = cli.run(conn="CONN", output=output)

    assert exit_code == 1
    rendered = output.getvalue()
    assert '"readiness": "blocked"' in rendered
    assert '"case_id": "ahmed-elazab"' in rendered
    assert '"duplicate_verified_paper_title_year_groups:1"' in rendered
    assert "closure_buckets" not in rendered


def test_cli_run_can_include_read_only_bucketed_report(monkeypatch) -> None:
    cli = _import_cli()

    def fake_load_inputs(conn, *, cases_path=None):
        return CoreProfilePaperQualityAuditInputs(
            professor_metrics=BaselineProfessorMetrics(
                total=1,
                ready=1,
                summary_lt_150=0,
                summary_lt_200=1,
                ready_summary_lt_200=1,
                has_research_source_label=0,
                research_overview_storage_available=True,
                missing_research_overview_zh=0,
                professors_with_verified_papers=0,
                professors_with_verified_missing_paper_summary=0,
            ),
            paper_metrics=BaselinePaperMetrics.empty(),
            cases=[],
        )

    def fake_load_buckets(
        conn,
        *,
        professor_metrics,
        paper_metrics,
        bucket_limit,
    ):
        assert conn == "CONN"
        assert bucket_limit == 3
        assert professor_metrics.ready_summary_lt_200 == 1
        return DatasetClosureBuckets(
            bucket_limit=3,
            summary={
                "ready_summary_lt_200": {
                    "total": 1,
                    "sampled": 1,
                    "truncated": False,
                    "remediation_lane": "profile_summary_repair",
                }
            },
            rows=[
                DatasetClosureBucketRow(
                    blocker_type="ready_summary_lt_200",
                    entity_type="professor",
                    remediation_lane="profile_summary_repair",
                    professor_id="PROF-1",
                    current_status="ready",
                    automatic_eligibility=True,
                    skip_reason=None,
                    evidence={"profile_summary_length": 120},
                )
            ],
        )

    monkeypatch.setattr(cli, "load_audit_inputs", fake_load_inputs)
    monkeypatch.setattr(cli, "load_dataset_closure_buckets", fake_load_buckets)
    output = io.StringIO()

    exit_code = cli.run(
        conn="CONN",
        output=output,
        include_buckets=True,
        bucket_limit=3,
    )

    assert exit_code == 1
    rendered = output.getvalue()
    assert '"closure_buckets"' in rendered
    assert '"bucket_limit": 3' in rendered
    assert '"remediation_lane": "profile_summary_repair"' in rendered
