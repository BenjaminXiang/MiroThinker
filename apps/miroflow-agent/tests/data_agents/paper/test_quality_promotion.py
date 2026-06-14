"""Tests for paper quality_status promotion state machine (T7.1-T7.3).

Per OpenSpec change ``prof-paper-patent-from-page-flow`` spec
Requirement "Quality status promotion logic" + design.md §12
(forward-monotonic invariant for ``ready``).
"""

from __future__ import annotations

import pytest

from src.data_agents.paper.quality_promotion import (
    LOW_CONFIDENCE,
    NEEDS_ENRICHMENT,
    NEEDS_REVIEW,
    PARTIAL,
    READY,
    REJECTED,
    VALID_QUALITY_STATUSES,
    PaperEnrichmentSignals,
    apply_admin_override,
    apply_identity_gate_reevaluation,
    evaluate_paper_promotion,
)


def _all_fields_present(boilerplate_rejected: bool = False) -> PaperEnrichmentSignals:
    return PaperEnrichmentSignals(
        has_title=True,
        has_year=True,
        has_venue=True,
        has_authors=True,
        has_abstract=True,
        has_summary_zh=True,
        summary_zh_boilerplate_rejected=boilerplate_rejected,
    )


# --- enum integrity --------------------------------------------------------


def test_valid_quality_statuses_match_v019_enum():
    """V019 migration declares the canonical 6-value enum. Keep our
    module's set in lock-step with the migration so a check-constraint
    insert never sees a value we generated."""
    assert VALID_QUALITY_STATUSES == frozenset(
        {
            "needs_review",
            "ready",
            "low_confidence",
            "needs_enrichment",
            "partial",
            "rejected",
        }
    )


# --- evaluate_paper_promotion ----------------------------------------------


def test_promotes_to_ready_when_all_required_fields_present():
    decision = evaluate_paper_promotion(
        current_status=NEEDS_ENRICHMENT,
        signals=_all_fields_present(),
    )
    assert decision.next_status == READY
    assert decision.reason == "all_required_fields_present"


def test_boilerplate_rejection_keeps_canonical_row_retryable():
    """A boilerplate-judge reject only rejects the generated summary.
    The canonical paper remains retryable because DOI/page evidence may
    still be valid and useful for later enrichment."""
    decision = evaluate_paper_promotion(
        current_status=NEEDS_ENRICHMENT,
        signals=_all_fields_present(boilerplate_rejected=True),
    )
    assert decision.next_status == PARTIAL
    assert decision.reason == "summary_rejected_needs_retry"


def test_partial_when_some_enrichment_fields_present():
    decision = evaluate_paper_promotion(
        current_status=NEEDS_ENRICHMENT,
        signals=PaperEnrichmentSignals(
            has_title=True,
            has_year=True,
            has_venue=False,
            has_authors=False,
            has_abstract=True,
            has_summary_zh=False,
        ),
    )
    assert decision.next_status == PARTIAL
    assert decision.reason == "partial_enrichment"


def test_stays_needs_enrichment_when_only_title_present():
    decision = evaluate_paper_promotion(
        current_status=NEEDS_ENRICHMENT,
        signals=PaperEnrichmentSignals(
            has_title=True,
            has_year=False,
            has_venue=False,
            has_authors=False,
            has_abstract=False,
            has_summary_zh=False,
        ),
    )
    assert decision.next_status == NEEDS_ENRICHMENT
    assert decision.reason == "awaiting_enrichment"


def test_partial_can_continue_to_ready_on_full_enrichment():
    """A row already in `partial` should promote to `ready` when the
    next enrichment pass fills the remaining gaps."""
    decision = evaluate_paper_promotion(
        current_status=PARTIAL,
        signals=_all_fields_present(),
    )
    assert decision.next_status == READY


def test_partial_stays_partial_when_gaps_remain():
    decision = evaluate_paper_promotion(
        current_status=PARTIAL,
        signals=PaperEnrichmentSignals(
            has_title=True,
            has_year=True,
            has_venue=True,
            has_authors=True,
            has_abstract=False,
            has_summary_zh=False,
        ),
    )
    assert decision.next_status == PARTIAL


# --- forward-monotonic invariant (design.md §12) ---------------------------


