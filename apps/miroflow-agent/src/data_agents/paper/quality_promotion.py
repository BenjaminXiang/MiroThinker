"""Quality-status promotion state machine for the paper canonical.

Pure functions, no DB writes. Callers wire decisions to
``UPDATE paper SET quality_status = ...`` as part of their own
transaction.

Per OpenSpec change ``prof-paper-patent-from-page-flow`` spec
Requirement "Quality status promotion logic" (V019 six-value enum):

| From → To | Trigger |
|---|---|
| (initial) → needs_enrichment   | New paper from prof-page with gaps   |
| needs_enrichment → ready       | All required fields + summary_zh OK   |
| needs_enrichment → partial     | Enrichment partially succeeded        |
| needs_enrichment → partial     | Boilerplate judge rejects summary_zh retry |
| ready → needs_review           | Admin manual flag                     |
| low_confidence → ready /
  needs_review                   | Identity-gate post-enrichment re-eval |

Forward-monotonic invariant (design.md §12): once a row reaches
``ready`` it does NOT auto-degrade on a later enrichment failure. Only
admin intervention or detected contradiction can take it back to
``needs_review``. ``rejected`` is reserved for row-level invalidity
such as admin rejection or identity/contradiction gates. A generated
summary rejection clears ``summary_zh`` but keeps the canonical row
retryable because DOI/page evidence may still be valid.
"""

from __future__ import annotations

from dataclasses import dataclass


# V019 six-value enum, kept in sync with the migration's check
# constraint via ``VALID_QUALITY_STATUSES``.
NEEDS_REVIEW = "needs_review"
READY = "ready"
LOW_CONFIDENCE = "low_confidence"
NEEDS_ENRICHMENT = "needs_enrichment"
PARTIAL = "partial"
REJECTED = "rejected"

VALID_QUALITY_STATUSES = frozenset(
    {NEEDS_REVIEW, READY, LOW_CONFIDENCE, NEEDS_ENRICHMENT, PARTIAL, REJECTED}
)


@dataclass(frozen=True, slots=True)
class PaperEnrichmentSignals:
    """Boolean view of a paper canonical row used by the promotion check.

    Construct from the canonical row (e.g. ``apps/miroflow-agent.../
    paper/canonical_writer.upsert_paper`` callers) and pass to
    ``evaluate_paper_promotion`` — keeping signal extraction at the
    caller lets us promote without coupling this module to the DB
    schema or to ``PaperRecord`` Pydantic.

    "Required" fields (spec Requirement "Quality status promotion
    logic" + "Async enrichment workflow"): title, year, venue,
    authors, abstract. ``summary_zh`` is also required for ``ready``
    plus must pass the boilerplate judge.
    """

    has_title: bool
    has_year: bool
    has_venue: bool
    has_authors: bool
    has_abstract: bool
    has_summary_zh: bool
    summary_zh_boilerplate_rejected: bool = False


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Decision returned by ``evaluate_paper_promotion``.

    ``reason`` is a short token suitable for ``pipeline_issue`` body
    or admin audit logs; ``next_status`` is what the caller writes to
    ``paper.quality_status`` (skip the write when ``next_status ==
    current_status`` to keep ``updated_at`` semantics clean).
    """

    next_status: str
    reason: str


def evaluate_paper_promotion(
    *,
    current_status: str,
    signals: PaperEnrichmentSignals,
) -> PromotionDecision:
    """Compute the next quality_status given the current row state.

    Pure: no DB access. The caller decides whether to write
    ``next_status`` back.
    """
    if current_status not in VALID_QUALITY_STATUSES:
        raise ValueError(
            f"current_status must be one of {sorted(VALID_QUALITY_STATUSES)}, "
            f"got {current_status!r}"
        )

    # rejected is terminal for this canonical row; only re-extraction +
    # a fresh judge pass can move it.
    if current_status == REJECTED:
        return PromotionDecision(REJECTED, reason="terminal_rejected")

    # Forward-monotonic: once ready, only admin can degrade (see
    # apply_admin_override). Re-running enrichment / promotion on a
    # ready row is a no-op.
    if current_status == READY:
        return PromotionDecision(READY, reason="forward_monotonic")

    # Manual review buckets stay parked until admin intervenes.
    if current_status == NEEDS_REVIEW:
        return PromotionDecision(NEEDS_REVIEW, reason="awaiting_admin")

    # Boilerplate judge rejected only the generated Chinese summary.
    # Keep the canonical row retryable; callers clear summary_zh.
    if signals.summary_zh_boilerplate_rejected:
        enriched_fields = sum(
            [
                signals.has_year,
                signals.has_venue,
                signals.has_authors,
                signals.has_abstract,
            ]
        )
        if enriched_fields >= 1:
            return PromotionDecision(PARTIAL, reason="summary_rejected_needs_retry")
        return PromotionDecision(NEEDS_ENRICHMENT, reason="summary_rejected_no_enrichment")

    required_present = all(
        [
            signals.has_title,
            signals.has_year,
            signals.has_venue,
            signals.has_authors,
            signals.has_abstract,
            signals.has_summary_zh,
        ]
    )

    if required_present:
        return PromotionDecision(READY, reason="all_required_fields_present")

    # At least some enrichment progress (title is always present from
    # the page; the bar is "we filled in at least one of the gaps").
    enriched_fields = sum(
        [
            signals.has_year,
            signals.has_venue,
            signals.has_authors,
            signals.has_abstract,
            signals.has_summary_zh,
        ]
    )
    if enriched_fields >= 1:
        return PromotionDecision(PARTIAL, reason="partial_enrichment")

    return PromotionDecision(NEEDS_ENRICHMENT, reason="awaiting_enrichment")


def apply_admin_override(
    *,
    current_status: str,
    override_action: str,
) -> PromotionDecision:
    """Apply an admin-initiated status transition.

    Supported ``override_action`` values:

    - ``"flag_for_review"``: any non-terminal status → ``needs_review``.
      Used when the admin spots a contradiction or quality issue on an
      already-promoted row. This is the only path that takes ``ready``
      backwards (per spec Requirement "Quality status promotion logic"
      + design.md §12).
    - ``"approve"``: ``needs_review`` → ``ready`` (manual upgrade).
    - ``"reject"``: any non-``ready`` status → ``rejected``. Mirrors
      the boilerplate-judge reject path but for admin-flagged content
      issues.

    Unknown actions raise ``ValueError`` so callers don't silently
    fall through with bad input from an API request.
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


def apply_identity_gate_reevaluation(
    *,
    current_status: str,
    gate_accepted: bool,
) -> PromotionDecision:
    """Identity-gate post-enrichment re-evaluation (V019 spec table row
    ``low_confidence → ready / needs_review``).

    When an existing ``low_confidence`` row gets enrichment-side
    authorship data, the identity gate re-evaluates. Accept → ``ready``;
    reject → ``needs_review`` (manual queue, not auto-rejected — the
    paper exists, we just can't auto-attribute it).
    """
    if current_status not in VALID_QUALITY_STATUSES:
        raise ValueError(
            f"current_status must be one of {sorted(VALID_QUALITY_STATUSES)}, "
            f"got {current_status!r}"
        )

    if current_status != LOW_CONFIDENCE:
        # Re-eval only applies to low_confidence rows; everything else
        # is a no-op (keeps the function safe to call on any status).
        return PromotionDecision(current_status, reason="not_low_confidence")

    if gate_accepted:
        return PromotionDecision(READY, reason="identity_gate_accept")
    return PromotionDecision(NEEDS_REVIEW, reason="identity_gate_reject")
