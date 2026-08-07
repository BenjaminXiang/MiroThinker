# Proposal: make-partial-papers-retrievable

> **Lifecycle clarification (2026-07-10): Accepted structural behavior dependency.** The implemented
> partial-rich eligibility/snippet/admission contract remains authoritative. Historical Task 2.1
> did not measure ready-but-not-embedded D3 and is not evidence of parity; that disjoint measurement
> is superseded by Slice F of `close-retrieval-generation-contract`, which reconciles every paper
> and exact chunk manifest under a frozen rule version. Archive this change normally only when its
> accepted deltas can migrate into canonical specs; do not treat the superseded D3 task as measured.

> Behavior-affecting. Deltas two in-flight capabilities: `data-quality-gating`
> (relaxes the retrieval-readiness invariant `unify-data-quality-gating` just
> established) and `agentic-rag-retrieval` (fixes an embedding-source ⊋
> snippet-source asymmetry so newly-retrievable papers are also presentable).
> Grounded in `docs/solutions/2026-07-03-data-gap-first-principles.md` +
> read-only `miroflow_real` scans this session.

## Why

`is_indexable ≡ (quality_status == "ready")` couples **retrievability** to
**completeness**: a paper whose full text is already collected locally is
invisible to vector recall purely because a *derived* field (`summary_zh`) is
NULL. The retrieval-readiness invariant set by `unify-data-quality-gating`
codifies this coupling ("indexable == gate-promoted-`ready`").

A read-only `miroflow_real` scan this session measured the structural waste:

| Paper population | Count | Retrievable today? | Why |
|---|---|---|---|
| `ready` | 25,990 | yes | full gate passed |
| `partial` + collected full text (`paper_full_text.abstract`/`intro`) | **~2,010** | **no** | `summary_zh` NULL → not `ready` → `is_indexable=False` |
| `partial` title-only | ~7,212 | no (and should not be) | data-poor; precision risk |
| `needs_enrichment` | 14,343 | no | no full text collected (Lever 3, out of scope) |

The ~2,010 partial-with-full-text papers are **pure structural waste**: the
data a topic query matches against (abstract text) IS collected, the chunker
produces a rich `abstract`/`intro` chunk for them, yet the gate (not the
chunker) blocks embedding and the recall filter blocks admission. This is the
structural root behind the recall ceiling — bigger than any single logic patch
and independent of external-source throttling (no OpenAlex/arXiv dependency).

A second, related defect: the **embedding source is a strict superset of the
snippet source**. `milvus_backfill._paper_embedding_abstract` embeds off
`summary_zh OR abstract_clean OR paper_full_text.abstract`, but the
title-exact snippet builder (`_paper_title_snippet`) and the vector-recall
filter only honor `summary_zh`/`abstract_clean`. So a paper can be embedded
off `paper_full_text.abstract` yet yield an **empty generation snippet** —
recalled but invisible to the answer, hence invisible to the recall oracle.
Any change that makes partials retrievable must also make them presentable,
else it is half-finished.

## What Changes

1. **MODIFY** the retrieval-readiness invariant (`data-quality-gating`): a
   `partial` paper SHALL be indexable iff it carries collected rich retrieval
   text (`paper_full_text.abstract` or `paper_full_text.intro` non-empty).
   `ready` remains the completeness contract for all domains; `partial`-with-
   rich-text is a *retrievability* relaxation, not a completeness change. A
   title-only `partial` (and all `needs_enrichment`) SHALL NOT be indexable.

2. **MODIFY** `gating_contract.is_indexable` and `paper/milvus_backfill._is_indexable_paper`
   to admit `partial`-with-collected-rich-text (the backfill SQL already
   fetches these rows; today it deletes their chunks). No new persisted
   column: the rich-text predicate is derived from `paper_full_text` at
   backfill time, not a parallel readiness signal.

3. **MODIFY** the vector-recall quality filter
   (`retrieval._filter_ready_only` / `_allow_non_ready_exact_paper`) to admit
   a vector-recalled `partial` paper that carries collected rich text — today
   only `ready` papers (and `paper_title_exact` non-ready with a snippet)
   pass this filter, so a newly-embeddable partial would be recalled by ANN
   then dropped before rerank.

4. **MODIFY** the paper snippet source chain (`_paper_title_snippet` and the
   vector Evidence snippet path) to include `paper_full_text.abstract` as a
   fallback after `summary_zh`/`abstract_clean`, so a retrievable partial is
   also presentable. This fixes the embedding-source ⊋ snippet-source
   asymmetry for all papers, present and future.

5. **Couple** a one-time Milvus rebackfill for the ~2,010 newly-indexable
   partials (the backfill hook already exists; this change triggers it for the
   new population). Write-path behavior for future partials is covered by the
   existing rebackfill coupling.

### Non-goals (deliberately excluded — separate changes)

- **Title-only `partial` indexing** (~7,212): precision risk, deferred. This
  change strictly scopes to partial-with-collected-rich-text.
- **`needs_enrichment` abstract backfill** (14,343): genuinely data-poor, no
  full text collected → owned by Lever 3 (abstract source-tracing + external
  throttling). Not salvageable by retrievability relaxation.
- **Professor path** (`unify`'s D2 was a false premise): owned by Lever 1
  (professor reason-class batch repair). Separate change.
- **Graph rescue** (Move C): owned by Lever 2. Independent, zero-contract.
- **D3 (ready-but-not-embedded)**: historical measurement was not completed in this change. It is
  now owned by the complete paper/chunk reconciler in Slice F of
  `close-retrieval-generation-contract`, not inferred from the partial targeted rebackfill.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `data-quality-gating`: relaxes the "Retrieval-readiness invariant" so a
  `partial` paper with collected rich retrieval text is indexable; defines the
  rich-text predicate and excludes title-only partials. (Capability being
  introduced by in-flight `unify-data-quality-gating`; this change amends its
  invariant before archive.)
- `agentic-rag-retrieval`: extends the paper snippet source chain to include
  `paper_full_text.abstract` (fixes embedding-source ⊋ snippet-source
  asymmetry); admits vector-recalled `partial`-with-rich-text through the
  quality filter. (Capability being introduced by in-flight
  `fix-chat-retrieval-recall-gaps`; this change amends its recall/snippet
  requirements before archive.)

## Impact

- **Code**: `src/data_agents/quality/gating_contract.py` (`is_indexable`),
  `src/data_agents/paper/milvus_backfill.py` (`_is_indexable_paper` +
  backfill SQL richness check), `src/data_agents/service/retrieval.py`
  (`_filter_ready_only`, `_allow_non_ready_exact_paper`,
  `_paper_title_snippet`, the vector Evidence snippet path, the title-exact
  SELECT to join `paper_full_text`).
- **Data contract**: relaxes the indexability invariant; does NOT change the
  `quality_status` enum, the `ready` criteria, `identity_status` semantics, or
  any persisted column. No migration.
- **Retrieval**: ~2,010 partial papers enter the vector pool → topic-vector
  recall gains candidates; precision must not regress (precision-oracle guard
  in the verification contract).
- **Latency**: one extra `paper_full_text` LEFT JOIN in the title-exact SELECT
  + a richness predicate at backfill; both are bounded and the latency oracle
  (p95 9.6s, SLO FAIL on qid26) is watched but this change does not touch
  qid26's cross-domain path.
- **Risk**: a `partial` paper has no `summary_zh` → if the snippet chain is
  not extended (seam 4), the paper is recalled-but-invisible to the answer =
  half-finished. All 4 seams are mandatory in one change; the verification
  contract enforces eval-RED on any seam missing.
