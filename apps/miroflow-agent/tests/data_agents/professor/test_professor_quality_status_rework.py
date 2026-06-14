# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.data_agents.professor.quality_gate import (
    PipelineIssueState,
    ProfessorAdminAction,
    ProfessorAffiliationState,
    ProfessorCanonicalState,
    ProfessorFactState,
    ProfessorQualityEvaluation,
    ProfessorQualityReason,
    SourcePageState,
    evaluate_professor_quality,
    persist_professor_quality_evaluation,
)


def _dt(hour: int) -> datetime:
    return datetime(2026, 5, 14, hour, tzinfo=timezone.utc)


def _state(**overrides: object) -> ProfessorCanonicalState:
    good_summary = (
        "吴亚北现任南方科技大学物理系教授，长期从事二维材料、电子结构与低维量子体系研究。"
        "其工作围绕材料表界面调控、能带结构分析和器件物理机制展开，结合实验表征与理论建模，"
        "为新型功能材料和电子器件设计提供可验证依据。相关成果体现出稳定的研究方向和清晰的学术产出。"
        "他在课程建设、研究生培养和跨学科合作中持续积累资料，公开主页能够支撑其身份、"
        "研究主题和代表性论文之间的关联，因此适合作为教师核心资料的完整样例和质量门槛样本。"
    )
    defaults = {
        "professor_id": "PROF-1",
        "canonical_name": "吴亚北",
        "identity_status": "resolved",
        "profile_summary": good_summary,
        "paper_summary": "代表论文围绕二维材料电子结构、低维量子体系与器件物理展开。",
        "updated_at": _dt(9),
        "source_pages": (
            SourcePageState(
                page_id="PAGE-1",
                url="https://www.sustech.edu.cn/zh/faculties/wuyabei.html",
                is_official_source=True,
            ),
        ),
        "affiliations": (
            ProfessorAffiliationState(
                institution="南方科技大学",
                department="物理系",
                title="教授",
                is_primary=True,
                is_current=True,
                source_page_id="PAGE-1",
                updated_at=_dt(9),
            ),
        ),
        "facts": (
            ProfessorFactState(
                fact_type="research_topic",
                value_raw="二维材料",
                source_page_id="PAGE-1",
                updated_at=_dt(9),
            ),
        ),
        "has_paper_candidates": True,
        "has_verified_paper_signal": True,
    }
    defaults.update(overrides)
    return ProfessorCanonicalState(**defaults)


def test_complete_official_professor_is_ready() -> None:
    evaluation = evaluate_professor_quality(_state())

    assert evaluation.quality_status == "ready"
    assert evaluation.reasons == ()


def test_archived_professor_can_remain_ready_when_source_grounded() -> None:
    evaluation = evaluate_professor_quality(_state(lifecycle_state="archived"))

    assert evaluation.quality_status == "ready"
    assert evaluation.reasons == ()


def test_merged_professor_can_remain_ready_when_source_grounded() -> None:
    evaluation = evaluate_professor_quality(
        _state(
            lifecycle_state="merged_to_other_school",
            lifecycle_merged_into_id="PROF-2",
        )
    )

    assert evaluation.quality_status == "ready"
    assert evaluation.reasons == ()


def test_trustworthy_incomplete_professor_needs_enrichment_not_review() -> None:
    evaluation = evaluate_professor_quality(_state(facts=()))

    assert evaluation.quality_status == "needs_enrichment"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "missing_research_topic"
    ]


def test_short_profile_summary_blocks_ready_status() -> None:
    evaluation = evaluate_professor_quality(
        _state(profile_summary="吴亚北长期从事二维材料与电子结构研究。")
    )

    assert evaluation.quality_status == "needs_enrichment"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "profile_summary_too_short"
    ]


def test_overlong_profile_summary_blocks_ready_status() -> None:
    evaluation = evaluate_professor_quality(
        _state(profile_summary="吴亚北现任南方科技大学教授，研究二维材料。" * 20)
    )

    assert evaluation.quality_status == "needs_enrichment"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "profile_summary_too_long"
    ]


def test_repetitive_term_list_summary_blocks_ready_status() -> None:
    repetitive = (
        "吴亚北现任南方科技大学物理系教授，研究方向包括二维材料、电子结构、二维材料、"
        "电子结构、二维材料、电子结构、低维材料、低维材料、低维材料、器件物理、器件物理。"
        "二维材料电子结构低维材料器件物理二维材料电子结构低维材料器件物理。二维材料、"
        "电子结构、低维材料、器件物理、二维材料、电子结构、低维材料、器件物理、二维材料、"
        "电子结构、低维材料、器件物理。二维材料、电子结构、低维材料、器件物理、二维材料、"
        "电子结构、低维材料、器件物理。"
    )

    evaluation = evaluate_professor_quality(_state(profile_summary=repetitive))

    assert evaluation.quality_status == "needs_review"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "shallow_or_repetitive_profile_summary"
    ]


