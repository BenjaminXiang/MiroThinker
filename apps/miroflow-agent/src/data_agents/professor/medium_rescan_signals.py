# SPDX-FileCopyrightText: 2026 MiroThinker Contributors
# SPDX-License-Identifier: Apache-2.0
"""Round 7.18e — cheap signals for re-verifying medium-confidence links.

The Round 7.6/7.14 identity gate produces a `topic_consistency_score` on
`professor_paper_link`. 534 verified links land in the medium band
[0.70, 0.85): passed the gate (usually on strong name match), but topic
alignment is weaker. Some of those are (c) same-name-different-person
contamination that slipped through.

Before paying for a full LLM re-verification, compute 3 cheap signals from
the rest of the prof's verified corpus:

    * coauthor_overlap  — fraction of the paper's coauthors who also
      appear in the prof's OTHER verified papers. SNDP contamination
      usually has zero overlap.
    * venue_alignment   — does the prof have ≥1 other verified paper at
      the same venue (journal/conference)?
    * year_plausibility — is the paper's year within ±5 years of the
      prof's existing verified paper year range?

Composite score (0.0-1.0) with weights 0.5/0.25/0.25. Thresholds consumed
by the cleanup script:

    composite >= 0.7  → keep  (strong lateral evidence, topic mismatch
                              just reflects an adjacent research area)
    composite <= 0.3  → demote (all signals weak; likely SNDP)
    0.3–0.7           → LLM re-verification (phase B)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Weights for the composite score (must sum to 1.0)
_W_COAUTHOR = 0.5
_W_VENUE = 0.25
_W_YEAR = 0.25

# Decision rules (applied in order, first match wins):
#   1. coauthor >= _COAUTHOR_STRONG_KEEP   → keep outright
#   2. all 3 signals zero                   → demote outright
#   3. else                                 → LLM re-verify
# No numeric composite threshold on its own — coauthor overlap
# dominates because SNDP contamination is near-zero on that axis.
_COAUTHOR_STRONG_KEEP = 0.4
_YEAR_TOLERANCE = 5  # ±5 years around prof's verified corpus range


@dataclass(frozen=True, slots=True)
class ProfessorCorpusProfile:
    """Bulk-loaded context for one professor's verified corpus."""

    professor_id: str
    coauthor_tokens: frozenset[str]   # lowercased name tokens across OTHER papers
    venues: frozenset[str]
    year_min: int | None
    year_max: int | None


@dataclass(frozen=True, slots=True)
class SignalScores:
    coauthor_overlap: float   # 0.0-1.0
    venue_alignment: float    # 0.0 or 1.0
    year_plausibility: float  # 0.0 or 1.0
    composite: float          # weighted sum
    verdict: str              # "keep" | "demote" | "llm_needed"


def _tokenize_authors(authors_display: str | None) -> set[str]:
    """Extract comparable name tokens from a comma-separated author string.

    Handles Chinese CJK names ("张三") and western "Firstname Lastname"
    equally by emitting lowercased tokens of length ≥ 2. Splits on the
    unicode "·" and "-" too because "Shu-Tao Xia" should tokenize as
    {"shu-tao", "shutao", "xia"} for some overlap slack.
    """
    if not authors_display:
        return set()
    tokens: set[str] = set()
    # Remove Unicode combining marks commonly found in scraped author strings
    cleaned = authors_display.replace("‐", "-").replace("—", "-")
    for author in re.split(r"[,;；、]", cleaned):
        author = author.strip()
        if not author:
            continue
        # Add the whole author as a token (normalised)
        full_norm = _normalise(author)
        if len(full_norm) >= 2:
            tokens.add(full_norm)
        # Split into sub-tokens (for surname/given overlap)
        for sub in re.split(r"[\s-]+", author):
            sub_norm = _normalise(sub)
            if len(sub_norm) >= 2:
                tokens.add(sub_norm)
    return tokens


def _normalise(token: str) -> str:
    return token.strip().lower()


def _coauthor_overlap_score(
    paper_tokens: set[str], corpus_tokens: frozenset[str]
) -> float:
    """Fraction of the paper's author tokens that also appear in the
    professor's verified corpus (excluding the professor themselves,
    which the caller strips before building corpus_tokens)."""
    if not paper_tokens or not corpus_tokens:
        return 0.0
    matches = sum(1 for t in paper_tokens if t in corpus_tokens)
    return matches / len(paper_tokens)


def compute_signals(
    *,
    paper_authors_display: str | None,
    paper_venue: str | None,
    paper_year: int | None,
    profile: ProfessorCorpusProfile,
    prof_name_tokens: frozenset[str],
) -> SignalScores:
    """Run Phase A signals for one (professor, paper) candidate pair.

    `prof_name_tokens` are the tokens of the target professor's own name
    (lowercased), stripped out of the paper's coauthors before scoring —
    a paper matching on the prof's own name tells us nothing about SNDP.
    """
    paper_tokens = _tokenize_authors(paper_authors_display) - prof_name_tokens
    coauthor = _coauthor_overlap_score(paper_tokens, profile.coauthor_tokens)
    venue = (
        1.0
        if paper_venue and paper_venue in profile.venues
        else 0.0
    )
    year = 0.0
    if (
        paper_year
        and profile.year_min is not None
        and profile.year_max is not None
        and (profile.year_min - _YEAR_TOLERANCE)
        <= paper_year
        <= (profile.year_max + _YEAR_TOLERANCE)
    ):
        year = 1.0
    composite = (
        _W_COAUTHOR * coauthor
        + _W_VENUE * venue
        + _W_YEAR * year
    )
    # Rule-based verdict (see _COAUTHOR_STRONG_KEEP constant docstring).
    if coauthor >= _COAUTHOR_STRONG_KEEP:
        verdict = "keep"
    elif coauthor == 0.0 and venue == 0.0 and year == 0.0:
        verdict = "demote"
    else:
        verdict = "llm_needed"
    return SignalScores(
        coauthor_overlap=coauthor,
        venue_alignment=venue,
        year_plausibility=year,
        composite=composite,
        verdict=verdict,
    )
