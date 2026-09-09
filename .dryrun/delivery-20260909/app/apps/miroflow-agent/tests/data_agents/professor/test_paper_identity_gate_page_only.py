"""Tests for the page-only attribution short-circuit on
``paper_identity_gate`` (T5.2).

Per OpenSpec change ``prof-paper-patent-from-page-flow`` spec
Requirement "Identity gate semantics" + Scenario
"Page-only attribution → unconditional acceptance":

> Given a paper candidate sourced solely from prof_id=PROF-X's Tier 2
> page, AND no enrichment data is available yet, WHEN the gate
> evaluates, THEN confidence = 1.0 → automatic acceptance.

The existing batch LLM path (`batch_verify_paper_identity`) is covered
elsewhere; this file targets only the new pure helper.
"""

from __future__ import annotations

from src.data_agents.professor.paper_identity_gate import (
    PAGE_ONLY_REASONING,
    PaperIdentityCandidate,
    PaperIdentityDecision,
    accept_page_only_attribution,
)


def test_page_only_attribution_accepts_at_confidence_one():
    candidate = PaperIdentityCandidate(
        index=0,
        title="Foo Bar",
        authors=["Smith, J. et al."],
        year=2026,
        venue=None,
        abstract=None,
    )
    decision = accept_page_only_attribution(candidate)
    assert isinstance(decision, PaperIdentityDecision)
    assert decision.accepted is True
    assert decision.confidence == 1.0
    assert decision.reasoning == PAGE_ONLY_REASONING
    assert decision.error is None


def test_page_only_attribution_preserves_index():
    candidate = PaperIdentityCandidate(
        index=42,
        title="Some Title",
        authors=["Lee, K."],
    )
    decision = accept_page_only_attribution(candidate)
    assert decision.index == 42


def test_page_only_attribution_ignores_authors_orcid():
    """ORCID is an enrichment-side signal; page-only short-circuit
    doesn't care whether the upstream resolver attached one or not."""
    candidate = PaperIdentityCandidate(
        index=0,
        title="Foo Bar",
        authors=["Smith, J."],
        authors_orcid=["0000-0001-2345-6789"],
    )
    decision = accept_page_only_attribution(candidate)
    assert decision.accepted is True
    assert decision.confidence == 1.0
    assert decision.reasoning == PAGE_ONLY_REASONING
