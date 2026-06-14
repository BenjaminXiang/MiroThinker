from __future__ import annotations

from src.data_agents.professor.post_full_quality_audit import (
    FieldDefectInput,
    FullRunEvidence,
    PostFullQualityMetrics,
    build_post_full_audit_report,
    format_post_full_audit_report,
)


def test_report_requires_latest_successful_full_runs_for_all_p7_seed_ids() -> None:
    report = build_post_full_audit_report(
        selected_seed_ids=[7, 8],
        full_runs=[
            FullRunEvidence(
                seed_id=7,
                run_id="RUN-7",
                status="succeeded",
                trigger_mode="full",
                failure_class="success",
                items_processed=98,
                items_failed=0,
                written_profile_count=98,
                diagnostic_profile_count=98,
            )
        ],
        metrics=PostFullQualityMetrics.empty(canonical_total=98),
        blocked_seed_ids=[5],
        field_defects=[],
    )

    assert [row.seed_id for row in report.full_run_coverage] == [7, 8]
    assert report.full_run_coverage[0].coverage_state == "covered"
    assert report.full_run_coverage[1].coverage_state == "missing"
    assert report.full_run_coverage[1].reason == "missing_latest_full_run"
    assert report.p9_readiness == "blocked"
    assert "missing_full_run_seed:8" in report.p9_blockers


def test_report_tracks_blocked_seed_carryover_and_known_bresar_defect() -> None:
    report = build_post_full_audit_report(
        selected_seed_ids=[7],
        full_runs=[
            FullRunEvidence(
                seed_id=7,
                run_id="RUN-7",
                status="succeeded",
                trigger_mode="full",
                failure_class="success",
                items_processed=98,
                items_failed=0,
                written_profile_count=98,
                diagnostic_profile_count=98,
            )
        ],
        metrics=PostFullQualityMetrics.empty(canonical_total=98),
        blocked_seed_ids=[5],
        field_defects=[
            FieldDefectInput(
                defect_id="cuhk-sds-bresar-title",
                professor_id="PROF-6553974C5393",
                canonical_name="BRESAR, Miha",
                source_url="https://sds.cuhk.edu.cn/teacher/2238",
                field_name="professor_affiliation.title",
                current_value="BRESAR, Miha | 香港中文大学（深圳）数据科学学院 URL Source: https://sds.cuhk.edu.cn/teacher/2238 Markdown Content: ## BRESAR, Miha 助理教授 教育背景 博士",
                expected_value="助理教授",
            )
        ],
    )

    assert report.blocked_seed_carryover == [5]
    assert len(report.known_field_defects) == 1
    defect = report.known_field_defects[0]
    assert defect.status == "unresolved"
    assert defect.expected_value == "助理教授"
    assert defect.current_value_preview.startswith("BRESAR, Miha |")
    assert "URL Source" in defect.contamination_markers
    assert "教育背景" in defect.contamination_markers
    assert report.p9_readiness == "blocked"
    assert "field_defect:cuhk-sds-bresar-title" in report.p9_blockers


def test_format_report_is_deterministic_json() -> None:
    report = build_post_full_audit_report(
        selected_seed_ids=[7],
        full_runs=[
            FullRunEvidence(
                seed_id=7,
                run_id="RUN-7",
                status="succeeded",
                trigger_mode="full",
                failure_class="success",
                items_processed=98,
                items_failed=0,
                written_profile_count=98,
                diagnostic_profile_count=98,
            )
        ],
        metrics=PostFullQualityMetrics.empty(canonical_total=98),
        blocked_seed_ids=[],
        field_defects=[],
    )

    rendered = format_post_full_audit_report(report)

    assert rendered.endswith("\n")
    assert '"p9_readiness": "ready"' in rendered
    assert '"canonical_total": 98' in rendered
    assert rendered.index('"blocked_seed_carryover"') < rendered.index('"canonical_total"')
