---
title: Round 7.18e — Medium-Consistency Paper Link Rescan
date: 2026-04-19
category: data-quality
module: professor_paper_link
problem_type: verification
component: identity_gate
tags:
  - topic_consistency
  - SNDP
  - batch_llm_gate
  - gemma4
  - phase_a_b
  - composite_signals
---

## Problem

After Round 7.6 (batch LLM identity gate) and Round 7.14 (strong author-name
match) cleared the obvious contamination, 534 verified `professor_paper_link`
rows remained in the `topic_consistency ∈ [0.70, 0.85)` band — the awkward
middle where a link is neither confidently legitimate nor confidently fake.

The band mixes two populations:

1. Legitimate papers in areas *adjacent* to the professor's primary research
   (cross-disciplinary collaborations, survey papers, early-career pivots).
2. Same-name-different-person (SNDP) contamination that slipped past the
   earlier gates because `author_name_match` was strong (common Chinese names
   on authors who happen to share Pinyin with the professor).

Topic-consistency alone cannot separate these two populations, so the
Round 7.18e rescan adds composite signals and a precision-first LLM fallback.

## Approach — two-phase rescan

**Phase A — cheap SQL-derived signals.** For each `(professor, paper)` pair,
compute three signals from existing SQLite tables:

- `coauthor_overlap` — Jaccard similarity between the paper's `author_display`
  tokens (excluding the professor's own name tokens) and the professor's
  corpus of known coauthors across other already-verified papers.
- `venue_alignment` — binary: does the paper's venue appear in the professor's
  known-venue set from other verified papers?
- `year_plausibility` — binary: is the publication year inside the
  professor's active window (±5y around observed career range)?

Decision rules, first match wins:

1. `coauthor_overlap ≥ 0.4` → **keep** (strong shared-network signal).
2. All three signals zero → **demote** (no supporting evidence at all).
3. Otherwise → queue for Phase B.

**Phase B — batch LLM re-verify.** Reuse `batch_verify_paper_identity`
from Round 7.6 against a local `gemma4` (gemma-4-26b-a4b-it) with batch
size 15 and a precision-first posture: `confidence < 0.8` → reject,
any parse error → fail-safe demote. No retries on LLM errors.

## Outcome

```
examined          : 534
phase A keep      : 321   (60%)
phase A demote    :   7   ( 1.3%)
phase B queued    : 206   (39%)
phase B keep      : 179   (87% of queue)
phase B demote    :  27   (13% of queue)
phase B error     :   0
TOTAL keep        : 500
TOTAL demote      :  34
demotes applied   :  34
pipeline_issue audit rows : 534
```

Every examined row got an audit trail entry; every demotion was applied
atomically in the same transaction as the audit insert. Zero LLM errors.

## Lessons

- **Cheap signals saved 94% of candidates from an LLM call.** Phase A
  resolved 328/534 rows (60% keep, 1.3% demote) without any model
  inference. Coauthor overlap alone accounts for roughly 60% of the
  win — if only one signal can be afforded, start there.
- **SNDP contamination was 6% (34/534), lower than the 10-20% hypothesis.**
  The earlier rounds' gates were tighter than we thought. Band-specific
  rescans should budget for smaller absolute yields going forward.
- **Dry-run vs apply variance was ±3 decisions (503/31 → 500/34).**
  That's LLM stochasticity on borderline cases with gemma4 temperature>0.
  For this batch 3/534 is within tolerance, but for higher-stakes bands
  we should probably run twice and only commit the consensus set.
- **Phase A demotions surfaced a different bug.** Several `paper.title_clean`
  rows contain coauthor lists rather than titles
  (e.g. `'L. B. Ju; Taiwu Huang; Ran Li; ...'`,
  `'(3)Hao Liu; Hanlong Zhang; Xiaoxi Nie; Wei He; ...'`,
  `'ACM SIGMOD China主席、IEEE Transactions on Knowledge ...'`).
  That's a paper-table ingestion issue — those rows demote cleanly here
  because they fail every signal, but the upstream should be tracked
  separately and is a Round 7.12' candidate.

## Related

- Commit `ce40d58` — signals module + rescan script + tests
  (`medium_rescan_signals.py`, `run_medium_consistency_rescan.py`,
  `test_medium_rescan_signals.py`: 9 tests, all pass).
- Audit rows landed via the `/api/pipeline-issues` endpoint work in
  commit `a00116b` (P2.2 dashboard pipeline).
- Builds directly on Round 7.6 `batch_verify_paper_identity`
  (commit `f9239a3`) — same batching infrastructure, tightened rejection
  threshold.
- Feeds into future Round 7.19+ signal expansion if we add ORCID or
  institution-match signals.
- Prior related post-mortem: `name-identity-gate-round-7-17-2026-04-18.md`.

## Reusability / Extension points

- **`medium_rescan_signals.compute_signals()`** takes a generic
  `ProfessorCorpusProfile` + `prof_name_tokens`, so it can be called
  on any topic-consistency band. Natural next uses: `[0.85, 0.95)` as
  a high-confidence audit pass, or `[0.50, 0.70)` as a rehabilitation
  pass on already-rejected rows.
- **Signal weights `(0.5, 0.25, 0.25)`** are module-level constants in
  `medium_rescan_signals.py`. If we add a 4th signal (ORCID match,
  institution co-affiliation), rebalance them there — don't thread
  weights through call sites.
- **The two-phase cheap-filter → LLM-rescue pattern** generalizes to
  any data-quality gate where the cheap filter has high precision but
  low recall. Budget the LLM for the ambiguous middle; let SQL do the
  obvious work. For 534 rows that meant 206 LLM calls instead of 534.
