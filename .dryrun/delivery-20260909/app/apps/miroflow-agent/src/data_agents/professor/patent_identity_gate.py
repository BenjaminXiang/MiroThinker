# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Identity gate for patent → professor attribution.

Symmetric to ``professor.paper_identity_gate`` but markedly simpler: per
OpenSpec change ``prof-paper-patent-from-page-flow`` design.md §8,
"Patent has no external enrichment; only xlsx-merge can enrich." There
is no OpenAlex / Crossref / Semantic Scholar equivalent for patents, so
the patent-side gate never needs to disambiguate against a probabilistic
external author list — and therefore never needs an LLM judge.

Two attribution paths exist:

1. **Page-only** (T4.3 ``patent.homepage_ingest`` flow). The prof's own
   page declares the patent. Per spec Requirement "Identity gate
   semantics" + design.md §5, the gate accepts at confidence 1.0
   without further verification.

2. **Xlsx-merge** (future ``patent.exact_backfill`` flow). An xlsx
   import lists patent inventors. The gate compares those inventors
   against the professor's canonical name (plus optional name variants
   from ``professor.name_variants.NameVariants``) and produces a
   deterministic confidence score. Same-name collisions with multiple
   inventors are downgraded; exact match (single inventor or unique
   match within the inventor list) is accepted.

The gate is intentionally pure (no DB writes). Callers are responsible
for filing ``pipeline_issue`` rows with ``stage="identity_gate"`` for
decisions with ``confidence < 0.5``, mirroring the paper-side contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .identity_verifier import CONFIDENCE_THRESHOLD
from .name_variants import NameVariants


PAGE_ONLY_REASONING = "prof_page_declaration"
XLSX_EXACT_MATCH_REASONING = "xlsx_inventor_exact_match"
XLSX_AMBIGUOUS_REASONING = "xlsx_inventor_same_name_collision"
NAME_MISMATCH_REASONING = "name_mismatch"


@dataclass(frozen=True, slots=True)
class PatentIdentityCandidate:
    """One patent presented to the gate for verification.

    ``inventors`` is the patent's inventor list as known to the system —
    typically populated by xlsx import. Empty inventors signal a
    page-only candidate (use ``accept_page_only_attribution`` for those).
    """

    index: int
    title: str
    patent_id: str | None = None
    inventors: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PatentIdentityDecision:
    """Per-patent verdict.

    Callers are responsible for filing a ``pipeline_issue`` with
    ``stage="identity_gate"`` when ``not accepted and confidence < 0.5``
    — matches the paper-side contract.
    """

    index: int
    accepted: bool
    confidence: float
    reasoning: str


def accept_page_only_attribution(
    candidate: PatentIdentityCandidate,
) -> PatentIdentityDecision:
    """Return an unconditional accept for a page-only patent candidate.

    Used by ``patent.homepage_ingest`` (T4.3) where the patent is
    discovered exclusively from a prof's Tier 2 / Tier 3 page. With no
    competing claim, the prof's declaration is authoritative; the gate
    is not asked to verify content truth (design.md §4).
    """
    return PatentIdentityDecision(
        index=candidate.index,
        accepted=True,
        confidence=1.0,
        reasoning=PAGE_ONLY_REASONING,
    )


def verify_xlsx_attribution(
    candidate: PatentIdentityCandidate,
    *,
    professor_canonical_name: str,
    name_variants: NameVariants | None = None,
) -> PatentIdentityDecision:
    """Verify that an xlsx-sourced patent really belongs to the target
    professor by comparing the patent's inventor list against the
    professor's canonical name and optional variants.

    Scoring rules (deterministic, no LLM):

    - Inventor list empty                                  → confidence 0.0 (reject)
    - Exactly one inventor and it matches a name form       → 1.0 (accept)
    - Multiple inventors, exactly one matches a name form   → 0.9 (accept)
    - Multiple inventors, more than one matches a name form
      (e.g. two homonyms in a research-group patent)        → 0.5 (uncertain
                                                              reject — caller
                                                              may escalate)
    - No matches at all                                     → 0.0 (reject)
    """
    if not candidate.inventors:
        return PatentIdentityDecision(
            index=candidate.index,
            accepted=False,
            confidence=0.0,
            reasoning=NAME_MISMATCH_REASONING,
        )

    name_forms = _build_name_forms(professor_canonical_name, name_variants)
    if not name_forms:
        return PatentIdentityDecision(
            index=candidate.index,
            accepted=False,
            confidence=0.0,
            reasoning=NAME_MISMATCH_REASONING,
        )

    matches = sum(1 for inventor in candidate.inventors if _matches_any(inventor, name_forms))
    inventor_count = len(candidate.inventors)

    if matches == 0:
        return PatentIdentityDecision(
            index=candidate.index,
            accepted=False,
            confidence=0.0,
            reasoning=NAME_MISMATCH_REASONING,
        )

    if matches == 1 and inventor_count == 1:
        confidence = 1.0
        reasoning = XLSX_EXACT_MATCH_REASONING
    elif matches == 1:
        confidence = 0.9
        reasoning = XLSX_EXACT_MATCH_REASONING
    else:
        # Multiple inventors match the same name form — homonym
        # collision (e.g. patent lists "张三" and "张三 (Jr.)"); the gate
        # cannot disambiguate without further evidence.
        confidence = 0.5
        reasoning = XLSX_AMBIGUOUS_REASONING

    accepted = confidence >= CONFIDENCE_THRESHOLD
    return PatentIdentityDecision(
        index=candidate.index,
        accepted=accepted,
        confidence=confidence,
        reasoning=reasoning,
    )


def _build_name_forms(canonical_name: str, variants: NameVariants | None) -> set[str]:
    forms: set[str] = set()
    if canonical_name and canonical_name.strip():
        forms.add(canonical_name.strip().casefold())
    if variants is not None:
        # NameVariants.all_lower is the canonical deduped-lowercased
        # tuple of every textual form; prefer it over reassembling.
        for value in variants.all_lower or ():
            if value and value.strip():
                forms.add(value.strip().casefold())
    return {form for form in forms if form}


def _matches_any(inventor: str, name_forms: set[str]) -> bool:
    """Match an inventor string against any registered name form.

    Comparison is case-insensitive and trims whitespace. Substring
    matches are deliberately NOT accepted (would conflate "张三" with
    unrelated "张三丰"); only exact whole-string equality counts.
    """
    if not inventor:
        return False
    normalized = inventor.strip().casefold()
    if not normalized:
        return False
    return normalized in name_forms
