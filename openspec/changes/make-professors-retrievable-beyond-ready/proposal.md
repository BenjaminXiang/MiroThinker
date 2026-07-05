# Proposal: make-professors-retrievable-beyond-ready

> Behavior-affecting. Amends `agentic-rag-retrieval` (professor recall filter).
> Grounded in `docs/solutions/2026-07-03-data-gap-first-principles.md` + the gate-vs-data
> first-principles analysis (2026-07-05): professor data is 94.5% official-sourced (high
> quality); the strict conjunction gate conflates publication-completeness with retrievability.

## Why

65% of professors (2,221/3,409) are NOT `ready`, so they are dropped by the vector-recall
quality filter and invisible to professor search — even though they are real, identified
entities collected from official sources, already embedded in Milvus (`professor_identity_profiles`
+ `professor_research_profiles`, all 3,409), and answerable for real queries. The "limited search"
symptom the user reports is dominated by this.

First-principles: `quality_status` is a **publication-completeness** contract (is this record
polished enough to display?), but the filter used it as the **retrievability** gate. These are
different concerns. A professor with a resolved identity, canonical name, and institution is
retrievable/useful regardless of whether every derived field (research_overview_zh, paper_summary,
…) is filled. This is the professor analog of Lever 0's completeness↔retrievability coupling.

## What Changes

1. **MODIFY** the professor branch of the vector-recall quality filter
   (`retrieval._filter_ready_only`): admit professors whose `quality_status` is NOT
   `low_confidence` — i.e. `ready`, `needs_review`, `needs_enrichment` are all retrievable.
   `low_confidence` (non-person-name / profile-blob / reader-artifact / missing-official-source)
   remains excluded (not a reliable entity). rejected/merged identity stay excluded upstream
   (not embedded).
2. `quality_status` becomes a **ranking signal** (better-embedded `ready` profiles rerank higher),
   not a retrieval gate.
3. No embedding change (all 3,409 professors are already embedded), no gate-criteria change,
   no persisted-column change, no migration.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `agentic-rag-retrieval`: professor vector recall SHALL admit any professor whose
  `quality_status != low_confidence` (decoupling retrievability from publication-completeness);
  `low_confidence` remains excluded. (Capability in-flight via `fix-chat-retrieval-recall-gaps`.)

## Impact

- **Recall**: ~2,176 additional professors become vector-retrievable (3,386 vs 1,210 ready-only).
- **Code**: `retrieval._filter_ready_only` professor branch (one conditional); tests updated
  (`test_retrieval_quality_filter.py` professor case + new `test_retrieval_filter.py` case).
- **Risk**: less-polished professors (`needs_review`) enter the candidate pool → precision risk
  (weak-profile matches). Mitigated by: only `low_confidence` excluded (the truly-unreliable);
  rerank + the precision oracle (to be labeled); `ready` ranks higher. This change is eval-gated
  on breadth (more professors returned for topic queries) WITHOUT precision regression.
- **Invariant**: evidence remains source-traceable; `quality_status` enum/`ready` criteria
  unchanged; the publication contract (`ready`) is preserved for display-quality decisions.
