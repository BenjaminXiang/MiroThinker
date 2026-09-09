"""Tests for ``professor.patent_identity_gate`` (T5.3 / T5.4).

Per OpenSpec change ``prof-paper-patent-from-page-flow`` spec
Requirement "Identity gate semantics": the patent-side gate mirrors the
paper-side contract but without an LLM step, since design.md §8 forbids
external patent enrichment. Three flows tested:

- Page-only attribution → confidence 1.0 (parallel to paper-side
  Scenario "Page-only attribution → unconditional acceptance").
- Xlsx-side same-name conflict (parallel to "OpenAlex enrichment
  reveals same-name conflict" but driven by deterministic inventor-list
  comparison rather than an LLM).
- Low-confidence reject → caller's responsibility to file
  ``pipeline_issue`` with ``stage='identity_gate'`` (asserted via the
  contract that ``not accepted and confidence < 0.5``).
"""

from __future__ import annotations

from src.data_agents.professor.name_variants import NameVariants
from src.data_agents.professor.patent_identity_gate import (
    NAME_MISMATCH_REASONING,
    PAGE_ONLY_REASONING,
    XLSX_AMBIGUOUS_REASONING,
    XLSX_EXACT_MATCH_REASONING,
    PatentIdentityCandidate,
    PatentIdentityDecision,
    accept_page_only_attribution,
    verify_xlsx_attribution,
)


# --- Page-only path --------------------------------------------------------


def test_page_only_attribution_accepts_at_confidence_one():
    candidate = PatentIdentityCandidate(
        index=0,
        title="一种用于X的方法",
    )
    decision = accept_page_only_attribution(candidate)
    assert isinstance(decision, PatentIdentityDecision)
    assert decision.accepted is True
    assert decision.confidence == 1.0
    assert decision.reasoning == PAGE_ONLY_REASONING


def test_page_only_attribution_ignores_inventors_field():
    """Even if inventors were populated by an earlier extraction step,
    the page-only short-circuit takes precedence (the caller has decided
    the attribution path)."""
    candidate = PatentIdentityCandidate(
        index=0,
        title="一种用于X的方法",
        inventors=("张三", "李四"),
    )
    decision = accept_page_only_attribution(candidate)
    assert decision.accepted is True
    assert decision.confidence == 1.0


# --- Xlsx-side: exact match -------------------------------------------------


def test_xlsx_attribution_single_inventor_exact_match():
    candidate = PatentIdentityCandidate(
        index=0,
        title="一种处理X的方法",
        patent_id="ZL202310099999.X",
        inventors=("张三",),
    )
    decision = verify_xlsx_attribution(candidate, professor_canonical_name="张三")
    assert decision.accepted is True
    assert decision.confidence == 1.0
    assert decision.reasoning == XLSX_EXACT_MATCH_REASONING


def test_xlsx_attribution_multi_inventor_one_match():
    candidate = PatentIdentityCandidate(
        index=0,
        title="一种处理X的方法",
        inventors=("张三", "李四", "王五"),
    )
    decision = verify_xlsx_attribution(candidate, professor_canonical_name="张三")
    assert decision.accepted is True
    assert decision.confidence == 0.9
    assert decision.reasoning == XLSX_EXACT_MATCH_REASONING


def test_xlsx_attribution_with_name_variants_matches_english_form():
    """Cross-script matching: zh canonical name, en inventor."""
    variants = NameVariants(
        zh="张三",
        en="Zhang San",
        pinyin="Zhang San",
        initials=("Z. San",),
        all_lower=("张三", "zhang san", "z. san"),
    )
    candidate = PatentIdentityCandidate(
        index=0,
        title="A method for X",
        inventors=("Zhang San",),
    )
    decision = verify_xlsx_attribution(
        candidate,
        professor_canonical_name="张三",
        name_variants=variants,
    )
    assert decision.accepted is True
    assert decision.confidence == 1.0


def test_xlsx_attribution_initials_form_also_matches():
    variants = NameVariants(
        zh="张三",
        en="Zhang San",
        pinyin="Zhang San",
        initials=("Z. San",),
        all_lower=("张三", "zhang san", "z. san"),
    )
    candidate = PatentIdentityCandidate(
        index=0,
        title="A method",
        inventors=("Z. San", "Wang Wu"),
    )
    decision = verify_xlsx_attribution(
        candidate,
        professor_canonical_name="张三",
        name_variants=variants,
    )
    assert decision.accepted is True
    assert decision.confidence == 0.9


# --- Xlsx-side: same-name collision ----------------------------------------


def test_xlsx_attribution_same_name_collision_is_uncertain_reject():
    """Two inventors with identical names → gate cannot decide which is
    the target; caller MAY escalate to manual review."""
    candidate = PatentIdentityCandidate(
        index=0,
        title="一种合作发明",
        inventors=("张三", "张三"),
    )
    decision = verify_xlsx_attribution(candidate, professor_canonical_name="张三")
    assert decision.accepted is False
    assert decision.confidence == 0.5
    assert decision.reasoning == XLSX_AMBIGUOUS_REASONING


# --- Xlsx-side: reject paths -----------------------------------------------


def test_xlsx_attribution_no_inventors_rejects():
    candidate = PatentIdentityCandidate(index=0, title="方法", inventors=())
    decision = verify_xlsx_attribution(candidate, professor_canonical_name="张三")
    assert decision.accepted is False
    assert decision.confidence == 0.0
    assert decision.reasoning == NAME_MISMATCH_REASONING


def test_xlsx_attribution_no_name_match_rejects_with_low_confidence():
    """Per spec Requirement 'Identity gate semantics': < 0.5 → caller
    SHOULD file pipeline_issue with stage='identity_gate'. We assert the
    decision shape that lets the caller make that decision."""
    candidate = PatentIdentityCandidate(
        index=0,
        title="一种由他人发明的方法",
        inventors=("李四", "王五"),
    )
    decision = verify_xlsx_attribution(candidate, professor_canonical_name="张三")
    assert decision.accepted is False
    assert decision.confidence == 0.0
    assert decision.confidence < 0.5
    assert decision.reasoning == NAME_MISMATCH_REASONING


def test_xlsx_attribution_does_not_match_substring_collisions():
    """'张三' must not be matched inside '张三丰' — exact whole-string
    only (per gate docstring; protects against substring false-accepts)."""
    candidate = PatentIdentityCandidate(
        index=0,
        title="无关方法",
        inventors=("张三丰",),
    )
    decision = verify_xlsx_attribution(candidate, professor_canonical_name="张三")
    assert decision.accepted is False
    assert decision.confidence == 0.0
    assert decision.reasoning == NAME_MISMATCH_REASONING


def test_xlsx_attribution_blank_canonical_name_rejects():
    candidate = PatentIdentityCandidate(
        index=0,
        title="方法",
        inventors=("张三",),
    )
    decision = verify_xlsx_attribution(candidate, professor_canonical_name="   ")
    assert decision.accepted is False
    assert decision.confidence == 0.0


# --- Decision contract -----------------------------------------------------


def test_low_confidence_decisions_signal_pipeline_issue_to_caller():
    """The gate is pure (no DB writes). The contract is:
    ``not accepted and confidence < 0.5`` → caller files pipeline_issue.
    """
    candidate = PatentIdentityCandidate(
        index=0,
        title="他人的方法",
        inventors=("张三丰",),
    )
    decision = verify_xlsx_attribution(candidate, professor_canonical_name="张三")
    assert (not decision.accepted) and decision.confidence < 0.5
