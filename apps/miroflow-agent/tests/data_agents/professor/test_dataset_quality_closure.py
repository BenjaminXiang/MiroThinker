from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.data_agents.professor.core_profile_paper_quality_audit import (
    DatasetClosureBucketRow,
    DatasetClosureBuckets,
)
from src.data_agents.professor.quality_gate import ProfessorQualityEvaluation
from src.data_agents.professor.dataset_quality_closure import (
    AffectedAuditEvidence,
    ApiSampleEvidence,
    ClosureRowWriteResult,
    DatasetClosureWriters,
    DryRunEvidenceRequired,
    DryRunEvidenceMismatch,
    IndexRefreshEvidence,
    PostWriteVerificationCallbacks,
    QualityReevaluationEvidence,
    build_lane_dry_run_report,
    build_post_write_verification_report,
    default_dataset_closure_writers,
    default_post_write_verification_callbacks,
    file_residual_risk_issues_for_buckets,
    build_residual_risk_coverage_report,
    require_dry_run_evidence_for_write,
    run_dataset_closure_write_batch,
)
from src.data_agents.professor import dataset_quality_closure as closure_module


def test_build_lane_dry_run_report_counts_every_lane() -> None:
    buckets = DatasetClosureBuckets(
        bucket_limit=5,
        summary={
            "ready_summary_lt_200": {
                "total": 441,
                "sampled": 2,
                "truncated": True,
                "remediation_lane": "profile_summary_repair",
            },
            "missing_research_overview_zh": {
                "total": 2510,
                "sampled": 1,
                "truncated": True,
                "remediation_lane": "research_overview_backfill",
            },
            "missing_professor_paper_summary": {
                "total": 2200,
                "sampled": 1,
                "truncated": True,
                "remediation_lane": "professor_paper_summary_generation",
            },
            "duplicate_verified_paper_title_year_groups": {
                "total": 5186,
                "sampled": 2,
                "truncated": True,
                "remediation_lane": "duplicate_paper_merge",
            },
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-SHORT-1",
                current_status="ready",
                automatic_eligibility=True,
                evidence={"profile_summary_length": 180},
            ),
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-SHORT-2",
                current_status="ready",
                automatic_eligibility=False,
                skip_reason="missing_grounded_profile_inputs",
            ),
            DatasetClosureBucketRow(
                blocker_type="missing_research_overview_zh",
                entity_type="professor",
                remediation_lane="research_overview_backfill",
                professor_id="PROF-OVERVIEW-1",
                automatic_eligibility=True,
                evidence={"source_language": "en"},
            ),
            DatasetClosureBucketRow(
                blocker_type="missing_professor_paper_summary",
                entity_type="professor",
                remediation_lane="professor_paper_summary_generation",
                professor_id="PROF-PAPER-SUMMARY-1",
                automatic_eligibility=True,
                evidence={"verified_paper_count": 4},
            ),
            DatasetClosureBucketRow(
                blocker_type="duplicate_verified_paper_title_year_groups",
                entity_type="paper_group",
                remediation_lane="duplicate_paper_merge",
                professor_id="PROF-DUP-1",
                duplicate_group_id="PROF-DUP-1:2024:title",
                automatic_eligibility=True,
                evidence={"paper_ids": ["PAPER-1", "PAPER-2"], "doi_count": 1},
            ),
            DatasetClosureBucketRow(
                blocker_type="duplicate_verified_paper_title_year_groups",
                entity_type="paper_group",
                remediation_lane="duplicate_paper_merge",
                professor_id="PROF-DUP-2",
                duplicate_group_id="PROF-DUP-2:2024:title",
                automatic_eligibility=False,
                skip_reason="ambiguous_fuzzy_match",
                evidence={"paper_ids": ["PAPER-3", "PAPER-4"]},
            ),
        ],
    )

    report = build_lane_dry_run_report(
        buckets,
        lanes=(
            "profile_summary_repair",
            "research_overview_backfill",
            "professor_paper_summary_generation",
            "duplicate_paper_merge",
        ),
    )

    assert report.dry_run is True
    assert report.mode == "dry_run"
    assert report.bucket_limit == 5
    assert report.write_allowed is False
    assert report.selection_hash

    by_lane = {lane.lane: lane for lane in report.lanes}
    profile = by_lane["profile_summary_repair"]
    assert profile.dataset_input_count == 441
    assert profile.input_count == 2
    assert profile.eligible_count == 1
    assert profile.proposed_write_count == 1
    assert profile.skipped_count == 1
    assert profile.validation_failure_count == 0
    assert profile.provider_failure_count == 0
    assert profile.validation_rules == ("profile_summary_200_300_zh_contract",)
    assert profile.affected_professor_ids == ("PROF-SHORT-1",)
    assert profile.skip_reason_counts == {"missing_grounded_profile_inputs": 1}

    duplicate = by_lane["duplicate_paper_merge"]
    assert duplicate.dataset_input_count == 5186
    assert duplicate.input_count == 2
    assert duplicate.eligible_count == 1
    assert duplicate.skipped_count == 1
    assert duplicate.affected_professor_ids == ("PROF-DUP-1",)
    assert duplicate.affected_paper_ids == ("PAPER-1", "PAPER-2")
    assert duplicate.skip_reason_counts == {"ambiguous_fuzzy_match": 1}


