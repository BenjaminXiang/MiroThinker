"""Numeric thresholds referenced by verification pipelines.

All numbers are CENTRALIZED here so that threshold changes are a single-file diff,
reviewable and dated. Every constant must state WHY the value was chosen and,
where applicable, the calibration set size used.

Plan reference: docs/plans/2026-04-17-005 §11.1.
Calibration guarantee: before Phase 3 ships, each score-threshold in this file
must be backed by a labelled eval set of ≥200 samples with precision ≥ 0.95.
Initial values below are starting points; they WILL be re-tuned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# =====================================================================
# professor_paper_link score thresholds
# =====================================================================

AUTHOR_NAME_MATCH_VERIFY_THRESHOLD: float = 0.85
"""Jaro–Winkler similarity between `professor.canonical_name` /
`canonical_name_en` and the paper's author-listed name.

Initial value 0.85 comes from ad-hoc inspection of current
paper_collector disambiguation behavior. Re-tune at Phase 3 exit."""

TOPIC_CONSISTENCY_VERIFY_THRESHOLD: float = 0.5
"""Cosine similarity between embedding(paper.title_clean + abstract_clean)
and embedding(aggregate of professor.research_topics).

0.5 is intentionally loose at verify-gate; research topics vary wildly
in free-text. Primary gate is evidence_source_type; topic score is
an additional sanity check."""

INSTITUTION_CONSISTENCY_VERIFY_THRESHOLD: float = 0.9
"""Required for academic_api-only evidence (OpenAlex / Semantic Scholar /
ORCID) to be auto-verified. Institution match via affiliation string
compared against `professor.primary_official_profile.institution` +
known aliases."""


@dataclass(frozen=True)
class LinkPromotionPolicy:
    """Promotion rules for `professor_paper_link.link_status` candidate → verified.

    All conditions must hold simultaneously. Any failure -> stay candidate.
    """

    allowed_evidence_sources: tuple[str, ...]
    min_author_name_score: float
    min_topic_score_or_none_if_official: float
    min_institution_score_for_api_only: float
    require_no_institution_conflict: bool


PROFESSOR_PAPER_LINK_PROMOTION = LinkPromotionPolicy(
    allowed_evidence_sources=(
        "official_publication_page",
        "personal_homepage",
        "cv_pdf",
        "official_external_profile",
        # academic_api_with_affiliation_match is allowed ONLY if institution
        # score also meets INSTITUTION_CONSISTENCY_VERIFY_THRESHOLD
        "academic_api_with_affiliation_match",
    ),
    min_author_name_score=AUTHOR_NAME_MATCH_VERIFY_THRESHOLD,
    min_topic_score_or_none_if_official=TOPIC_CONSISTENCY_VERIFY_THRESHOLD,
    min_institution_score_for_api_only=INSTITUTION_CONSISTENCY_VERIFY_THRESHOLD,
    require_no_institution_conflict=True,
)


# =====================================================================
# company_signal_event confidence floor by source tier
# =====================================================================

EventTier = Literal["official", "trusted", "unknown"]


@dataclass(frozen=True)
class EventConfidenceRule:
    min_confidence: float
    min_corroborating_sources: int


EVENT_CONFIDENCE_FLOOR_BY_TIER: dict[EventTier, EventConfidenceRule] = {
    "official": EventConfidenceRule(min_confidence=0.9, min_corroborating_sources=1),
    "trusted": EventConfidenceRule(min_confidence=0.7, min_corroborating_sources=2),
    "unknown": EventConfidenceRule(min_confidence=0.6, min_corroborating_sources=3),
}
"""Minimum confidence + required corroborating news sources to mark a
company_signal_event as active (non-candidate) by its primary source tier.

tier=official: e.g. 公司官网公告 → 单源即可
tier=trusted:  e.g. 36kr / 21st Century / 财经 → 需 2 源
tier=unknown:  任何未评估域名 → 需 3 源
"""


# =====================================================================
# company merge auto-decision reasons
# =====================================================================

CompanyMergeReason = Literal[
    "UNIFIED_CREDIT_CODE_MATCH",
    "WEBSITE_HOST_MATCH",
    "OFFICIAL_URL_MATCH",
    "NAME_ALIAS_EXPLICIT",
    "HUMAN_EVIDENCE",
    "ROLLBACK",
]

COMPANY_MERGE_AUTO_REASONS: tuple[CompanyMergeReason, ...] = (
    "UNIFIED_CREDIT_CODE_MATCH",
    "WEBSITE_HOST_MATCH",
    "OFFICIAL_URL_MATCH",
)
"""Merge reasons that permit automatic merging without human review.
Any other reason (NAME_ALIAS_EXPLICIT, HUMAN_EVIDENCE) requires a row in
admin_audit_log with `action='merge_entity'` and a human actor_ref.
"""


# =====================================================================
# Helpers for consumers
# =====================================================================


def is_auto_merge_reason(reason: str) -> bool:
    return reason in COMPANY_MERGE_AUTO_REASONS


def event_confidence_ok(
    tier: EventTier, confidence: float, corroborating_sources: int
) -> bool:
    rule = EVENT_CONFIDENCE_FLOOR_BY_TIER[tier]
    return (
        confidence >= rule.min_confidence
        and corroborating_sources >= rule.min_corroborating_sources
    )
