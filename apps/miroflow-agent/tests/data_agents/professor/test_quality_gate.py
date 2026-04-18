# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from src.data_agents.professor.models import EnrichedProfessorProfile
from src.data_agents.professor.quality_gate import (
    build_quality_report,
    evaluate_quality,
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
        "evaluation_summary": "h-index 45，总引用12000次，发表论文150篇。国家杰青获得者。",
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


def test_passes_l1_with_all_fields():
    profile = _profile(profile_summary=_pad_summary(
        "张三现任南方科技大学教授，研究方向聚焦大语言模型安全对齐与RLHF训练策略", 250
    ))
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.l1_failures == []


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
    boilerplate = _pad_summary("张三南方科技大学教授。已整理5条可追溯来源，持续补全中", 250)
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


def test_fails_l1_reader_artifact_in_title_or_name():
    profile = _profile(
        name_en="Published Time",
        title=(
            "李海洲 | 人工智能学院 URL Source: https://sai.cuhk.edu.cn/teacher/102 "
            "Published Time: Thu, 02 Apr 2026 08:09:45 GMT Markdown Content: ..."
        ),
        profile_summary=_pad_summary("张三现任南方科技大学教授，研究大语言模型安全对齐", 250),
    )
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "reader_artifact_detected" in result.l1_failures


def test_fails_l1_faculty_section_heading_name():
    profile = _profile(
        name="教师队伍",
        profile_summary=_pad_summary("张三现任中山大学（深圳）材料学院教授，研究半导体封装关键材料", 250),
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
        profile_summary=_pad_summary("张三现任中山大学（深圳）材料学院教授，研究半导体封装关键材料", 250),
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
        profile_summary=_pad_summary("张三现任南方科技大学教授，研究大语言模型安全对齐", 250),
    )
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "name_not_person" in result.l1_failures
    assert result.quality_status == "low_confidence"


def test_short_summary_passes_l1_with_l2_flag():
    profile = _profile(profile_summary="张三是教授。")
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert "summary_length_suboptimal" in result.l2_flags
    assert result.quality_status == "needs_enrichment"


def test_fails_l1_missing_summary():
    profile = _profile(profile_summary="")
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "summary_missing" in result.l1_failures
    assert result.quality_status == "low_confidence"


def test_l2_flags_incomplete_when_no_directions():
    profile = _profile(
        research_directions=[],
        profile_summary=_pad_summary("张三现任南方科技大学教授，在人工智能领域有丰富经验", 250),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "needs_enrichment"


def test_l2_flags_needs_enrichment():
    profile = _profile(
        enrichment_source="regex_only",
        top_papers=[],
        profile_summary=_pad_summary("张三现任南方科技大学教授，研究大语言模型安全对齐", 250),
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
        profile_summary=_pad_summary("张三现任南方科技大学教授，研究大语言模型安全对齐", 250),
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
        profile_summary=_pad_summary("张三现任南方科技大学教授，研究大语言模型安全对齐", 250),
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
            profile_summary=_pad_summary(f"教授{i}南方科技大学大语言模型安全对齐研究", 250),
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
        profile_summary=_pad_summary("张三现任南方科技大学教授，研究大语言模型安全对齐", 250),
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