def test_write_mode_requires_matching_dry_run_evidence() -> None:
    with pytest.raises(DryRunEvidenceRequired) as exc:
        require_dry_run_evidence_for_write(
            lanes=("profile_summary_repair",),
            evidence_path=None,
        )

    assert "dry-run evidence" in str(exc.value)


def test_profile_summary_dry_run_excludes_invalid_candidate_summary() -> None:
    buckets = DatasetClosureBuckets(
        bucket_limit=2,
        summary={
            "ready_summary_lt_200": {
                "total": 2,
                "sampled": 2,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-VALID",
                automatic_eligibility=True,
                evidence={
                    "candidate_profile_summary": (
                        "张三现任深圳高校教授，长期从事人工智能、医学影像和可信机器学习研究。"
                        "其工作围绕多模态数据融合、模型可解释性和临床辅助诊断展开，结合算法设计、"
                        "系统验证和真实场景应用，形成稳定研究方向。公开资料能够支撑其身份、"
                        "研究主题和代表性论文之间的关联，适合作为教师核心资料的高质量样例。"
                        "相关成果覆盖脑疾病诊断、图像分割和风险预测，并体现出清晰的学术脉络、"
                        "持续产出能力和可用于后续论文摘要生成的结构化证据基础与验证依据。"
                    )
                },
            ),
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-INVALID",
                automatic_eligibility=True,
                evidence={"candidate_profile_summary": "Too short."},
            ),
        ],
    )

    report = build_lane_dry_run_report(buckets, lanes=("profile_summary_repair",))
    profile = report.lanes[0]

    assert profile.eligible_count == 2
    assert profile.validation_failure_count == 1
    assert profile.proposed_write_count == 1
    assert profile.affected_professor_ids == ("PROF-VALID",)


def test_write_batch_requires_real_run_id_and_matching_dry_run_evidence() -> None:
    buckets = _write_batch_buckets()
    evidence = build_lane_dry_run_report(buckets, lanes=("profile_summary_repair",))

    with pytest.raises(ValueError, match="requires run_id"):
        run_dataset_closure_write_batch(
            conn=object(),
            buckets=buckets,
            lanes=("profile_summary_repair",),
            dry_run_evidence=evidence,
            run_id=None,
            writers=DatasetClosureWriters(),
        )

    stale_buckets = DatasetClosureBuckets(
        bucket_limit=1,
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
                professor_id="PROF-STALE",
                automatic_eligibility=True,
            )
        ],
    )

    with pytest.raises(DryRunEvidenceMismatch, match="selection_hash"):
        run_dataset_closure_write_batch(
            conn=object(),
            buckets=stale_buckets,
            lanes=("profile_summary_repair",),
            dry_run_evidence=evidence,
            run_id="11111111-1111-1111-1111-111111111111",
            writers=DatasetClosureWriters(),
        )


def test_write_batch_limits_rows_and_records_rollback_evidence() -> None:
    buckets = _write_batch_buckets()
    evidence = build_lane_dry_run_report(buckets, lanes=("profile_summary_repair",))
    calls: list[str] = []

    def writer(_conn, row, run_id):
        calls.append(row.professor_id or "")
        assert run_id == "11111111-1111-1111-1111-111111111111"
        return ClosureRowWriteResult(
            status="written",
            changed_professor_ids=(row.professor_id or "",),
            rollback_evidence={
                "table": "professor",
                "field": "profile_summary",
                "professor_id": row.professor_id,
                "before": "旧摘要",
                "after": "新摘要",
            },
        )

    report = run_dataset_closure_write_batch(
        conn=object(),
        buckets=buckets,
        lanes=("profile_summary_repair",),
        dry_run_evidence=evidence,
        run_id="11111111-1111-1111-1111-111111111111",
        batch_size=1,
        writers=DatasetClosureWriters(profile_summary_writer=writer),
    )

    assert calls == ["PROF-WRITE-1"]
    assert report.mode == "write"
    assert report.write_allowed is True
    assert report.batch_size == 1
    assert report.dry_run_selection_hash == evidence.selection_hash
    summary = report.lanes[0]
    assert summary.attempted_count == 1
    assert summary.written_count == 1
    assert summary.unchanged_count == 0
    assert summary.failed_count == 0
    assert summary.changed_professor_ids == ("PROF-WRITE-1",)
    assert summary.rollback_evidence[0]["before"] == "旧摘要"