def test_missing_research_overview_zh_blocks_ready_when_source_exists() -> None:
    evaluation = evaluate_professor_quality(
        _state(
            has_research_overview_source=True,
            has_research_overview_zh=False,
        )
    )

    assert evaluation.quality_status == "needs_enrichment"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "missing_research_overview_zh"
    ]


def test_missing_paper_summary_blocks_ready_for_verified_papers() -> None:
    evaluation = evaluate_professor_quality(_state(paper_summary=None))

    assert evaluation.quality_status == "needs_enrichment"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "missing_professor_paper_summary"
    ]


def test_duplicate_verified_papers_block_ready_status() -> None:
    evaluation = evaluate_professor_quality(_state(has_duplicate_verified_papers=True))

    assert evaluation.quality_status == "needs_review"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "duplicate_verified_paper_links"
    ]


def test_ding_wenbo_complete_core_profile_ready_without_company_role() -> None:
    ding_summary = (
        "丁文伯现任清华大学深圳国际研究生院助理教授，研究方向包括联邦学习、边缘智能、"
        "分布式机器学习与高效模型训练。他的工作关注通信受限环境下的个性化学习和参数聚合，"
        "结合算法设计、系统优化与真实场景验证，支撑智能终端和协同计算应用。公开资料显示其"
        "具备完整教育与科研履历，代表性论文围绕个性化联邦学习与生成式参数聚合展开。"
        "教师核心质量只要求官网可证的身份、研究和论文链路，不要求企业任职或创业经历作为必要字段之一。"
    )
    evaluation = evaluate_professor_quality(
        _state(
            professor_id="PROF-DING",
            canonical_name="丁文伯",
            profile_summary=ding_summary,
            paper_summary="代表论文围绕个性化联邦学习、参数聚合和边缘智能系统优化展开。",
            facts=(
                ProfessorFactState(
                    fact_type="research_topic",
                    value_raw="联邦学习",
                    source_page_id="PAGE-1",
                    updated_at=_dt(9),
                ),
                ProfessorFactState(
                    fact_type="education",
                    value_raw="博士",
                    source_page_id="PAGE-1",
                    updated_at=_dt(9),
                ),
                ProfessorFactState(
                    fact_type="work_experience",
                    value_raw="清华大学深圳国际研究生院助理教授",
                    source_page_id="PAGE-1",
                    updated_at=_dt(9),
                ),
                ProfessorFactState(
                    fact_type="honor",
                    value_raw="青年学者",
                    source_page_id="PAGE-1",
                    updated_at=_dt(9),
                ),
            ),
            has_research_overview_source=True,
            has_research_overview_zh=True,
        )
    )

    assert evaluation.quality_status == "ready"
    assert evaluation.reasons == ()


def test_missing_official_source_is_low_confidence() -> None:
    evaluation = evaluate_professor_quality(_state(source_pages=()))

    assert evaluation.quality_status == "low_confidence"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "missing_official_source"
    ]


def test_external_issue_blocks_review_but_gate_issue_does_not_self_feedback() -> None:
    gate_issue = PipelineIssueState(
        issue_id="ISSUE-GATE",
        stage="coverage",
        reported_by="professor_quality_gate",
        description="missing profile summary",
        reported_at=_dt(10),
    )
    external_issue = PipelineIssueState(
        issue_id="ISSUE-EXT",
        stage="identity_gate",
        reported_by="professor_seed_runner",
        description="identity conflict",
        reported_at=_dt(10),
    )

    gate_only = evaluate_professor_quality(_state(open_issues=(gate_issue,)))
    blocked = evaluate_professor_quality(_state(open_issues=(gate_issue, external_issue)))

    assert gate_only.quality_status == "ready"
    assert blocked.quality_status == "needs_review"
    assert [reason.rule_id for reason in blocked.reasons] == [
        "external_blocking_issue"
    ]
    assert blocked.reasons[0].persist is False


def test_multiple_current_primary_institutions_are_field_contradiction() -> None:
    state = _state(
        affiliations=(
            ProfessorAffiliationState(
                institution="南方科技大学",
                department="物理系",
                title="教授",
                is_primary=True,
                is_current=True,
                source_page_id="PAGE-1",
                updated_at=_dt(9),
            ),
            ProfessorAffiliationState(
                institution="深圳大学",
                department="物理系",
                title="教授",
                is_primary=True,
                is_current=True,
                source_page_id="PAGE-2",
                updated_at=_dt(9),
            ),
        )
    )

    evaluation = evaluate_professor_quality(state)

    assert evaluation.quality_status == "needs_review"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "field_contradiction"
    ]


def test_missing_title_and_department_are_enrichment_not_contradiction() -> None:
    state = _state(
        affiliations=(
            ProfessorAffiliationState(
                institution="南方科技大学",
                department=None,
                title=None,
                is_primary=True,
                is_current=True,
                source_page_id="PAGE-1",
                updated_at=_dt(9),
            ),
        )
    )

    evaluation = evaluate_professor_quality(state)

    assert evaluation.quality_status == "needs_enrichment"
    assert [reason.rule_id for reason in evaluation.reasons] == [
        "missing_title_or_department"
    ]


