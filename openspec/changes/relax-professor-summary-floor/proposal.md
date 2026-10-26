# Proposal: relax-professor-summary-floor

Human doc: `docs/plans/2026-10-26-systematic-completion-gates.md` §3.10.

## Why

`PROFILE_SUMMARY_MIN_CHARS = 200` was a quality bar for LLM-written biographies.
In practice:

- web-enriched summaries frequently land at 120–190 characters — a pilot run
  rejected 1 of 5 for `profile_summary_too_short`;
- the rule-based fallback worked around the bar by appending
  `该教授在深圳科创领域有持续贡献。` in a loop, which is exactly the template text
  that later polluted 2,149 summaries and their research vectors.

A shorter factual paragraph beats a longer padded one, so the floor moves to 120
(ceiling stays 300, prompt contract updated).

## What Changes

1. `PROFILE_SUMMARY_MIN_CHARS` 200 → 120.
2. The generation prompt says 120–300 characters.
3. Nothing else: the placeholder, language-dominance and meta-language checks are
   unchanged.

## Impact

- Summaries of 120–199 characters now pass instead of being rejected or padded.
- Existing tests: 50 in the professor quality/status suites pass unchanged.

## Out of scope

- Re-running enrichment across the roster (a separate batch decision).
- Changing the ceiling or the other contract checks.