def test_write_batch_reports_partial_failures_and_unchanged_reruns() -> None:
    buckets = _write_batch_buckets()
    evidence = build_lane_dry_run_report(buckets, lanes=("profile_summary_repair",))

    def writer(_conn, row, _run_id):
        if row.professor_id == "PROF-WRITE-1":
            return ClosureRowWriteResult(status="unchanged")
        raise RuntimeError("profile generator failed")

    report = run_dataset_closure_write_batch(
        conn=object(),
        buckets=buckets,
        lanes=("profile_summary_repair",),
        dry_run_evidence=evidence,
        run_id="11111111-1111-1111-1111-111111111111",
        batch_size=2,
        writers=DatasetClosureWriters(profile_summary_writer=writer),
    )

    summary = report.lanes[0]
    assert summary.attempted_count == 2
    assert summary.written_count == 0
    assert summary.unchanged_count == 1
    assert summary.failed_count == 1
    assert summary.unresolved_issue_count == 1
    assert summary.issues[0]["professor_id"] == "PROF-WRITE-2"
    assert summary.issues[0]["reason"] == "profile generator failed"


def test_default_writers_persist_candidate_evidence_for_all_write_lanes() -> None:
    buckets = _all_lane_candidate_buckets()
    evidence = build_lane_dry_run_report(
        buckets,
        lanes=(
            "profile_summary_repair",
            "research_overview_backfill",
            "professor_paper_summary_generation",
            "duplicate_paper_merge",
        ),
    )
    conn = _WriteConn()

    report = run_dataset_closure_write_batch(
        conn=conn,
        buckets=buckets,
        lanes=(
            "profile_summary_repair",
            "research_overview_backfill",
            "professor_paper_summary_generation",
            "duplicate_paper_merge",
        ),
        dry_run_evidence=evidence,
        run_id="11111111-1111-1111-1111-111111111111",
        batch_size=4,
        writers=default_dataset_closure_writers(),
    )

    summaries = {summary.lane: summary for summary in report.lanes}
    assert summaries["profile_summary_repair"].written_count == 1
    assert summaries["research_overview_backfill"].written_count == 1
    assert summaries["professor_paper_summary_generation"].written_count == 1
    assert summaries["duplicate_paper_merge"].written_count == 1
    assert summaries["profile_summary_repair"].rollback_evidence[0]["field"] == (
        "profile_summary"
    )
    assert summaries["duplicate_paper_merge"].changed_paper_ids == (
        "PAPER-CANON",
        "PAPER-OLD",
    )
    compact_sql = " ".join(sql for sql, _params in conn.calls)
    assert "UPDATE professor" in compact_sql
    assert "INSERT INTO professor_profile_section" in compact_sql
    assert "INSERT INTO paper_merge_alias" in compact_sql


def test_post_write_verification_records_required_evidence() -> None:
    write_report = _write_report_with_changed_ids()

    report = build_post_write_verification_report(
        conn=object(),
        write_report=write_report,
        callbacks=PostWriteVerificationCallbacks(
            quality_re_evaluator=lambda _conn, professor_ids: QualityReevaluationEvidence(
                evaluated_professor_ids=professor_ids,
                before_distribution={"needs_enrichment": 1},
                after_distribution={"ready": 1},
            ),
            affected_audit_checker=lambda _conn, professor_ids, paper_ids: AffectedAuditEvidence(
                checked_professor_ids=professor_ids,
                checked_paper_ids=paper_ids,
                remaining_blocker_counts={},
            ),
            professor_detail_sampler=lambda _conn, professor_ids: ApiSampleEvidence(
                sampled_ids=professor_ids,
            ),
            paper_detail_sampler=lambda _conn, paper_ids: ApiSampleEvidence(
                sampled_ids=paper_ids,
            ),
            refresh_selector=lambda _conn, professor_ids, paper_ids, _run_id: IndexRefreshEvidence(
                professor_ids=professor_ids,
                paper_ids=paper_ids,
            ),
        ),
    )

    assert report.status == "success"
    assert report.completion_allowed is True
    assert report.changed_professor_ids == ("PROF-WRITE-1",)
    assert report.changed_paper_ids == ("PAPER-1",)
    assert report.quality_re_evaluation is not None
    assert report.quality_re_evaluation.after_distribution == {"ready": 1}
    assert report.affected_audit is not None
    assert report.affected_audit.remaining_blocker_counts == {}
    assert report.admin_professor_detail_samples.sampled_ids == ("PROF-WRITE-1",)
    assert report.paper_detail_samples is not None
    assert report.paper_detail_samples.sampled_ids == ("PAPER-1",)
    assert report.index_refresh_selection is not None
    assert report.index_refresh_selection.paper_ids == ("PAPER-1",)


