# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.quality_gate import (
    QUALITY_GATE_REPORTED_BY,
    ProfessorAdminActionState,
    ProfessorAffiliationState,
    ProfessorCanonicalState,
    ProfessorFactState,
    ProfessorIssueState,
    build_quality_report,
    evaluate_quality,
    evaluate_professor_quality,
    persist_professor_quality_evaluation,
    _check_profile_summary_boilerplate,
    _check_profile_summary_length,
)


def _profile(**overrides) -> EnrichedProfessorProfile:
    good_summary = (
        "张三现任南方科技大学计算机科学与工程系教授，研究方向聚焦大语言模型安全对齐与RLHF训练策略。"
        "近年来在NeurIPS、ICML等顶会发表多篇高影响力论文，提出了多种创新的安全对齐方法。"
        "曾获国家杰出青年科学基金资助，在模型安全评估与红队测试领域有深入研究。"
    )
    defaults = {
        "name": "张三",
        "institution": "南方科技大学",
        "department": "计算机系",
        "title": "教授",
        "research_directions": ["大语言模型安全对齐", "RLHF训练策略"],
        "profile_summary": good_summary[:280],
        "enrichment_source": "paper_enriched",
        "evidence_urls": ["https://faculty.sustech.edu.cn/zhangsan"],
        "profile_url": "https://faculty.sustech.edu.cn/zhangsan",
        "roster_source": "https://www.sustech.edu.cn/",
        "extraction_status": "structured",
    }
    defaults.update(overrides)
    return EnrichedProfessorProfile(**defaults)


def _pad_summary(base: str, target_len: int) -> str:
    """Pad or trim a summary to exactly target_len characters."""
    if len(base) >= target_len:
        return base[:target_len]
    return base + "。" * (target_len - len(base))


def _canonical_state(**overrides) -> ProfessorCanonicalState:
    now = datetime(2026, 5, 14, 8, 0, tzinfo=timezone.utc)
    defaults = {
        "professor_id": "prof-001",
        "canonical_name": "张三",
        "identity_status": "resolved",
        "primary_official_profile_page_id": "11111111-1111-1111-1111-111111111111",
        "profile_summary": "张三现任南方科技大学计算机科学与工程系教授，研究方向为大语言模型安全。",
        "updated_at": now,
        "facts": (
            ProfessorFactState(
                fact_type="research_topic",
                value_raw="大语言模型安全",
                source_page_id="11111111-1111-1111-1111-111111111111",
                updated_at=now,
            ),
        ),
        "affiliations": (
            ProfessorAffiliationState(
                institution="南方科技大学",
                department="计算机科学与工程系",
                title="教授",
                is_primary=True,
                is_current=True,
                source_page_id="11111111-1111-1111-1111-111111111111",
                updated_at=now,
            ),
        ),
        "open_issues": (),
        "has_paper_candidates": False,
        "has_verified_paper_link": False,
    }
    defaults.update(overrides)
    return ProfessorCanonicalState(**defaults)


def _reason_ids(evaluation) -> set[str]:
    return {reason.rule_id for reason in evaluation.reasons}


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _QualityPersistenceConn:
    def __init__(self, *, open_gate_issues=None):
        self.open_gate_issues = list(open_gate_issues or [])
        self.inserted_issue_descriptions: list[str] = []
        self.resolved_issue_ids: list[str] = []
        self.quality_status_updates: list[str] = []
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()):
        compact_sql = " ".join(sql.split())
        self.statements.append((compact_sql, params))
        if compact_sql.startswith("SELECT issue_id, description FROM pipeline_issue"):
            return _Rows(list(self.open_gate_issues))
        if compact_sql.startswith("UPDATE professor"):
            self.quality_status_updates.append(str(params[0]))
            return _Rows([])
        if compact_sql.startswith("INSERT INTO pipeline_issue"):
            description = str(params[3])
            if description not in {
                str(row["description"]) for row in self.open_gate_issues
            }:
                self.inserted_issue_descriptions.append(description)
                self.open_gate_issues.append(
                    {
                        "issue_id": f"new-{len(self.inserted_issue_descriptions)}",
                        "description": description,
                    }
                )
            return _Rows([])
        if compact_sql.startswith("UPDATE pipeline_issue"):
            issue_id = str(params[2])
            self.resolved_issue_ids.append(issue_id)
            self.open_gate_issues = [
                row for row in self.open_gate_issues if row["issue_id"] != issue_id
            ]
            return _Rows([])
        raise AssertionError(f"Unexpected SQL: {compact_sql}")


