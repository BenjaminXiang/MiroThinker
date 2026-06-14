from __future__ import annotations

import pytest

from src.data_agents.professor.recollection_readiness import (
    SeedReadinessInput,
    assert_complete_matrix,
    build_readiness_matrix,
    format_readiness_matrix,
    load_readiness_inputs,
)


def _row(**overrides) -> SeedReadinessInput:
    defaults = dict(
        seed_id=6,
        school="香港中文大学（深圳）",
        department="人工智能学院",
        seed_url="https://sai.cuhk.edu.cn/teacher-search",
        last_run_status="success",
        resolver_result="cuhk_teacher_search",
        coverage_state="resolver_covered",
        latest_run_id="run-6",
        latest_run_status="succeeded",
        latest_trigger_mode="preview",
        latest_failure_class="success",
        diagnostic_profile_count=3,
        written_profile_count=0,
        latest_issue_id=None,
        latest_issue_failure_class=None,
    )
    defaults.update(overrides)
    return SeedReadinessInput(**defaults)


def test_preview_success_recommends_sample_not_full() -> None:
    matrix = build_readiness_matrix([_row()])

    assert matrix[0].recommended_next_mode == "sample"
    assert matrix[0].full_recollection_allowed is False
    assert matrix[0].decision_reason == "latest_preview_success_requires_sample"


def test_sample_success_with_written_profiles_allows_full_recollection() -> None:
    matrix = build_readiness_matrix(
        [
            _row(
                latest_run_id="sample-run",
                latest_trigger_mode="sample",
                latest_failure_class="success",
                diagnostic_profile_count=12,
                written_profile_count=3,
            )
        ]
    )

    assert matrix[0].recommended_next_mode == "full"
    assert matrix[0].full_recollection_allowed is True
    assert matrix[0].evidence_reference == "run:sample-run"


def test_latest_full_roster_success_is_not_reclassified_as_needing_preview() -> None:
    matrix = build_readiness_matrix(
        [
            _row(
                seed_id=25,
                school="电子科技大学（深圳）高等研究院",
                department="电子信息",
                seed_url="https://yjsjy.uestc.edu.cn/gmis/jcsjgl/dsfc?yxsh=25",
                resolver_result="uestc-yjsjy-mentor-roster",
                latest_run_id="full-roster-run",
                latest_run_status="succeeded",
                latest_trigger_mode="full",
                latest_failure_class="success",
                diagnostic_profile_count=42,
                written_profile_count=42,
            )
        ]
    )

    assert matrix[0].recommended_next_mode == "full"
    assert matrix[0].full_recollection_allowed is False
    assert matrix[0].decision_reason == "latest_full_success_complete"
    assert matrix[0].evidence_reference == "run:full-roster-run"


def test_latest_fetch_blocked_run_remains_blocked_even_with_resolver() -> None:
    matrix = build_readiness_matrix(
        [
            _row(
                seed_id=5,
                school="深圳大学",
                department="计算机与软件学院",
                seed_url="https://csse.szu.edu.cn/pages/teacherTeam/index?zc=1",
                last_run_status="failure",
                resolver_result="szu-teacher-family",
                latest_run_id="blocked-run",
                latest_run_status="failed",
                latest_trigger_mode="preview",
                latest_failure_class="fetch_blocked",
                diagnostic_profile_count=None,
                written_profile_count=None,
                latest_issue_id="issue-5",
                latest_issue_failure_class="fetch_blocked",
            )
        ]
    )

    assert matrix[0].recommended_next_mode == "blocked"
    assert matrix[0].full_recollection_allowed is False
    assert matrix[0].evidence_reference == "issue:issue-5"
    assert matrix[0].decision_reason == "latest_run_fetch_blocked"


def test_resolver_without_bounded_success_recommends_preview() -> None:
    matrix = build_readiness_matrix(
        [
            _row(
                latest_run_id=None,
                latest_run_status=None,
                latest_trigger_mode=None,
                latest_failure_class=None,
                diagnostic_profile_count=None,
                written_profile_count=None,
            )
        ]
    )

    assert matrix[0].recommended_next_mode == "preview"
    assert matrix[0].full_recollection_allowed is False
    assert matrix[0].decision_reason == "resolver_covered_needs_preview"


def test_missing_observed_seed_fails_completion() -> None:
    matrix = build_readiness_matrix([_row(seed_id=6)])

    with pytest.raises(ValueError, match="missing readiness rows: 7"):
        assert_complete_matrix([6, 7], matrix)


def test_formatted_matrix_includes_required_columns() -> None:
    lines = format_readiness_matrix(build_readiness_matrix([_row(seed_id=6)]))

    assert lines[0].split("\t") == [
        "seed_id",
        "school",
        "department",
        "seed_url",
        "last_run_status",
        "resolver_result",
        "coverage_state",
        "latest_run_id",
        "latest_run_status",
        "latest_trigger_mode",
        "latest_failure_class",
        "latest_issue_id",
        "recommended_next_mode",
        "full_recollection_allowed",
        "decision_reason",
        "evidence_reference",
    ]
    assert "\tsample\tFalse\tlatest_preview_success_requires_sample\trun:run-6" in lines[1]


class _FakeResult:
    def fetchall(self) -> list[dict]:
        return []


class _CapturingConn:
    def __init__(self) -> None:
        self.sql = ""

    def execute(self, sql: str):
        self.sql = sql
        return _FakeResult()


def test_load_readiness_inputs_guards_non_scalar_seed_id_casts() -> None:
    conn = _CapturingConn()

    assert load_readiness_inputs(conn, adapter_resolver=lambda _seed: None) == []

    assert "run_scope->>'seed_id' ~ '^\\d+$'" in conn.sql
    assert "evidence_snapshot->>'seed_id' ~ '^\\d+$'" in conn.sql


def test_load_readiness_inputs_ignores_backfill_runs_for_latest_seed_readiness() -> None:
    conn = _CapturingConn()

    assert load_readiness_inputs(conn, adapter_resolver=lambda _seed: None) == []

    compact_sql = " ".join(conn.sql.split())
    assert "FROM pipeline_run" in compact_sql
    assert "run_kind = 'roster_crawl'" in compact_sql
    assert "COALESCE(run_scope->>'trigger_mode', '') IN ('preview', 'sample', 'full')" in compact_sql