def test_failed_post_write_sampling_blocks_completion() -> None:
    write_report = _write_report_with_changed_ids()

    report = build_post_write_verification_report(
        conn=object(),
        write_report=write_report,
        callbacks=PostWriteVerificationCallbacks(
            quality_re_evaluator=lambda _conn, professor_ids: QualityReevaluationEvidence(
                evaluated_professor_ids=professor_ids,
                before_distribution={"needs_enrichment": 1},
                after_distribution={"ready": 1},
            ),
            affected_audit_checker=lambda _conn, professor_ids, paper_ids: AffectedAuditEvidence(
                checked_professor_ids=professor_ids,
                checked_paper_ids=paper_ids,
                remaining_blocker_counts={},
            ),
            professor_detail_sampler=lambda _conn, professor_ids: ApiSampleEvidence(
                sampled_ids=(),
                failures=(
                    {
                        "stage": "admin_professor_detail_sample",
                        "id": professor_ids[0],
                        "reason": "404",
                    },
                ),
            ),
            paper_detail_sampler=lambda _conn, paper_ids: ApiSampleEvidence(
                sampled_ids=paper_ids,
            ),
            refresh_selector=lambda _conn, professor_ids, paper_ids, _run_id: IndexRefreshEvidence(
                professor_ids=professor_ids,
                paper_ids=paper_ids,
            ),
        ),
    )

    assert report.status == "failed"
    assert report.completion_allowed is False
    assert report.issues[0]["stage"] == "admin_professor_detail_sample"
    assert report.issues[0]["reason"] == "404"


def test_default_post_write_callbacks_collect_batch_verification_evidence(
    monkeypatch,
) -> None:
    persisted: list[str] = []
    monkeypatch.setattr(
        closure_module,
        "load_professor_canonical_states",
        lambda _conn, professor_ids: [
            SimpleNamespace(professor_id=professor_id) for professor_id in professor_ids
        ],
    )
    monkeypatch.setattr(
        closure_module,
        "evaluate_professor_quality",
        lambda state: ProfessorQualityEvaluation(
            professor_id=state.professor_id,
            quality_status="ready",
            reasons=(),
        ),
    )
    monkeypatch.setattr(
        closure_module,
        "persist_professor_quality_evaluation",
        lambda _conn, evaluation: persisted.append(evaluation.professor_id),
    )
    conn = _PostWriteConn(
        professor_rows=[
            {
                "professor_id": "PROF-WRITE-1",
                "profile_summary": _valid_profile_summary(),
                "paper_summary": "该教师论文围绕医学影像和可信人工智能展开。",
                "has_research_overview_zh": True,
                "verified_paper_count": 1,
            }
        ],
        paper_rows=[
            {
                "paper_id": "PAPER-1",
                "title_clean": "Trustworthy AI for Medical Imaging",
                "quality_status": "ready",
                "verified_professor_count": 1,
            }
        ],
        remaining_blockers={
            "ready_summary_lt_200": 0,
            "missing_research_overview_zh": 0,
            "missing_professor_paper_summary": 0,
            "duplicate_verified_paper_title_year_groups": 0,
        },
        quality_distribution={"needs_enrichment": 1},
    )

    report = build_post_write_verification_report(
        conn=conn,
        write_report=_write_report_with_changed_ids(),
        callbacks=default_post_write_verification_callbacks(),
    )

    assert report.status == "success"
    assert report.completion_allowed is True
    assert persisted == ["PROF-WRITE-1"]
    assert report.quality_re_evaluation is not None
    assert report.quality_re_evaluation.before_distribution == {"needs_enrichment": 1}
    assert report.quality_re_evaluation.after_distribution == {"ready": 1}
    assert report.affected_audit is not None
    assert report.affected_audit.remaining_blocker_counts == {}
    assert report.admin_professor_detail_samples is not None
    assert report.admin_professor_detail_samples.sampled_ids == ("PROF-WRITE-1",)
    assert report.paper_detail_samples is not None
    assert report.paper_detail_samples.sampled_ids == ("PAPER-1",)
    assert report.index_refresh_selection is not None
    assert report.index_refresh_selection.professor_ids == ("PROF-WRITE-1",)
    assert report.index_refresh_selection.paper_ids == ("PAPER-1",)


