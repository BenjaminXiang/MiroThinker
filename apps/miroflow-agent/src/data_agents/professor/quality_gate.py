# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Quality gate for professor records — three-level validation.

L1: Hard blocks (release prevented)
L2: Quality markers (released with status flag)
L3: Statistical alerts (aggregate-level warnings)
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from src.data_agents.contracts import (
    SHENZHEN_INSTITUTION_KEYWORDS,
    QualityStatus,
    normalize_quality_status,
)

from .models import EnrichedProfessorProfile
from .name_selection import is_obvious_non_person_name, looks_like_profile_blob

BOILERPLATE_KEYWORDS = frozenset({
    "暂未获取",
    "持续补全",
    "仍在完善",
    "已整理",
    "可追溯来源",
    "已同步整理",
    "持续补充",
    "仍在持续",
    "由于您提供的教授信息极度匮乏",
    "无法构建符合您要求",
    "若需生成符合学术规范",
    "请补充以下关键维度信息",
})
READER_ARTIFACT_MARKERS = ("URL Source:", "Published Time:", "Markdown Content:")
HSS_DEPARTMENT_KEYWORDS = frozenset({
    "法学院",
    "法学",
    "教育学",
    "教育学部",
    "文学",
    "文学院",
    "外语",
    "外国语",
    "历史",
    "哲学",
    "新闻",
    "传播",
    "社会学",
    "人文",
    "马克思主义",
    "艺术",
    "创意设计",
    "设计学院",
})
HSS_PROJECT_KEYWORDS = frozenset({
    "国家社科",
    "社科基金",
    "哲学社会科学",
    "教育部人文",
    "教育部社科",
    "人文社科",
    "教改",
})
HSS_AWARD_KEYWORDS = frozenset({
    "教学成果",
    "哲学社会科学",
    "社科",
    "人文社科",
    "优秀成果",
})


@dataclass(frozen=True)
class QualityResult:
    passed_l1: bool
    quality_status: QualityStatus
    l1_failures: list[str]
    l2_flags: list[str]
    quality_detail: str | None = None


@dataclass(frozen=True)
class QualityReport:
    total_count: int
    released_count: int
    blocked_count: int
    ready_count: int
    needs_review_count: int
    low_confidence_count: int
    needs_enrichment_count: int
    legacy_breakdown: dict[str, int]
    alerts: list[str]

    @property
    def incomplete_count(self) -> int:
        return self.legacy_breakdown.get("incomplete", 0)

    @property
    def shallow_summary_count(self) -> int:
        return self.legacy_breakdown.get("shallow_summary", 0)


def evaluate_quality(
    profile: EnrichedProfessorProfile,
    *,
    shenzhen_keywords: tuple[str, ...] = SHENZHEN_INSTITUTION_KEYWORDS,
) -> QualityResult:
    l1_failures: list[str] = []
    l2_flags: list[str] = []

    # L1 — hard blocks
    if not profile.name or not profile.name.strip():
        l1_failures.append("name_empty")
    elif is_obvious_non_person_name(profile.name) or looks_like_profile_blob(profile.name):
        l1_failures.append("name_not_person")

    if not profile.institution or not profile.institution.strip():
        l1_failures.append("institution_empty")
    elif not any(kw in profile.institution for kw in shenzhen_keywords):
        l1_failures.append("institution_not_shenzhen")

    if not any(
        url
        for url in profile.evidence_urls
        if _is_likely_official(url, shenzhen_keywords)
    ):
        l1_failures.append("missing_official_evidence")

    if _has_reader_artifact(profile):
        l1_failures.append("reader_artifact_detected")

    summary = profile.profile_summary
    if not summary:
        l1_failures.append("summary_missing")
    elif any(kw in summary for kw in BOILERPLATE_KEYWORDS):
        l1_failures.append("profile_summary_boilerplate")

    passed_l1 = len(l1_failures) == 0

    # L2 — quality markers
    if summary and (len(summary) < 200 or len(summary) > 300):
        l2_flags.append("summary_length_suboptimal")

    if not profile.research_directions:
        l2_flags.append("incomplete")

    if (
        summary
        and len(summary) >= 200
        and not _has_specific_research_terms(summary, profile.research_directions)
    ):
        l2_flags.append("shallow_summary")

    if not has_scholarly_output_signal(profile):
        l2_flags.append("needs_enrichment")

    quality_status: QualityStatus = "ready"
    quality_detail: str | None = None
    if not passed_l1:
        quality_status = "low_confidence"
        quality_detail = "low_confidence"
        if "name_not_person" in l1_failures:
            quality_detail = "low_confidence"
    elif l2_flags:
        # Canonical priority: needs_enrichment > needs_review(shallow/incomplete).
        if "needs_enrichment" in l2_flags:
            quality_status = "needs_enrichment"
            quality_detail = "needs_enrichment"
        elif "incomplete" in l2_flags:
            quality_status = "needs_review"
            quality_detail = "incomplete"
        else:
            quality_status = "needs_review"
            quality_detail = "shallow_summary"

    return QualityResult(
        passed_l1=passed_l1,
        quality_status=quality_status,
        l1_failures=l1_failures,
        l2_flags=l2_flags,
        quality_detail=quality_detail,
    )


