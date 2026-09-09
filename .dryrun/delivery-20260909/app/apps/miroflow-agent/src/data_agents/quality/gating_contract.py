from __future__ import annotations

from typing import get_args, cast

from src.data_agents.contracts import QUALITY_STATUS_CANONICAL_MAP, QualityStatus


_CANONICAL_STATUSES = frozenset(get_args(QualityStatus))
_IDENTITY_EXCLUDED_FROM_INDEX = {"rejected", "merged"}
_PROMOTION_RANK: dict[QualityStatus, int] = {
    "low_confidence": 0,
    "needs_review": 1,
    "needs_enrichment": 2,
    "partial": 3,
    "ready": 4,
}


def normalize_quality_status(raw_status: object | None) -> QualityStatus:
    """Normalize legacy/current quality_status values to the six-value enum."""
    if raw_status is None:
        return "needs_review"
    status = str(raw_status).strip()
    if status in _CANONICAL_STATUSES:
        return cast(QualityStatus, status)
    return QUALITY_STATUS_CANONICAL_MAP.get(status, "needs_review")


def promote_monotonic(
    current: object | None,
    proposed: object | None,
    *,
    admin_action: object | None = None,
) -> QualityStatus:
    """Return a forward-monotonic status transition.

    Automated gates can promote upward or hold. A ready row is never
    downgraded unless the caller passes an explicit admin action.
    """
    current_status = normalize_quality_status(current)
    proposed_status = normalize_quality_status(proposed)

    if admin_action is not None:
        return proposed_status

    if current_status == "rejected":
        return "rejected"
    if current_status == "ready" and proposed_status != "ready":
        return "ready"
    if proposed_status == "rejected":
        return current_status

    current_rank = _PROMOTION_RANK[current_status]
    proposed_rank = _PROMOTION_RANK[proposed_status]
    if proposed_rank > current_rank:
        return proposed_status
    return current_status


def is_indexable(
    quality_status: object | None,
    identity_status: object | None = None,
    *,
    paper_has_rich_text: bool | None = None,
) -> bool:
    """Return whether a row is eligible for retrieval indexing."""
    if identity_status is not None:
        normalized_identity = str(identity_status).strip()
        if normalized_identity in _IDENTITY_EXCLUDED_FROM_INDEX:
            return False
    normalized_status = normalize_quality_status(quality_status)
    if normalized_status == "ready":
        return True
    return normalized_status == "partial" and paper_has_rich_text is True