def test_default_post_write_callbacks_block_on_remaining_blocker_and_missing_detail(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        closure_module,
        "load_professor_canonical_states",
        lambda _conn, professor_ids: [
            SimpleNamespace(professor_id=professor_id) for professor_id in professor_ids
        ],
    )
    monkeypatch.setattr(
        closure_module,
        "evaluate_professor_quality",
        lambda state: ProfessorQualityEvaluation(
            professor_id=state.professor_id,
            quality_status="needs_enrichment",
            reasons=(),
        ),
    )
    monkeypatch.setattr(
        closure_module,
        "persist_professor_quality_evaluation",
        lambda _conn, _evaluation: None,
    )
    conn = _PostWriteConn(
        professor_rows=[],
        paper_rows=[],
        remaining_blockers={
            "ready_summary_lt_200": 1,
            "missing_research_overview_zh": 0,
            "missing_professor_paper_summary": 0,
            "duplicate_verified_paper_title_year_groups": 0,
        },
        quality_distribution={"needs_enrichment": 1},
    )

    report = build_post_write_verification_report(
        conn=conn,
        write_report=_write_report_with_changed_ids(),
        callbacks=default_post_write_verification_callbacks(),
    )

    assert report.status == "failed"
    assert report.completion_allowed is False
    issues = {(issue["stage"], issue["reason"]) for issue in report.issues}
    assert ("affected_id_closure_audit", "remaining_blockers") in issues
    assert ("admin_professor_detail_sample", "not_found") in issues
    assert ("paper_detail_sample", "not_found") in issues


def test_provider_only_author_results_do_not_create_professor_paper_summary() -> None:
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
        summary={
            "missing_professor_paper_summary": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "professor_paper_summary_generation",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="missing_professor_paper_summary",
                entity_type="professor",
                remediation_lane="professor_paper_summary_generation",
                professor_id="PROF-NO-OFFICIAL-PAPERS",
                automatic_eligibility=False,
                skip_reason="no_official_professor_paper_source",
                evidence={
                    "external_author_search_results": [
                        {"provider": "openalex", "title": "Provider-only paper"}
                    ]
                },
            )
        ],
    )
    evidence = build_lane_dry_run_report(
        buckets,
        lanes=("professor_paper_summary_generation",),
    )

    assert evidence.lanes[0].proposed_write_count == 0
    assert evidence.lanes[0].skip_reason_counts == {
        "no_official_professor_paper_source": 1
    }

    def provider_only_writer(_conn, _row, _run_id):
        raise AssertionError("provider-only rows must not reach writer")

    report = run_dataset_closure_write_batch(
        conn=object(),
        buckets=buckets,
        lanes=("professor_paper_summary_generation",),
        dry_run_evidence=evidence,
        run_id="11111111-1111-1111-1111-111111111111",
        writers=DatasetClosureWriters(
            professor_paper_summary_writer=provider_only_writer
        ),
    )

    summary = report.lanes[0]
    assert summary.attempted_count == 0
    assert summary.unresolved_issue_count == 1
    assert summary.issues[0]["reason"] == "no_official_professor_paper_source"


def test_hidden_company_roles_do_not_block_professor_core_summary_closure() -> None:
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
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
                professor_id="PROF-NO-COMPANY-ROLE",
                automatic_eligibility=True,
                evidence={
                    "has_profile_raw_text": True,
                    "hidden_company_role_status": "not_required_for_professor_core",
                    "candidate_profile_summary": _valid_profile_summary(),
                },
            )
        ],
    )

    evidence = build_lane_dry_run_report(buckets, lanes=("profile_summary_repair",))

    assert evidence.lanes[0].eligible_count == 1
    assert evidence.lanes[0].proposed_write_count == 1
    assert evidence.lanes[0].skip_reason_counts == {}