def test_passes_l1_with_all_fields():
    profile = _profile(
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，研究方向聚焦大语言模型安全对齐与RLHF训练策略",
            250,
        )
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.l1_failures == []


def test_professor_quality_ready_with_all_pinned_key_fields():
    result = evaluate_professor_quality(_canonical_state())

    assert result.quality_status == "ready"
    assert result.reasons == ()


def test_professor_quality_missing_summary_needs_enrichment_not_review():
    result = evaluate_professor_quality(_canonical_state(profile_summary=""))

    assert result.quality_status == "needs_enrichment"
    assert "missing_profile_summary" in _reason_ids(result)
    assert "field_contradiction" not in _reason_ids(result)


def test_professor_quality_missing_official_source_is_low_confidence():
    result = evaluate_professor_quality(
        _canonical_state(primary_official_profile_page_id=None)
    )

    assert result.quality_status == "low_confidence"
    assert "missing_official_source" in _reason_ids(result)


def test_professor_quality_external_issue_blocks_without_duplicate_reason():
    result = evaluate_professor_quality(
        _canonical_state(
            open_issues=(
                ProfessorIssueState(
                    stage="identity_gate",
                    reported_by="manual_reviewer",
                    description="same-name conflict requires review",
                    reported_at=datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
                ),
            )
        )
    )

    assert result.quality_status == "needs_review"
    reason = result.reasons[0]
    assert reason.rule_id == "external_blocking_issue"
    assert reason.stage is None
    assert reason.persist is False


def test_professor_quality_ignores_gate_authored_issue_self_feedback():
    result = evaluate_professor_quality(
        _canonical_state(
            open_issues=(
                ProfessorIssueState(
                    stage="identity_gate",
                    reported_by=QUALITY_GATE_REPORTED_BY,
                    description="old quality gate reason",
                    reported_at=datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
                ),
            )
        )
    )

    assert result.quality_status == "ready"
    assert "external_blocking_issue" not in _reason_ids(result)


def test_professor_quality_multiple_primary_institutions_is_field_contradiction():
    now = datetime(2026, 5, 14, 8, 0, tzinfo=timezone.utc)
    result = evaluate_professor_quality(
        _canonical_state(
            affiliations=(
                ProfessorAffiliationState(
                    institution="南方科技大学",
                    department="计算机科学与工程系",
                    title="教授",
                    is_primary=True,
                    is_current=True,
                    source_page_id="11111111-1111-1111-1111-111111111111",
                    updated_at=now,
                ),
                ProfessorAffiliationState(
                    institution="深圳大学",
                    department="计算机与软件学院",
                    title="教授",
                    is_primary=True,
                    is_current=True,
                    source_page_id="22222222-2222-2222-2222-222222222222",
                    updated_at=now,
                ),
            )
        )
    )

    assert result.quality_status == "needs_review"
    assert "field_contradiction" in _reason_ids(result)


def test_professor_quality_missing_title_or_department_is_not_contradiction():
    result = evaluate_professor_quality(
        _canonical_state(
            affiliations=(
                ProfessorAffiliationState(
                    institution="南方科技大学",
                    department=None,
                    title=None,
                    is_primary=True,
                    is_current=True,
                    source_page_id="11111111-1111-1111-1111-111111111111",
                    updated_at=datetime(2026, 5, 14, 8, 0, tzinfo=timezone.utc),
                ),
            )
        )
    )

    assert result.quality_status == "needs_enrichment"
    assert "missing_title_or_department" in _reason_ids(result)
    assert "field_contradiction" not in _reason_ids(result)


