## Context

P0 through P8 have moved the Professor domain from schema repair through seed
coverage, source remediation, controlled full recollection, and post-full audit.
The latest P8 audit after the BRESAR title repair reports `p9_readiness=ready`
and no P9 blockers, but it still reports duplicate identity risk groups and
large historical quality-gate issue counts.

The current publish/index surface for online Professor retrieval is the split
Milvus pair introduced by `professor-retrieval-index-split`:
`professor_identity_profiles` and `professor_research_profiles`. The existing
`run_milvus_backfill.py --domain professor` command can rebuild those
collections from canonical Postgres rows. P9 must therefore be an evidence-first
refresh stage, not a new collection or schema design.

## Goals / Non-Goals

**Goals:**

- Use the current P8 audit result as a hard preflight for P9 execution.
- Explicitly classify remaining duplicate-risk and quality-gate findings as
  accepted P9 residual risks or blockers before refreshing the index.
- Refresh the Professor split Milvus indexes from `miroflow_real` canonical
  rows.
- Verify the refresh with row counts, collection counts, BRESAR title spot
  checks, and retrieval smoke tests.
- Produce a P10 handoff for final user-facing/API validation.

**Non-Goals:**

- No schema migration.
- No canonical duplicate merge.
- No quality-status mass promotion.
- No seed 5 source unblock attempt.
- No deletion or broad historical cleanup.
- No legacy `enriched.jsonl` publish path.
- No expansion of online RAG domains beyond Professor/Paper.

## Decisions

### Decision 1: Treat P8 as the P9 gate

P9 starts by re-running `scripts/run_professor_post_full_quality_audit.py`
against `miroflow_real`. If the report has non-empty `p9_blockers`, P9 records
the blockers and stops before index refresh.

Alternative considered: rely on archived P8 acceptance evidence. That would be
stale after the BRESAR remediation and would not protect against new drift.

### Decision 2: Refresh split Professor Milvus indexes from canonical rows

P9 uses `scripts/run_milvus_backfill.py --domain professor --rebuild` with the
current real database. The default Professor path refreshes identity and
research collections, matching the current retrieval split contract.

Alternative considered: run `run_professor_publish_to_search.py`. That script
publishes legacy enriched JSONL/released-object artifacts and is not the
canonical post-P7/P8 refresh path.

### Decision 3: Do not silently resolve duplicate and quality findings

Duplicate identity risk groups and quality-gate issue counts remain visible in
P9 evidence. P9 may proceed only by explicitly accepting them as non-blocking
for this index refresh. That acceptance is limited to refreshing the index; it
does not claim duplicate cleanup or quality readiness is complete.

Alternative considered: merge duplicates or mass-promote quality statuses in
P9. Those are behavior-changing data cleanup decisions and need separate
OpenSpec changes if required.

### Decision 4: Verify with both write evidence and retrieval smoke

P9 is complete only after the backfill command exits successfully, collection
counts are recorded, and at least one retrieval smoke proves the refreshed
index can return BRESAR with `title=助理教授` under an explicit quality-filter
setting.

Alternative considered: count-only verification. Counts prove write coverage
but do not prove query-time routing, payload shape, or title visibility.

## Risks / Trade-offs

- Full Professor embedding refresh can be slow or provider-limited -> first run
  a dry-run/schema preflight and record failures with resume guidance.
- Most Professor rows still have `quality_status=needs_enrichment` -> retrieval
  smoke must state whether quality filtering is enabled or disabled, and P10
  owns final user-facing quality decisions.
- Duplicate risk groups remain in canonical data -> P9 records them as
  residual risk and does not claim deduplication.
- The local Milvus URI controls the refreshed artifact -> P9 records the exact
  URI and treats it as the rollback checkpoint.