def test_external_enrichment_is_allowed_only_for_official_seeded_paper_candidates() -> None:
    buckets = DatasetClosureBuckets(
        bucket_limit=2,
        summary={
            "missing_professor_paper_summary": {
                "total": 2,
                "sampled": 2,
                "truncated": False,
                "remediation_lane": "professor_paper_summary_generation",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="missing_professor_paper_summary",
                entity_type="professor",
                remediation_lane="professor_paper_summary_generation",
                professor_id="PROF-OFFICIAL-SEED",
                automatic_eligibility=True,
                evidence={
                    "verified_paper_count": 2,
                    "official_professor_seeded_paper_ids": ["PAPER-OFFICIAL-1"],
                    "external_enrichment_used_for": ["PAPER-OFFICIAL-1"],
                },
            ),
            DatasetClosureBucketRow(
                blocker_type="missing_professor_paper_summary",
                entity_type="professor",
                remediation_lane="professor_paper_summary_generation",
                professor_id="PROF-EXTERNAL-ONLY",
                automatic_eligibility=False,
                skip_reason="external_provider_only_author_match",
                evidence={
                    "verified_paper_count": 0,
                    "external_author_search_results": [
                        {"provider": "semantic_scholar", "title": "External only"}
                    ],
                },
            ),
        ],
    )

    evidence = build_lane_dry_run_report(
        buckets,
        lanes=("professor_paper_summary_generation",),
    )

    assert evidence.lanes[0].proposed_write_count == 1
    assert evidence.lanes[0].affected_professor_ids == ("PROF-OFFICIAL-SEED",)
    assert evidence.lanes[0].skip_reason_counts == {
        "external_provider_only_author_match": 1
    }


def test_residual_risk_issue_filing_requires_full_bucket_coverage() -> None:
    buckets = DatasetClosureBuckets(
        bucket_limit=1,
        summary={
            "ready_summary_lt_200": {
                "total": 2,
                "sampled": 1,
                "truncated": True,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-1",
                automatic_eligibility=True,
            )
        ],
    )

    with pytest.raises(ValueError, match="full bucket coverage"):
        file_residual_risk_issues_for_buckets(
            conn=object(),
            buckets=buckets,
            run_id="11111111-1111-1111-1111-111111111111",
        )


def test_residual_risk_issue_filing_persists_next_action_and_is_idempotent() -> None:
    buckets = _residual_risk_buckets()
    conn = _ResidualRiskConn()

    first = file_residual_risk_issues_for_buckets(
        conn=conn,
        buckets=buckets,
        run_id="11111111-1111-1111-1111-111111111111",
    )
    second = file_residual_risk_issues_for_buckets(
        conn=conn,
        buckets=buckets,
        run_id="22222222-2222-2222-2222-222222222222",
    )

    assert first.input_count == 2
    assert first.inserted_count == 2
    assert first.updated_count == 0
    assert second.input_count == 2
    assert second.inserted_count == 0
    assert second.updated_count == 2
    assert len(conn.issues) == 2
    evidence = conn.issues[0]["evidence_snapshot"]
    assert evidence["issue_type"] == "professor_dataset_quality_closure_residual_risk"
    assert evidence["blocker_type"] == "ready_summary_lt_200"
    assert evidence["confidence_impact"]
    assert evidence["recommended_action"]
    assert evidence["next_action"] == evidence["recommended_action"]


def test_residual_risk_coverage_report_requires_open_issue_for_every_bucket() -> None:
    buckets = _residual_risk_buckets()
    conn = _ResidualRiskConn()

    missing = build_residual_risk_coverage_report(conn=conn, buckets=buckets)
    assert missing.status == "incomplete"
    assert missing.unclassified_count == 2

    file_residual_risk_issues_for_buckets(
        conn=conn,
        buckets=buckets,
        run_id="11111111-1111-1111-1111-111111111111",
    )

    covered = build_residual_risk_coverage_report(conn=conn, buckets=buckets)
    assert covered.status == "complete"
    assert covered.unclassified_count == 0
    assert covered.covered_by_blocker == {
        "duplicate_verified_paper_title_year_groups": 1,
        "ready_summary_lt_200": 1,
    }


class _Cursor:
    def __init__(self, row=None) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _WriteConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        compact = " ".join(str(sql).split())
        if compact.startswith("SELECT profile_summary"):
            return _Cursor({"profile_summary": "旧摘要"})
        if compact.startswith("SELECT paper_summary"):
            return _Cursor({"paper_summary": None, "patent_summary": None})
        if "INSERT INTO professor_profile_section" in compact:
            return _Cursor({"section_id": "SECTION-1"})
        if "INSERT INTO paper_merge_alias" in compact:
            return _Cursor({"alias_id": "ALIAS-1"})
        return _Cursor()


