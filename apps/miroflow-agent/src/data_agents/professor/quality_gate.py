# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Quality gate for professor records — three-level validation.

L1: Hard blocks (release prevented)
L2: Quality markers (released with status flag)
L3: Statistical alerts (aggregate-level warnings)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.data_agents.contracts import SHENZHEN_INSTITUTION_KEYWORDS

from .models import EnrichedProfessorProfile

BOILERPLATE_KEYWORDS = frozenset({
    "暂未获取",
    "持续补全",
    "仍在完善",
    "已整理",
    "可追溯来源",
    "已同步整理",
    "持续补充",
    "仍在持续",
})


@dataclass(frozen=True)
class QualityResult:
    passed_l1: bool
    quality_status: str  # "ready" | "incomplete" | "shallow_summary" | "needs_enrichment"
    l1_failures: list[str]
    l2_flags: list[str]


@dataclass(frozen=True)
class QualityReport:
    total_count: int
    released_count: int
    blocked_count: int
    ready_count: int
    incomplete_count: int
    shallow_summary_count: int
    needs_enrichment_count: int
    alerts: list[str]


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

    summary = profile.profile_summary
    if not summary or len(summary) < 200 or len(summary) > 300:
        l1_failures.append("profile_summary_length_invalid")
    elif any(kw in summary for kw in BOILERPLATE_KEYWORDS):
        l1_failures.append("profile_summary_boilerplate")

    passed_l1 = len(l1_failures) == 0

    # L2 — quality markers
    if not profile.research_directions:
        l2_flags.append("incomplete")

    if (
        summary
        and len(summary) >= 200
        and not _has_specific_research_terms(summary, profile.research_directions)
    ):
        l2_flags.append("shallow_summary")

    if profile.enrichment_source == "regex_only" and not profile.top_papers:
        l2_flags.append("needs_enrichment")

    if l2_flags:
        # Priority: needs_enrichment > incomplete > shallow_summary
        if "needs_enrichment" in l2_flags:
            quality_status = "needs_enrichment"
        elif "incomplete" in l2_flags:
            quality_status = "incomplete"
        else:
            quality_status = "shallow_summary"
    else:
        quality_status = "ready"

    return QualityResult(
        passed_l1=passed_l1,
        quality_status=quality_status,
        l1_failures=l1_failures,
        l2_flags=l2_flags,
    )


def build_quality_report(
    results: list[tuple[EnrichedProfessorProfile, QualityResult]],
) -> QualityReport:
    total = len(results)
    released = sum(1 for _, qr in results if qr.passed_l1)
    blocked = total - released

    ready = sum(1 for _, qr in results if qr.passed_l1 and qr.quality_status == "ready")
    incomplete = sum(1 for _, qr in results if qr.passed_l1 and qr.quality_status == "incomplete")
    shallow = sum(1 for _, qr in results if qr.passed_l1 and qr.quality_status == "shallow_summary")
    needs_enrichment = sum(
        1 for _, qr in results if qr.passed_l1 and qr.quality_status == "needs_enrichment"
    )

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
        incomplete_count=incomplete,
        shallow_summary_count=shallow,
        needs_enrichment_count=needs_enrichment,
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
    return any(d in summary for d in directions)