def test_professor_quality_verified_paper_signal_only_required_when_candidates_exist():
    no_candidates = evaluate_professor_quality(_canonical_state())
    candidates_without_verified_link = evaluate_professor_quality(
        _canonical_state(has_paper_candidates=True, has_verified_paper_link=False)
    )
    candidates_with_verified_link = evaluate_professor_quality(
        _canonical_state(has_paper_candidates=True, has_verified_paper_link=True)
    )

    assert no_candidates.quality_status == "ready"
    assert candidates_without_verified_link.quality_status == "needs_enrichment"
    assert "missing_verified_paper_signal" in _reason_ids(candidates_without_verified_link)
    assert candidates_with_verified_link.quality_status == "ready"


def test_professor_quality_fresh_human_override_is_display_only():
    state = _canonical_state(profile_summary="")
    override = ProfessorAdminActionState(
        action="confirm_ready",
        observed_data_updated_at=state.updated_at,
        created_at=state.updated_at + timedelta(minutes=1),
    )

    result = evaluate_professor_quality(state, latest_admin_action=override)

    assert result.quality_status == "ready"
    assert result.reasons[0].rule_id == "human_override"
    assert result.reasons[0].persist is False


def test_professor_quality_external_issue_invalidates_human_override():
    base = datetime(2026, 5, 14, 8, 0, tzinfo=timezone.utc)
    state = _canonical_state(
        updated_at=base,
        open_issues=(
            ProfessorIssueState(
                stage="identity_gate",
                reported_by="manual_reviewer",
                description="filed after override",
                reported_at=base + timedelta(hours=1),
            ),
        ),
    )
    override = ProfessorAdminActionState(
        action="confirm_ready",
        observed_data_updated_at=base,
        created_at=base + timedelta(minutes=1),
    )

    result = evaluate_professor_quality(state, latest_admin_action=override)

    assert result.quality_status == "needs_review"
    assert "external_blocking_issue" in _reason_ids(result)
    assert "human_override" not in _reason_ids(result)


def test_persist_professor_quality_reasons_is_idempotent_and_resolves_stale_gate_rows():
    evaluation = evaluate_professor_quality(_canonical_state(profile_summary=""))
    conn = _QualityPersistenceConn(
        open_gate_issues=(
            {
                "issue_id": "old-research-topic",
                "description": (
                    "missing_research_topic: no active research_topic fact is present"
                ),
            },
        )
    )

    first = persist_professor_quality_evaluation(
        conn,
        professor_id="prof-001",
        evaluation=evaluation,
    )
    second = persist_professor_quality_evaluation(
        conn,
        professor_id="prof-001",
        evaluation=evaluation,
    )

    assert first.quality_status == "needs_enrichment"
    assert first.issues_inserted == 1
    assert first.issues_resolved == 1
    assert second.issues_inserted == 0
    assert second.issues_resolved == 0
    assert conn.inserted_issue_descriptions == [
        "missing_profile_summary: profile_summary is missing"
    ]
    assert conn.resolved_issue_ids == ["old-research-topic"]


def test_persist_professor_quality_does_not_duplicate_external_blocking_issue():
    evaluation = evaluate_professor_quality(
        _canonical_state(
            open_issues=(
                ProfessorIssueState(
                    stage="identity_gate",
                    reported_by="manual_reviewer",
                    description="existing external identity issue",
                    reported_at=datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc),
                ),
            )
        )
    )
    conn = _QualityPersistenceConn()

    report = persist_professor_quality_evaluation(
        conn,
        professor_id="prof-001",
        evaluation=evaluation,
    )

    assert report.quality_status == "needs_review"
    assert report.issues_inserted == 0
    assert conn.inserted_issue_descriptions == []
    assert conn.quality_status_updates == ["needs_review"]


def test_fails_l1_empty_name():
    profile = _profile(name="", profile_summary=_pad_summary("X", 250))
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "name_empty" in result.l1_failures