class _RowsCursor:
    def __init__(self, rows=None) -> None:
        self._rows = rows or []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _PostWriteConn:
    def __init__(
        self,
        *,
        professor_rows: list[dict[str, object]],
        paper_rows: list[dict[str, object]],
        remaining_blockers: dict[str, int],
        quality_distribution: dict[str, int],
    ) -> None:
        self.professor_rows = professor_rows
        self.paper_rows = paper_rows
        self.remaining_blockers = remaining_blockers
        self.quality_distribution = quality_distribution
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        compact = " ".join(str(sql).split())
        if "GROUP BY quality_status" in compact:
            return _RowsCursor(
                [
                    {"quality_status": status, "count": count}
                    for status, count in self.quality_distribution.items()
                ]
            )
        if "AS ready_summary_lt_200" in compact:
            return _RowsCursor([self.remaining_blockers])
        if "AS duplicate_verified_paper_title_year_groups" in compact:
            return _RowsCursor(
                [
                    {
                        "duplicate_verified_paper_title_year_groups": self.remaining_blockers[
                            "duplicate_verified_paper_title_year_groups"
                        ]
                    }
                ]
            )
        if "has_research_overview_zh" in compact:
            return _RowsCursor(self.professor_rows)
        if "verified_professor_count" in compact:
            return _RowsCursor(self.paper_rows)
        return _RowsCursor([])


class _ResidualRiskConn:
    def __init__(self) -> None:
        self.issues: list[dict[str, object]] = []
        self.calls: list[tuple[str, object]] = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        compact = " ".join(str(sql).split())
        if compact.startswith("SELECT issue_id") and "FROM pipeline_issue" in compact:
            professor_id, institution, stage, reported_by, description = params
            for issue in self.issues:
                if (
                    issue["professor_id"] == professor_id
                    and issue["institution"] == institution
                    and issue["stage"] == stage
                    and issue["reported_by"] == reported_by
                    and issue["description"] == description
                    and not issue["resolved"]
                ):
                    return _RowsCursor([{"issue_id": issue["issue_id"]}])
            return _RowsCursor([])
        if compact.startswith("UPDATE pipeline_issue"):
            evidence, severity, issue_id = params
            evidence = getattr(evidence, "obj", evidence)
            for issue in self.issues:
                if issue["issue_id"] == issue_id:
                    issue["evidence_snapshot"] = evidence
                    issue["severity"] = severity
                    return _RowsCursor([])
        if compact.startswith("INSERT INTO pipeline_issue"):
            professor_id, institution, stage, severity, description, evidence, reported_by = (
                params
            )
            evidence = getattr(evidence, "obj", evidence)
            self.issues.append(
                {
                    "issue_id": f"ISSUE-{len(self.issues) + 1}",
                    "professor_id": professor_id,
                    "institution": institution,
                    "stage": stage,
                    "severity": severity,
                    "description": description,
                    "evidence_snapshot": evidence,
                    "reported_by": reported_by,
                    "resolved": False,
                }
            )
            return _RowsCursor([])
        if "COUNT(*)::int AS count" in compact and "FROM pipeline_issue" in compact:
            professor_id, institution, stage, reported_by, description, issue_type = params
            count = sum(
                1
                for issue in self.issues
                if issue["professor_id"] == professor_id
                and issue["institution"] == institution
                and issue["stage"] == stage
                and issue["reported_by"] == reported_by
                and issue["description"] == description
                and issue["evidence_snapshot"]["issue_type"] == issue_type
                and not issue["resolved"]
            )
            return _RowsCursor([{"count": count}])
        return _RowsCursor([])


def _write_report_with_changed_ids():
    buckets = _write_batch_buckets()
    evidence = build_lane_dry_run_report(buckets, lanes=("profile_summary_repair",))

    def writer(_conn, row, _run_id):
        return ClosureRowWriteResult(
            status="written",
            changed_professor_ids=(row.professor_id or "",),
            changed_paper_ids=("PAPER-1",),
            rollback_evidence={"professor_id": row.professor_id},
        )

    return run_dataset_closure_write_batch(
        conn=object(),
        buckets=buckets,
        lanes=("profile_summary_repair",),
        dry_run_evidence=evidence,
        run_id="11111111-1111-1111-1111-111111111111",
        batch_size=1,
        writers=DatasetClosureWriters(profile_summary_writer=writer),
    )


