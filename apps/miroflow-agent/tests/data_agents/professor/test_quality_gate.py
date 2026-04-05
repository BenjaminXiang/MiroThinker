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


def test_fails_l1_summary_too_short():
    profile = _profile(profile_summary="张三是教授。")
    result = evaluate_quality(profile)
    assert not result.passed_l1
    assert "profile_summary_length_invalid" in result.l1_failures


def test_l2_flags_incomplete_when_no_directions():
    profile = _profile(
        research_directions=[],
        profile_summary=_pad_summary("张三现任南方科技大学教授，在人工智能领域有丰富经验", 250),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "incomplete"


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
        top_papers=[],
        profile_summary=_pad_summary("张三现任南方科技大学教授，研究大语言模型安全对齐", 250),
    )
    result = evaluate_quality(profile)
    assert result.passed_l1
    assert result.quality_status == "ready"


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
                quality_status="incomplete",
                l1_failures=[],
                l2_flags=["incomplete"],
            )
        profiles_and_results.append((p, qr))

    report = build_quality_report(profiles_and_results)
    assert report.total_count == 10
    assert report.released_count == 10
    assert report.ready_count == 3
    assert any("ready_ratio_low" in a for a in report.alerts)


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
    assert report.alerts == []