def test_fails_l1_non_shenzhen_institution():
    profile = _profile(
        institution="北京大学",
        profile_summary=_pad_summary("X", 250),
    )
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "institution_not_shenzhen" in result.l1_failures


def test_fails_l1_missing_official_evidence():
    profile = _profile(
        evidence_urls=["https://scholar.google.com/citations?user=xxx"],
        profile_summary=_pad_summary("X", 250),
    )
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "missing_official_evidence" in result.l1_failures


def test_fails_l1_boilerplate_summary():
    boilerplate = _pad_summary(
        "张三南方科技大学教授。已整理5条可追溯来源，持续补全中", 250
    )
    profile = _profile(profile_summary=boilerplate)
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "profile_summary_boilerplate" in result.l1_failures


def test_fails_l1_refusal_style_summary():
    refusal = _pad_summary(
        "由于您提供的教授信息极度匮乏，无法构建符合您要求的专业学术简介。请补充以下关键维度信息。",
        250,
    )
    profile = _profile(profile_summary=refusal)
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "profile_summary_boilerplate" in result.l1_failures


def test_fails_l1_academic_norm_refusal_style_summary():
    refusal = _pad_summary(
        "由于您提供的原始信息中，除姓名和学校外，缺乏研究方向、职称、院系、h-index、"
        "代表论文及教育背景等核心学术维度，无法构建符合学术规范且达到要求的专业简介。"
        "若要生成高质量的学术摘要，请提供包含具体研究领域、学术头衔、核心论文题目及具体科研成果的详细文本。",
        250,
    )
    profile = _profile(profile_summary=refusal)
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "profile_summary_boilerplate" in result.l1_failures


def test_fails_l1_when_profile_has_no_academic_signal():
    profile = _profile(
        department=None,
        title=None,
        research_directions=[],
        top_papers=[],
        paper_count=None,
        h_index=None,
        citation_count=None,
        awards=[],
        academic_positions=[],
        education_structured=[],
        work_experience=[],
        profile_summary=_pad_summary(
            "尤政现任清华大学深圳国际研究生院教师，当前官方主页未提供可核验的研究方向、"
            "职称、论文、项目、履历或荣誉信息，本条记录需继续补充后再进入发布库。",
            250,
        ),
        evidence_urls=["http://www.sigs.tsinghua.edu.cn/yzys/main.htm"],
        profile_url="http://www.sigs.tsinghua.edu.cn/yzys/main.htm",
    )

    result = evaluate_quality(profile)

    assert not result.passed_l1
    assert "insufficient_academic_signal" in result.l1_failures
    assert result.quality_status == "low_confidence"


def test_fails_l1_reader_artifact_in_title_or_name():
    profile = _profile(
        name_en="Published Time",
        title=(
            "李海洲 | 人工智能学院 URL Source: https://sai.cuhk.edu.cn/teacher/102 "
            "Published Time: Thu, 02 Apr 2026 08:09:45 GMT Markdown Content: ..."
        ),
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，研究大语言模型安全对齐", 250
        ),
    )
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "reader_artifact_detected" in result.l1_failures


def test_fails_l1_faculty_section_heading_name():
    profile = _profile(
        name="教师队伍",
        profile_summary=_pad_summary(
            "张三现任中山大学（深圳）材料学院教授，研究半导体封装关键材料", 250
        ),
        institution="中山大学（深圳）",
        department="材料学院",
    )
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "name_not_person" in result.l1_failures
    assert result.quality_status == "low_confidence"


def test_fails_l1_title_only_profile_name():
    profile = _profile(
        name="教授",
        profile_summary=_pad_summary(
            "张三现任中山大学（深圳）材料学院教授，研究半导体封装关键材料", 250
        ),
        institution="中山大学（深圳）",
        department="材料学院",
    )
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "name_not_person" in result.l1_failures
    assert result.quality_status == "low_confidence"


def test_fails_l1_non_person_profile_name():
    profile = _profile(
        name="Teaching",
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，研究大语言模型安全对齐", 250
        ),
    )
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "name_not_person" in result.l1_failures
    assert result.quality_status == "low_confidence"