def test_ready_does_not_auto_degrade_on_enrichment_loss():
    """Once `ready`, a later enrichment pass that finds gaps must NOT
    take the row backwards to `needs_enrichment`. Forward-monotonic is
    a load-bearing invariant for chat/browse stability."""
    decision = evaluate_paper_promotion(
        current_status=READY,
        signals=PaperEnrichmentSignals(
            has_title=True,
            has_year=False,
            has_venue=False,
            has_authors=False,
            has_abstract=False,
            has_summary_zh=False,
            summary_zh_boilerplate_rejected=True,  # even with reject signal
        ),
    )
    assert decision.next_status == READY
    assert decision.reason == "forward_monotonic"


def test_rejected_is_terminal():
    decision = evaluate_paper_promotion(
        current_status=REJECTED,
        signals=_all_fields_present(),
    )
    assert decision.next_status == REJECTED


def test_needs_review_parks_until_admin():
    decision = evaluate_paper_promotion(
        current_status=NEEDS_REVIEW,
        signals=_all_fields_present(),
    )
    assert decision.next_status == NEEDS_REVIEW
    assert decision.reason == "awaiting_admin"


def test_invalid_current_status_raises():
    with pytest.raises(ValueError, match="current_status must be one of"):
        evaluate_paper_promotion(
            current_status="unknown_state",
            signals=_all_fields_present(),
        )


# --- apply_admin_override --------------------------------------------------


def test_admin_flag_for_review_degrades_ready_to_needs_review():
    """The only path that takes `ready` backwards."""
    decision = apply_admin_override(
        current_status=READY,
        override_action="flag_for_review",
    )
    assert decision.next_status == NEEDS_REVIEW
    assert decision.reason == "admin_flag_for_review"


def test_admin_approve_promotes_needs_review_to_ready():
    decision = apply_admin_override(
        current_status=NEEDS_REVIEW,
        override_action="approve",
    )
    assert decision.next_status == READY


def test_admin_reject_makes_row_terminal():
    decision = apply_admin_override(
        current_status=READY,
        override_action="reject",
    )
    assert decision.next_status == REJECTED


def test_admin_override_on_rejected_stays_rejected_for_flag_and_approve():
    """Rejected is terminal for the canonical row — admin cannot
    flag-for-review or approve a rejected row (must re-extract from
    source). The function returns the terminal status rather than
    raising, so the API surface stays uniform."""
    assert (
        apply_admin_override(
            current_status=REJECTED,
            override_action="flag_for_review",
        ).next_status
        == REJECTED
    )
    assert (
        apply_admin_override(
            current_status=REJECTED,
            override_action="approve",
        ).next_status
        == REJECTED
    )
    # ...but admin can re-reject explicitly (idempotent).
    assert (
        apply_admin_override(
            current_status=REJECTED,
            override_action="reject",
        ).next_status
        == REJECTED
    )


def test_admin_override_unknown_action_raises():
    with pytest.raises(ValueError, match="override_action must be one of"):
        apply_admin_override(
            current_status=READY,
            override_action="bogus",
        )


# --- apply_identity_gate_reevaluation --------------------------------------


def test_identity_gate_accept_promotes_low_confidence_to_ready():
    decision = apply_identity_gate_reevaluation(
        current_status=LOW_CONFIDENCE,
        gate_accepted=True,
    )
    assert decision.next_status == READY
    assert decision.reason == "identity_gate_accept"


def test_identity_gate_reject_demotes_low_confidence_to_needs_review():
    decision = apply_identity_gate_reevaluation(
        current_status=LOW_CONFIDENCE,
        gate_accepted=False,
    )
    assert decision.next_status == NEEDS_REVIEW
    assert decision.reason == "identity_gate_reject"


def test_identity_gate_reeval_is_noop_on_other_statuses():
    """Re-evaluation only applies to `low_confidence`; calling it on a
    `ready` or `needs_enrichment` row must not change anything."""
    for status in (READY, NEEDS_ENRICHMENT, PARTIAL, NEEDS_REVIEW, REJECTED):
        decision = apply_identity_gate_reevaluation(
            current_status=status,
            gate_accepted=True,
        )
        assert decision.next_status == status
        assert decision.reason == "not_low_confidence"