def build_quality_report(
    results: list[tuple[EnrichedProfessorProfile, QualityResult]],
) -> QualityReport:
    total = len(results)
    released = sum(1 for _, qr in results if qr.passed_l1)
    blocked = total - released

    ready = 0
    needs_review = 0
    low_confidence = 0
    needs_enrichment = 0
    legacy_breakdown = {
        "ready": 0,
        "incomplete": 0,
        "shallow_summary": 0,
        "needs_enrichment": 0,
        "needs_review": 0,
        "low_confidence": 0,
    }
    for _, qr in results:
        if not qr.passed_l1:
            canonical_status = normalize_quality_status(qr.quality_status)
            if canonical_status == "low_confidence":
                low_confidence += 1
                legacy_breakdown["low_confidence"] += 1
            continue
        canonical_status = normalize_quality_status(qr.quality_status)
        if canonical_status == "ready":
            ready += 1
        elif canonical_status == "needs_review":
            needs_review += 1
        elif canonical_status == "low_confidence":
            low_confidence += 1
        elif canonical_status == "needs_enrichment":
            needs_enrichment += 1

        legacy_key = qr.quality_detail or str(qr.quality_status)
        if legacy_key in legacy_breakdown:
            legacy_breakdown[legacy_key] += 1

    alerts: list[str] = []
    if released > 0 and ready / released < 0.7:
        alerts.append(
            f"ready_ratio_low: {ready}/{released} = {ready / released:.1%} < 70%"
        )

    # Per-institution coverage alert
    institution_counts: dict[str, int] = {}
    for profile, qr in results:
        inst = profile.institution
        if inst:
            institution_counts[inst] = institution_counts.get(inst, 0) + 1
    for inst, count in institution_counts.items():
        released_for_inst = sum(
            1 for p, qr in results if p.institution == inst and qr.passed_l1
        )
        if count > 0 and released_for_inst / count < 0.8:
            alerts.append(
                f"low_release_rate:{inst}: {released_for_inst}/{count} = "
                f"{released_for_inst / count:.1%}"
            )

    return QualityReport(
        total_count=total,
        released_count=released,
        blocked_count=blocked,
        ready_count=ready,
        needs_review_count=needs_review,
        low_confidence_count=low_confidence,
        needs_enrichment_count=needs_enrichment,
        legacy_breakdown=legacy_breakdown,
        alerts=alerts,
    )


def _is_likely_official(url: str, institution_keywords: tuple[str, ...]) -> bool:
    """Heuristic: URL contains .edu.cn or institution-related domain."""
    url_lower = url.lower()
    if ".edu.cn" in url_lower:
        return True
    if ".ac.cn" in url_lower:
        return True
    return False


def _has_specific_research_terms(
    summary: str,
    directions: list[str],
) -> bool:
    """Check if summary contains at least one specific research term."""
    if not directions:
        return False
    normalized_summary = _normalize_term_text(summary)
    if not normalized_summary:
        return False
    for direction in directions:
        normalized_direction = _normalize_term_text(direction)
        if not normalized_direction:
            continue
        if normalized_direction in normalized_summary:
            return True
        for token in _extract_research_term_tokens(normalized_direction):
            if token in normalized_summary:
                return True
    return False


def _normalize_term_text(value: str) -> str:
    return (
        value.strip()
        .replace("（", "(")
        .replace("）", ")")
        .replace("：", ":")
        .replace("，", ",")
        .replace("；", ";")
        .replace("　", " ")
    )


def _extract_research_term_tokens(direction: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[、,，;；/()（）:：]+", direction):
        normalized = chunk.strip()
        if not normalized:
            continue
        parts.append(normalized)
        parts.extend(
            piece.strip()
            for piece in re.split(r"[的与及和]", normalized)
            if piece.strip()
        )

    seen: set[str] = set()
    tokens: list[str] = []
    for part in parts:
        if part in seen:
            continue
        seen.add(part)
        cjk_length = len(re.findall(r"[\u4e00-\u9fff]", part))
        ascii_length = len(re.findall(r"[A-Za-z0-9+\-]", part))
        if cjk_length >= 4 or ascii_length >= 3:
            tokens.append(part)
    return tokens


def _has_paper_signal(profile: EnrichedProfessorProfile) -> bool:
    has_top_papers = len(profile.top_papers) > 0
    has_paper_count = (profile.paper_count or 0) > 0
    return has_top_papers or has_paper_count


def has_scholarly_output_signal(profile: EnrichedProfessorProfile) -> bool:
    if _has_paper_signal(profile):
        return True
    if not _is_hss_profile(profile):
        return False
    return _has_hss_project_signal(profile.projects) or _has_hss_award_signal(profile.awards)


def _is_hss_profile(profile: EnrichedProfessorProfile) -> bool:
    department = (profile.department or "").strip()
    if not department:
        return False
    return any(keyword in department for keyword in HSS_DEPARTMENT_KEYWORDS)


def _has_hss_project_signal(projects: list[str]) -> bool:
    return any(
        keyword in project
        for project in projects
        for keyword in HSS_PROJECT_KEYWORDS
    )


def _has_hss_award_signal(awards: list[str]) -> bool:
    return any(
        keyword in award
        for award in awards
        for keyword in HSS_AWARD_KEYWORDS
    )


def _has_reader_artifact(profile: EnrichedProfessorProfile) -> bool:
    candidate_values = (
        profile.name,
        profile.name_en,
        profile.title,
        profile.profile_summary,
    )
    return any(
        marker in (value or "")
        for value in candidate_values
        for marker in READER_ARTIFACT_MARKERS
    )