def test_verified_paper_signal_is_required_only_when_candidates_exist() -> None:
    no_collection = evaluate_professor_quality(
        _state(has_paper_candidates=False, has_verified_paper_signal=False)
    )
    unresolved_candidates = evaluate_professor_quality(
        _state(has_paper_candidates=True, has_verified_paper_signal=False)
    )

    assert no_collection.quality_status == "ready"
    assert unresolved_candidates.quality_status == "needs_enrichment"
    assert [reason.rule_id for reason in unresolved_candidates.reasons] == [
        "missing_verified_paper_signal"
    ]


def test_human_override_is_honored_until_canonical_watermark_advances() -> None:
    action_time = _dt(11)
    fresh_action = ProfessorAdminAction(
        action="send_to_review",
        observed_data_updated_at=action_time,
    )
    stale_action = ProfessorAdminAction(
        action="confirm_ready",
        observed_data_updated_at=action_time - timedelta(hours=3),
    )

    fresh = evaluate_professor_quality(_state(latest_admin_action=fresh_action))
    stale = evaluate_professor_quality(_state(facts=(), latest_admin_action=stale_action))

    assert fresh.quality_status == "needs_review"
    assert [reason.rule_id for reason in fresh.reasons] == ["human_override"]
    assert fresh.reasons[0].persist is False
    assert stale.quality_status == "needs_enrichment"


class _Cursor:
    def __init__(self, rows: list[object] | None = None) -> None:
        self._rows = rows or []

    def fetchone(self) -> object | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[object]:
        return list(self._rows)


class _FakeQualityConn:
    def __init__(self) -> None:
        self.open_gate_issues = {
            "professor quality gate: stale_reason": "ISSUE-STALE"
        }
        self.inserted_descriptions: list[str] = []
        self.resolved_issue_ids: list[str] = []
        self.updated_statuses: list[tuple[str, str]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> _Cursor:
        compact = " ".join(sql.split())
        if compact.startswith("UPDATE professor"):
            self.updated_statuses.append((str(params[1]), str(params[0])))
            return _Cursor()
        if "SELECT issue_id FROM pipeline_issue" in compact:
            description = str(params[1])
            issue_id = self.open_gate_issues.get(description)
            return _Cursor([(issue_id,)] if issue_id else [])
        if compact.startswith("INSERT INTO pipeline_issue"):
            description = str(params[3])
            self.open_gate_issues[description] = f"ISSUE-{len(self.open_gate_issues)}"
            self.inserted_descriptions.append(description)
            return _Cursor()
        if "SELECT issue_id, description FROM pipeline_issue" in compact:
            return _Cursor(
                [
                    {"issue_id": issue_id, "description": description}
                    for description, issue_id in self.open_gate_issues.items()
                ]
            )
        if compact.startswith("UPDATE pipeline_issue") and "evidence_snapshot" in compact:
            return _Cursor()
        if compact.startswith("UPDATE pipeline_issue"):
            issue_id = str(params[0])
            self.resolved_issue_ids.append(issue_id)
            for description, existing_issue_id in list(self.open_gate_issues.items()):
                if existing_issue_id == issue_id:
                    del self.open_gate_issues[description]
            return _Cursor()
        msg = f"unexpected SQL: {compact}"
        raise AssertionError(msg)


def test_persist_quality_evaluation_is_idempotent_and_resolves_stale_gate_rows() -> None:
    conn = _FakeQualityConn()
    evaluation = ProfessorQualityEvaluation(
        professor_id="PROF-1",
        quality_status="needs_enrichment",
        reasons=(
            ProfessorQualityReason(
                rule_id="missing_profile_summary",
                stage="coverage",
                description="professor quality gate: missing_profile_summary",
            ),
        ),
    )

    persist_professor_quality_evaluation(conn, evaluation)
    persist_professor_quality_evaluation(conn, evaluation)

    assert conn.updated_statuses == [
        ("PROF-1", "needs_enrichment"),
        ("PROF-1", "needs_enrichment"),
    ]
    assert conn.inserted_descriptions == [
        "professor quality gate: missing_profile_summary"
    ]
    assert conn.resolved_issue_ids == ["ISSUE-STALE"]


def test_persist_quality_evaluation_does_not_duplicate_external_blocking_issue() -> None:
    conn = _FakeQualityConn()
    evaluation = ProfessorQualityEvaluation(
        professor_id="PROF-1",
        quality_status="needs_review",
        reasons=(
            ProfessorQualityReason(
                rule_id="external_blocking_issue",
                description="external issue already exists",
                persist=False,
            ),
        ),
    )

    persist_professor_quality_evaluation(conn, evaluation)

    assert conn.inserted_descriptions == []
