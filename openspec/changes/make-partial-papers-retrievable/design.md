## Context

`is_indexable ≡ (quality_status == "ready")` couples retrievability to
completeness. A `partial` paper whose full text is already collected locally
(`paper_full_text.abstract`/`intro`) is invisible to vector recall purely
because the derived `summary_zh` is NULL. This change relaxes that coupling
for `paper` only, scoped to the ~2,010 partial-with-collected-rich-text rows
measured in `miroflow_real` (2026-07-03). Title-only partials (~7,212) and
`needs_enrichment` (14,343) are explicitly excluded — they are data-poor and
belong to Lever 3.

Current state (verified this session):

- `quality/gating_contract.py:60-69` — `is_indexable` returns
  `normalize_quality_status(quality_status) == "ready"`.
- `paper/milvus_backfill.py:50-56` — backfill SQL fetches partial rows;
  `:86-97` deletes their chunks because `_is_indexable_paper` (`:181`) is
  `identity not in {rejected,merged} AND quality_status == "ready"`.
- `paper/chunker.py` — `chunk_paper` emits a `title` chunk always + optional
  `abstract`/`intro` chunks; a partial-with-full-text produces rich chunks.
- `service/retrieval.py:1200-1272` — `_filter_ready_only` drops non-ready
  vector candidates unless `_allow_non_ready_exact_paper` (title-exact + a
  snippet in `{summary_zh, abstract_clean}`) admits them. Vector-recalled
  partials are dropped.
- `service/retrieval.py:1070-1075` — `_paper_title_snippet` source chain is
  `summary_zh → abstract_clean → title`. `paper_full_text.abstract` is NOT in
  the chain (embedding source ⊋ snippet source).

Stakeholders: chat retrieval (`/api/chat`), Milvus backfill, paper pipeline.
Constraints: CLAUDE.md §5 (evidence traceable, no silent data-contract
change), §8 (behavior-affecting → OpenSpec + eval-first verification
contract), Milvus single-writer ([[milvus-single-writer-real-index]] — backend
holds `milvus.db`; backfill runs against the running backend).

## Goals / Non-Goals

**Goals:**
- Make `partial` papers with collected rich retrieval text both **retrievable**
  (indexed, admitted by the vector filter) and **presentable** (non-empty
  snippet) — all four seams in one change, so no half-finished state.
- Relax the retrieval-readiness invariant for `paper` only; preserve `ready`
  as the completeness contract for all domains.
- No persisted readiness column (the rich-text predicate is derived).
- Eval-first GREEN with a precision-oracle guard: recall gain on topic-vector
  cases with no precision regression.

**Non-Goals:**
- Title-only `partial` indexing (precision risk; deferred).
- `needs_enrichment` abstract backfill (Lever 3; data-poor).
- Professor path (Lever 1) and graph rescue (Lever 2) — separate changes.
- Changing the `quality_status` enum, `ready` criteria, `identity_status`
  semantics, any migration, or any persisted column.
- qid26 latency (cross-domain path; orthogonal).

## Decisions

### D1: Relax `is_indexable`, not redefine `ready` (Option A over B)
`ready` is a cross-domain completeness contract (professor ready ⇒ has
`profile_summary`; paper ready ⇒ has `summary_zh`). Redefining paper `ready` to
drop `summary_zh` (Option B) would fragment `ready`'s meaning and risk
Chinese-answer quality regression (answer generation may rely on
ready ⇒ Chinese summary). Relaxing `is_indexable` to admit
`partial AND has_rich_text` keeps `ready` intact and adds a *retrievability*
dimension that `is_indexable` was always meant to express (it is a separate
function from the promotion gate for exactly this reason). Alternatives
considered: Option B (promote partial→ready) — rejected for semantic
fragmentation + answer-quality risk; Option C (separate retrievable collection,
no gate edit) — rejected as half-finished (partials stay non-retrievable).

### D2: Derive the rich-text predicate from `paper_full_text`, do not persist
A persisted `retrievable`/`indexed` column would be exactly the "second
readiness signal" the unify invariant forbids and would create a freshness
bug (column drifts from `paper_full_text`). The predicate
`paper_has_rich_retrieval_text = EXISTS paper_full_text.abstract OR .intro`
is computed at backfill (SQL) and at filter time (the vector filter re-checks
richness defensively against stale Milvus state). Cost: one `LEFT JOIN
paper_full_text` in the backfill SQL and the title-exact SELECT — bounded.

