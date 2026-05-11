"""Quality-status promotion state machine for the patent canonical.

Pure functions, no DB writes. Mirror of ``paper.quality_promotion`` but
markedly simpler: design.md §8 forbids external patent enrichment
("Patent has no external enrichment; only xlsx-merge can enrich"), so
a prof-page-discovered patent transitions out of ``needs_enrichment``
only when:

- An xlsx import brings authoritative fields (``patent_type``,
  ``applicants``, ``filing_date``, ``abstract``, etc.), OR
- An admin manually upgrades the row.

The forward-monotonic invariant from ``paper.quality_promotion``
applies here too: once ``ready``, only an admin override can degrade
the row.
"""

from __future__ import annotations

from dataclasses import dataclass

# Reuse the same constants as the paper promotion module so callers can
# inter-operate (a join across canonical tables won't have to translate
# vocabularies).
from ..paper.quality_promotion import (
    LOW_CONFIDENCE,
    NEEDS_ENRICHMENT,
    NEEDS_REVIEW,
    PARTIAL,
    READY,
    REJECTED,
    VALID_QUALITY_STATUSES,
    PromotionDecision,
)

__all__ = [
    "VALID_QUALITY_STATUSES",
    "PromotionDecision",
    "PatentEnrichmentSignals",
    "evaluate_patent_promotion",
    "apply_admin_override",
    "NEEDS_REVIEW",
    "READY",
    "LOW_CONFIDENCE",
    "NEEDS_ENRICHMENT",
    "PARTIAL",
    "REJECTED",
]


@dataclass(frozen=True, slots=True)
class PatentEnrichmentSignals:
    """Boolean view of a patent canonical row used by the promotion check.

    "Required" fields for ``ready`` (matches V004 NOT NULL set plus
    fields a researcher / end user expects to see): patent_number,
    title, patent_type, at least one of filing_date/grant_date, and at
    least one applicant or inventor.

    ``xlsx_merged`` flips True when a future xlsx import has overlaid
    authoritative data for this row (e.g. ``patent.exact_backfill``).
    Page-only rows have ``xlsx_merged=False`` until then.
    """

    has_patent_number: bool
    has_title: bool
    has_patent_type: bool
    has_filing_or_grant_date: bool
    has_applicants_or_inventors: bool
    xlsx_merged: bool = False


def evaluate_patent_promotion(
    *,
    current_status: str,
    signals: PatentEnrichmentSignals,
) -> PromotionDecision:
    """Compute the next quality_status for a patent canonical row.

    Pure: no DB access. Caller decides whether to write the result back.

    Promotion rules (design.md §8 + spec table):

    - ``rejected`` → terminal.
    - ``ready`` → terminal except via ``apply_admin_override``.
    - ``needs_review`` → parked until admin acts.
    - Otherwise: if xlsx_merged AND all required fields present →
      ``ready``. If xlsx_merged with gaps → ``partial``. If
      page-only (not xlsx_merged) → ``needs_enrichment``.
    """
    if current_status not in VALID_QUALITY_STATUSES:
        raise ValueError(
            f"current_status must be one of {sorted(VALID_QUALITY_STATUSES)}, "
            f"got {current_status!r}"
        )

    if current_status == REJECTED:
        return PromotionDecision(REJECTED, reason="terminal_rejected")

    # Forward-monotonic: ready never auto-degrades.
    if current_status == READY:
        return PromotionDecision(READY, reason="forward_monotonic")

    if current_status == NEEDS_REVIEW:
        return PromotionDecision(NEEDS_REVIEW, reason="awaiting_admin")

    required_present = all(
        [
            signals.has_patent_number,
            signals.has_title,
            signals.has_patent_type,
            signals.has_filing_or_grant_date,
            signals.has_applicants_or_inventors,
        ]
    )

    if signals.xlsx_merged and required_present:
        return PromotionDecision(READY, reason="xlsx_merged_all_required")

    if signals.xlsx_merged:
        return PromotionDecision(PARTIAL, reason="xlsx_merged_with_gaps")

    return PromotionDecision(NEEDS_ENRICHMENT, reason="awaiting_xlsx_or_admin")


def apply_admin_override(
    *,
    current_status: str,
    override_action: str,
) -> PromotionDecision:
    """Admin-initiated status transition for a patent canonical row.

    Mirrors ``paper.quality_promotion.apply_admin_override`` and shares
    the same supported actions: ``flag_for_review``, ``approve``,
    ``reject``. The patent side accepts ``approve`` directly from
    ``needs_enrichment`` since there is no external enrichment path —
    if an admin reviews a page-only row and judges it complete, they
    can promote it to ``ready`` without waiting for an xlsx import.
    """
    if current_status not in VALID_QUALITY_STATUSES:
        raise ValueError(
            f"current_status must be one of {sorted(VALID_QUALITY_STATUSES)}, "
            f"got {current_status!r}"
        )

    if override_action == "flag_for_review":
        if current_status == REJECTED:
            return PromotionDecision(REJECTED, reason="terminal_rejected")
        return PromotionDecision(NEEDS_REVIEW, reason="admin_flag_for_review")

    if override_action == "approve":
        if current_status == REJECTED:
            return PromotionDecision(REJECTED, reason="terminal_rejected")
        return PromotionDecision(READY, reason="admin_approve")

    if override_action == "reject":
        return PromotionDecision(REJECTED, reason="admin_reject")

    raise ValueError(
        "override_action must be one of "
        "{'flag_for_review', 'approve', 'reject'}, "
        f"got {override_action!r}"
    )