def _write_batch_buckets() -> DatasetClosureBuckets:
    return DatasetClosureBuckets(
        bucket_limit=2,
        summary={
            "ready_summary_lt_200": {
                "total": 2,
                "sampled": 2,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            }
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-WRITE-1",
                automatic_eligibility=True,
                evidence={"candidate_profile_summary": _valid_profile_summary()},
            ),
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-WRITE-2",
                automatic_eligibility=True,
                evidence={"candidate_profile_summary": _valid_profile_summary()},
            ),
        ],
    )


def _all_lane_candidate_buckets() -> DatasetClosureBuckets:
    return DatasetClosureBuckets(
        bucket_limit=4,
        summary={
            "ready_summary_lt_200": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            },
            "missing_research_overview_zh": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "research_overview_backfill",
            },
            "missing_professor_paper_summary": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "professor_paper_summary_generation",
            },
            "duplicate_verified_paper_title_year_groups": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "duplicate_paper_merge",
            },
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-PROFILE",
                automatic_eligibility=True,
                evidence={"candidate_profile_summary": _valid_profile_summary()},
            ),
            DatasetClosureBucketRow(
                blocker_type="missing_research_overview_zh",
                entity_type="professor",
                remediation_lane="research_overview_backfill",
                professor_id="PROF-SECTION",
                source_page_id="00000000-0000-0000-0000-000000000042",
                automatic_eligibility=True,
                evidence={
                    "research_overview_content": "研究方向包括可信人工智能、医学影像分析和脑疾病辅助诊断。",
                    "source_language": "zh",
                    "source_text_hash": "source-hash-1",
                    "source_span": "研究方向包括可信人工智能、医学影像分析和脑疾病辅助诊断。",
                },
            ),
            DatasetClosureBucketRow(
                blocker_type="missing_professor_paper_summary",
                entity_type="professor",
                remediation_lane="professor_paper_summary_generation",
                professor_id="PROF-PAPER-SUMMARY",
                automatic_eligibility=True,
                evidence={
                    "candidate_paper_summary": "该教师论文围绕可信人工智能和医学影像展开，覆盖脑疾病诊断、模型解释和多模态融合。"
                },
            ),
            DatasetClosureBucketRow(
                blocker_type="duplicate_verified_paper_title_year_groups",
                entity_type="paper_group",
                remediation_lane="duplicate_paper_merge",
                professor_id="PROF-DUP",
                duplicate_group_id="PROF-DUP:2024:title",
                automatic_eligibility=True,
                evidence={
                    "canonical_paper_id": "PAPER-CANON",
                    "old_paper_ids": ["PAPER-OLD"],
                    "paper_ids": ["PAPER-CANON", "PAPER-OLD"],
                    "merge_reason": "dataset_quality_closure:doi_match",
                },
            ),
        ],
    )


def _residual_risk_buckets() -> DatasetClosureBuckets:
    return DatasetClosureBuckets(
        bucket_limit=2,
        summary={
            "ready_summary_lt_200": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "profile_summary_repair",
            },
            "duplicate_verified_paper_title_year_groups": {
                "total": 1,
                "sampled": 1,
                "truncated": False,
                "remediation_lane": "duplicate_paper_merge",
            },
        },
        rows=[
            DatasetClosureBucketRow(
                blocker_type="ready_summary_lt_200",
                entity_type="professor",
                remediation_lane="profile_summary_repair",
                professor_id="PROF-RESIDUAL-1",
                current_status="ready",
                automatic_eligibility=True,
                source_url="https://example.edu/prof",
                evidence={"profile_summary_length": 180},
            ),
            DatasetClosureBucketRow(
                blocker_type="duplicate_verified_paper_title_year_groups",
                entity_type="paper_group",
                remediation_lane="duplicate_paper_merge",
                professor_id="PROF-RESIDUAL-2",
                duplicate_group_id="PROF-RESIDUAL-2:2024:title",
                automatic_eligibility=False,
                skip_reason="ambiguous_fuzzy_match",
                evidence={"paper_ids": ["PAPER-1", "PAPER-2"]},
            ),
        ],
    )


def _valid_profile_summary() -> str:
    return (
        "李四现任深圳高校教授，长期从事可信人工智能、医学影像分析和脑疾病辅助诊断研究。"
        "其工作结合机器学习、深度学习和多模态数据融合方法，关注模型可解释性、临床可靠性"
        "以及真实医疗场景中的辅助决策价值。公开资料能够支撑其身份、研究方向和代表性成果，"
        "并显示其持续围绕神经影像、生物标志物发现和计算机辅助诊断系统开展研究。"
        "相关成果适合作为教师画像和论文摘要生成的核心证据基础。该摘要聚焦官方资料能够"
        "证明的任职、方向和产出，不引入未公开企业经历或未经证实的外部关联。"
    )