### D3: All four seams in one change (no half-finished)
Seams: (1) `is_indexable`, (2) `_is_indexable_paper` + backfill SQL richness,
(3) vector-recall filter (`_filter_ready_only`/`_allow_non_ready_exact_paper`),
(4) snippet chain (`_paper_title_snippet` + title-exact SELECT join + vector
Evidence snippet). Missing any seam produces a distinct half-finished state:
- (1)✗ others✓ → gate blocks embedding.
- (2)✗ → backfill deletes chunks.
- (3)✗ → embedded but dropped pre-rerank (eval-RED, looks like no-op).
- (4)✗ → recalled but empty snippet → invisible to answer (eval-RED).
The verification contract's RED phase asserts each seam's failure mode; GREEN
requires all four present.

### D4: Eval-first, precision-guarded GREEN (not unit-only)
Per CLAUDE.md §14.7, agentic-RAG recall work is eval-first — a unit test alone
is not GREEN. RED = baseline recall 12/24 (post-fix-recall.json) + a precision
baseline. GREEN = recall ≥ 14/24 (≥2 newly-retrievable partials surface on
topic-vector cases) with precision oracle not regressed (no new false-positive
entity labels) and no passing case regressed. A unit test asserts the
predicate + filter + snippet at the contract level (deterministic module) but
acceptance is the eval.

### D5: Task 0 — measure D3 (ready-but-not-embedded) before any code
Postgres has no embedding ledger; only Milvus knows. If ready-but-unindexed is
non-zero, "embed already-ready entities" is a zero-data-work, zero-contract
predecessor that should ship first (it does not need this change). Measured by
comparing `paper_chunks` row counts (per paper_id) against `ready` papers via
the running backend's Milvus. If D3 > 0, raise it as a separate slice and
defer this change's rebackfill; this change proceeds regardless because its
unlock (partials) is disjoint.

## Risks / Trade-offs

- **[Precision regression from title-adjacent partials]** → a `partial` paper
  with full-text abstract may be topically adjacent but not the target;
  rerank + the precision oracle guard. Scoping to rich-text (not title-only)
  keeps the embedding substantive. Mitigation: precision-oracle is a hard
  GREEN gate, not advisory.
- **[Stale Milvus state admits a title-only partial that was later enriched]** →
  the vector filter re-checks `paper_has_rich_retrieval_text` defensively, so a
  title-only partial that slipped into Milvus is dropped at filter time.
- **[Snippet from `paper_full_text.abstract` is English while `summary_zh` is
  Chinese]** → answer generation may render an English snippet for a partial.
  Accepted: presentable-but-English is strictly better than invisible; Chinese
  summarization of partials is a Lever 3 follow-up (summary_zh backfill), not
  this change. The snippet `snippet_source` metadata is preserved for the
  generator to detect and label.
- **[Latency: extra `paper_full_text` JOIN in title-exact SELECT]** → bounded
  (one LEFT JOIN on a PK); the latency oracle is watched but this change does
  not touch qid26's cross-domain path.
- **[Milvus single-writer during rebackfill]** → backfill runs against the
  running backend ([[milvus-single-writer-real-index]]); the one-time catch-up
  rebackfill for ~2,010 partials uses the existing `run_milvus_backfill.py`
  with the backend up.

## Migration Plan

No migration. Deploy order:
1. Task 0: measure D3; if >0, ship "embed already-ready" as a separate
   predecessor slice (does not block this change).
2. Code seams 1–4 (one slice, TDD-allowed on the deterministic predicate +
   filter + snippet contract; eval-first for the recall behavior).
3. Unit/contract tests green (predicate, `is_indexable` parity, snippet chain
   order, vector-filter admit/drop).
4. One-time Milvus rebackfill for the newly-indexable partial population
   (`run_milvus_backfill.py`, backend up).
5. Eval: recall ≥ 14/24 with precision not regressed → Accept. Else Revise.

Rollback: revert the code; re-run `run_milvus_backfill.py` (the partial rows
return to non-indexable, their chunks deleted on next backfill). No persisted
state was added, so rollback is a code revert + rebackfill. The relaxation is
additive to `is_indexable` (a new branch), so reverting restores
`is_indexable ≡ ready` exactly.

## Open Questions

- None blocking. D3's magnitude is discovered at Task 0 and may split off a
  predecessor slice but does not change this change's contract.
