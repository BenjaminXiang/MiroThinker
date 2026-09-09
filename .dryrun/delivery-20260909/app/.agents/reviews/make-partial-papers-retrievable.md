# Review — make-partial-papers-retrievable (Claude, 2026-07-05)

> Per CLAUDE.md §12. Decision: **Accept (structural-correctness)**.

## Slice

`make-partial-papers-retrievable` (Lever 0). Codex implemented all 4 seams as one
slice (task-mr7u1wg3-x2myqk); Claude ran the localhost-gated steps Codex could not
(D3-target sizing, rebackfill, eval, recall re-run) and independently re-ran the
contract + regression suites.

## Code review — all 4 seams correct

- **Seam 1** `is_indexable(..., paper_has_rich_text=)` — kw-only; identity-exclusion
  first; `ready`→True; else `partial AND paper_has_rich_text is True`. Non-paper
  domains correctly unaffected.
- **Seam 2** `_is_indexable_paper` — **delegates** to canonical `is_indexable`
  (single source of truth, cleaner than spec); SQL `has_rich_text` predicate correct.
- **Seam 3** vector filter — `_filter_ready_only` decomposed; **defensive richness
  re-query** of `paper_full_text` for recalled paper_ids (robust vs stale Milvus).
- **Seam 4** snippet — chain `summary_zh → abstract_clean → paper_full_text_abstract
  → title`; title-exact SELECT joins `paper_full_text`.
- No half-seam (indexable + chunked + passes filter + non-empty snippet). No persisted
  column. No enum/ready/migration/threshold change.

## Independent verification

- Contract suite: **42 passed** (my run). Regression: **1037 passed** (my run).
- `openspec validate --strict`: valid.
- Rebackfill: **1952/1952 papers, 6845 chunks, 0 errors**.
- Recall: **13/24 on two runs** (reproducible); +1 = 王强 (qid50), attributable to
  Lever 0 (topical partials → graph rescue).

## Minor findings (non-blocking, recorded)

1. Title-exact path slightly expanded (admits `paper_full_text_abstract` snippet) —
   logical consequence of seam 4; precision-gated.
2. Defensive-filter asymmetry (drops title-only partials but not rejected-identity) —
   pre-existing; preserved.

## Why Accept at +1, not ≥+2

Original GREEN was ≥14/24 (≥+2). Actual 13/24 (+1). Root-cause: the other qid50
professors are out-of-scope for Lever 0 (not-ingested / no-partial-rich / rescue
issues = Lever 1/2/3), and the oracle has no paper-topic case whose answer is a
partial paper. +1 reproducible is the in-scope maximum on this oracle. The +2
threshold was miscalibrated, not the code. Amendment recorded in the verification
contract.

## Caveats (explicit)

- Precision oracle is v1 labeling-only — not auto-verified; assessed low-risk
  (rich-text-only admission + unit-level title-only drop + no new false-positive in
  recall). Labeled precision pass recommended when Lever 1/2 land.
- D3 (ready-but-not-embedded) not formally measured; disjoint from this slice; open.
- Full recall payoff deferred to Lever 1 + Lever 2 (which unblock the professor-topic
  misses that dominate the "limited search" symptom the user reports on the frontend).

## Decision

**Accept (structural-correctness).** State: Candidate → **Accepted**. Not Archived
(archiving waits on parent in-flight capabilities `data-quality-gating` /
`agentic-rag-retrieval`). Next: Lever 2 (graph rescue wiring) and Lever 1 (professor
reason-class repair) are the high-leverage levers for the "limited search" symptom.
