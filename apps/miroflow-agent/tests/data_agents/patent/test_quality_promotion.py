"""Tests for patent quality_status promotion state machine (T7.4).

Per OpenSpec change ``prof-paper-patent-from-page-flow`` spec
Requirement "Quality status promotion logic" + design.md §8 (no
external patent enrichment).
"""

from __future__ import annotations

import pytest

from src.data_agents.patent.quality_promotion import (
    NEEDS_ENRICHMENT,
    NEEDS_REVIEW,
    PARTIAL,
    READY,
    REJECTED,
    PatentEnrichmentSignals,
    apply_admin_override,
    evaluate_patent_promotion,
)


def _xlsx_full() -> PatentEnrichmentSignals:
    return PatentEnrichmentSignals(
        has_patent_number=True,
        has_title=True,
        has_patent_type=True,
        has_filing_or_grant_date=True,
        has_applicants_or_inventors=True,
        xlsx_merged=True,
    )


def _page_only() -> PatentEnrichmentSignals:
    return PatentEnrichmentSignals(
        has_patent_number=True,
        has_title=True,
        has_patent_type=False,
        has_filing_or_grant_date=False,
        has_applicants_or_inventors=False,
        xlsx_merged=False,
    )


# --- evaluate_patent_promotion ---------------------------------------------


def test_xlsx_merge_with_all_required_promotes_to_ready():
    decision = evaluate_patent_promotion(
        current_status=NEEDS_ENRICHMENT,
        signals=_xlsx_full(),
    )
    assert decision.next_status == READY
    assert decision.reason == "xlsx_merged_all_required"


def test_xlsx_merge_with_gaps_lands_in_partial():
    signals = PatentEnrichmentSignals(
        has_patent_number=True,
        has_title=True,
        has_patent_type=True,
        has_filing_or_grant_date=False,
        has_applicants_or_inventors=False,
        xlsx_merged=True,
    )
    decision = evaluate_patent_promotion(
        current_status=NEEDS_ENRICHMENT,
        signals=signals,
    )
    assert decision.next_status == PARTIAL
    assert decision.reason == "xlsx_merged_with_gaps"


def test_page_only_stays_needs_enrichment():
    """Per design.md §8: page-only patents stay incomplete until xlsx
    import or admin intervenes — no external API to call."""
    decision = evaluate_patent_promotion(
        current_status=NEEDS_ENRICHMENT,
        signals=_page_only(),
    )
    assert decision.next_status == NEEDS_ENRICHMENT
    assert decision.reason == "awaiting_xlsx_or_admin"


# --- forward-monotonic ------------------------------------------------------


def test_ready_does_not_auto_degrade_on_signal_loss():
    """Forward-monotonic: a `ready` patent stays `ready` even if a
    later cron pass sees gaps (e.g. a partial xlsx re-import that
    overwrites with NULLs would not be allowed to drag the row back)."""
    decision = evaluate_patent_promotion(
        current_status=READY,
        signals=_page_only(),
    )
    assert decision.next_status == READY
    assert decision.reason == "forward_monotonic"


def test_rejected_is_terminal():
    decision = evaluate_patent_promotion(
        current_status=REJECTED,
        signals=_xlsx_full(),
    )
    assert decision.next_status == REJECTED


def test_needs_review_parks_until_admin():
    decision = evaluate_patent_promotion(
        current_status=NEEDS_REVIEW,
        signals=_xlsx_full(),
    )
    assert decision.next_status == NEEDS_REVIEW
    assert decision.reason == "awaiting_admin"


def test_invalid_current_status_raises():
    with pytest.raises(ValueError, match="current_status must be one of"):
        evaluate_patent_promotion(
            current_status="bogus",
            signals=_page_only(),
        )


# --- apply_admin_override --------------------------------------------------


def test_admin_can_directly_promote_page_only_to_ready():
    """Patents have no external enrichment path; admin manual upgrade
    is the only way a page-only row reaches `ready` without xlsx."""
    decision = apply_admin_override(
        current_status=NEEDS_ENRICHMENT,
        override_action="approve",
    )
    assert decision.next_status == READY
    assert decision.reason == "admin_approve"


def test_admin_flag_for_review_degrades_ready():
    decision = apply_admin_override(
        current_status=READY,
        override_action="flag_for_review",
    )
    assert decision.next_status == NEEDS_REVIEW


def test_admin_reject_makes_row_terminal():
    decision = apply_admin_override(
        current_status=READY,
        override_action="reject",
    )
    assert decision.next_status == REJECTED


def test_admin_override_on_rejected_stays_rejected_for_flag_and_approve():
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


def test_admin_override_unknown_action_raises():
    with pytest.raises(ValueError, match="override_action must be one of"):
        apply_admin_override(
            current_status=NEEDS_ENRICHMENT,
            override_action="bogus",
        )