def test_summary_length_check_rejects_below_150():
    profile = _profile(profile_summary="张三是教授。")
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "profile_summary_too_short" in result.l1_failures
    assert result.quality_status == "low_confidence"


def test_summary_length_check_accepts_above_150():
    profile = _profile(
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，研究大语言模型安全对齐与RLHF训练策略",
            150,
        )
    )
    result = _check_profile_summary_length(profile)
    assert result.passed


def test_summary_boilerplate_check_rejects():
    profile = _profile(
        profile_summary=_pad_summary("张三南方科技大学教授。持续补全中", 180)
    )
    result = _check_profile_summary_boilerplate(profile)
    assert not result.passed
    assert result.code == "profile_summary_boilerplate"


def test_summary_full_check_accepts_clean():
    profile = _profile(
        enrichment_source="paper_enriched",
        top_papers=[
            {
                "title": "Safety Alignment for LLMs",
                "year": 2024,
                "venue": "NeurIPS",
                "citation_count": 120,
                "source": "openalex",
            }
        ],
        paper_count=30,
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，研究大语言模型安全对齐", 250
        ),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "ready"


def test_fails_l1_missing_summary():
    profile = _profile(profile_summary="")
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "summary_missing" in result.l1_failures
    assert result.quality_status == "low_confidence"


def test_l2_flags_incomplete_when_no_directions():
    profile = _profile(
        research_directions=[],
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，在人工智能领域有丰富经验", 250
        ),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "needs_enrichment"


def test_l2_flags_needs_enrichment():
    profile = _profile(
        enrichment_source="regex_only",
        top_papers=[],
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，研究大语言模型安全对齐", 250
        ),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "needs_enrichment"


def test_quality_status_ready_when_all_good():
    profile = _profile(
        enrichment_source="paper_enriched",
        top_papers=[
            {
                "title": "Safety Alignment for LLMs",
                "year": 2024,
                "venue": "NeurIPS",
                "citation_count": 120,
                "source": "openalex",
            }
        ],
        paper_count=30,
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，研究大语言模型安全对齐", 250
        ),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "ready"


def test_quality_status_ready_when_summary_contains_specific_overlap_without_exact_direction_string():
    summary = _pad_summary(
        "谢健教授任职于哈尔滨工业大学（深圳），研究聚焦Na+/K+-ATPase的非离子泵信号转导功能，"
        "重点探讨Src激酶介导的细胞信号通路、Ouabain作用机制，以及心肌保护与代谢重塑相关问题。",
        250,
    )
    profile = _profile(
        institution="哈尔滨工业大学（深圳）",
        department="马克思主义学院（深圳）",
        research_directions=[
            "Na+/K+-ATPase的信号转导机制",
            "Src激酶介导的细胞信号转导",
            "Ouabain（乌本苷）的非离子泵功能研究",
            "心肌细胞线粒体钾通道与心肌保护",
        ],
        paper_count=203,
        top_papers=[
            {
                "title": "Na+/K+-ATPase as a signal transducer",
                "year": 2002,
                "venue": "European Journal of Biochemistry",
                "citation_count": 588,
                "source": "openalex",
            }
        ],
        profile_summary=summary,
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "ready"


def test_quality_status_needs_enrichment_when_paper_fields_missing():
    profile = _profile(
        enrichment_source="paper_enriched",
        top_papers=[],
        h_index=None,
        citation_count=None,
        paper_count=None,
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，研究大语言模型安全对齐", 250
        ),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "needs_enrichment"


def test_quality_status_ready_for_hss_profile_with_project_signal_without_papers():
    profile = _profile(
        department="教育学部",
        research_directions=["课程思政", "高等教育治理"],
        top_papers=[],
        h_index=None,
        citation_count=None,
        paper_count=None,
        projects=["国家社科基金重大项目：高校课程思政评价体系研究"],
        awards=[],
        profile_summary=_pad_summary(
            "靳玉乐现任深圳大学教育学部教授，研究方向包括课程思政与高等教育治理，主持国家社科基金重大项目。",
            250,
        ),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "ready"


def test_quality_status_ready_for_hss_profile_with_academic_award_without_papers():
    profile = _profile(
        department="法学院",
        research_directions=["国际法", "比较法"],
        top_papers=[],
        h_index=None,
        citation_count=None,
        paper_count=None,
        projects=[],
        awards=["国家级教学成果一等奖"],
        profile_summary=_pad_summary(
            "张三现任南方科技大学法学院教授，研究方向包括国际法与比较法，曾获国家级教学成果一等奖。",
            250,
        ),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "ready"


def test_quality_status_still_needs_enrichment_for_stem_profile_without_papers_even_with_awards():
    profile = _profile(
        department="计算机科学与工程系",
        top_papers=[],
        h_index=None,
        citation_count=None,
        paper_count=None,
        projects=["国家重点研发计划课题"],
        awards=["国家科技进步奖二等奖"],
        profile_summary=_pad_summary(
            "张三现任南方科技大学计算机科学与工程系教授，研究大语言模型安全对齐，承担国家重点研发计划课题。",
            250,
        ),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "needs_enrichment"


def test_quality_status_keeps_algorithm_department_strict_even_if_contains_fa_character():
    profile = _profile(
        department="算法科学与工程系",
        top_papers=[],
        h_index=None,
        citation_count=None,
        paper_count=None,
        projects=[],
        awards=["国家级教学成果一等奖"],
        profile_summary=_pad_summary(
            "张三现任南方科技大学算法科学与工程系教授，研究算法系统与机器学习基础，曾获国家级教学成果一等奖。",
            250,
        ),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "needs_enrichment"


def test_build_quality_report_generates_alert_on_low_ready():
    profiles_and_results = []
    # 3 out of 10 are ready → 30% < 70%
    for i in range(10):
        p = _profile(
            name=f"教授{i}",
            profile_summary=_pad_summary(
                f"教授{i}南方科技大学大语言模型安全对齐研究", 250
            ),
        )
        from src.data_agents.professor.quality_gate import QualityResult

        if i < 3:
            qr = QualityResult(
                passed_l1=True, quality_status="ready", l1_failures=[], l2_flags=[]
            )
        else:
            qr = QualityResult(
                passed_l1=True,
                quality_status="needs_review",
                l1_failures=[],
                l2_flags=["incomplete"],
                quality_detail="incomplete",
            )
        profiles_and_results.append((p, qr))

    report = build_quality_report(profiles_and_results)
    assert report.total_count == 10
    assert report.released_count == 10
    assert report.ready_count == 3
    assert report.needs_review_count == 7
    assert report.incomplete_count == 7
    assert any("ready_ratio_low" in a for a in report.alerts)


def test_build_quality_report_counts_low_confidence_blocked_profiles():
    profile = _profile(
        name="Teaching",
        profile_summary=_pad_summary(
            "张三现任南方科技大学教授，研究大语言模型安全对齐", 250
        ),
    )
    from src.data_agents.professor.quality_gate import QualityResult

    report = build_quality_report(
        [
            (
                profile,
                QualityResult(
                    passed_l1=False,
                    quality_status="low_confidence",
                    l1_failures=["name_not_person"],
                    l2_flags=[],
                    quality_detail="low_confidence",
                ),
            )
        ]
    )

    assert report.total_count == 1
    assert report.released_count == 0
    assert report.blocked_count == 1
    assert report.low_confidence_count == 1


def test_build_quality_report_no_alerts_when_all_ready():
    profiles_and_results = []
    for i in range(5):
        p = _profile(name=f"教授{i}")
        from src.data_agents.professor.quality_gate import QualityResult

        qr = QualityResult(
            passed_l1=True, quality_status="ready", l1_failures=[], l2_flags=[]
        )
        profiles_and_results.append((p, qr))

    report = build_quality_report(profiles_and_results)
    assert report.ready_count == 5
    assert report.needs_review_count == 0
    assert report.alerts == []
