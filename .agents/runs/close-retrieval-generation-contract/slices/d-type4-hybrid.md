# Slice Contract: D — type4-hybrid

## Status

Specified — blocked until Slice C is Accepted

Internal checkpoints after unblocking: D0 subject/lexical substrate -> D1 hybrid retrieval. D1
cannot become Ready until D0 is Candidate-reviewed and Accepted with rollback evidence.

## Parent

- OpenSpec change: `openspec/changes/close-retrieval-generation-contract/`
- Depends on: accepted `slices/c-deterministic-paper-paths.md`

## Goal

Make Type4 a structured, paper-level hybrid retrieval path: independent dense and local lexical
candidate lanes, paper-before-rerank aggregation, partial-rich competition, truthful degradation,
and strict local/Web provenance separation.

## Non-goals

- Type3 company traversal, bulk enrichment, embedding ledger/reconciliation, or canonical chat
  cutover.
- Claiming recall without a candidate universe.
- Treating Web pages as local paper objects.

## Allowed scope

- Type4 structured predicate parser and trace model.
- A narrowly scoped reversible normalized paper-subject migration/model, versioned category alias
  map, retained-source-backed bounded category backfill, and reversible PostgreSQL FTS/trigram
  indexes with query-plan proof.
- A benchmark-independent pre-output frozen category cohort and a new immutable derivative snapshot
  created after substrate work, used identically by parent/candidate while preserving A's baseline.
- Bounded local lexical/FTS retrieval, dense/lexical concurrency, candidate normalization,
  paper-level aggregation/fusion/filter/rerank, quality penalties, and lane degradation.
- Local/Web provenance typing at the Type4 planner/evidence boundary.
- Slice-owned tests, fixtures, frozen-topic artifacts, and contract status.

## Forbidden changes

- Query-specific token lists, titles, IDs, or rank boosts tuned to the frozen topic set.
- Chunk-level final ranking that lets one paper occupy multiple positions.
- Global ready-first suppression of partial-rich candidates.
- Web results counted toward local recall/identity or cast as local paper citations.
- Unrelated/canonical paper-column rewrites, category inference from titles, embedding/Milvus writes,
  Type3 traversal, or Type1/Type2 contract changes. Only the explicit subject/lexical substrate
  migration above is allowed.
- Starting Slice E before acceptance.

## Expected unchanged behavior

- Accepted Type1/Type2/Q004/Q017 behavior and canonical grounded-answer contract remain unchanged.
- Non-paper domains and non-Type4 ranking remain unchanged.
- Active index contents remain read-only; Slice D consumes the current snapshot.
- Existing Web fallback remains supplemental but gains truthful provenance/outcome behavior where
  this slice routes it.

## Internal checkpoint contracts

### D0 — subject and lexical substrate

- **Status:** Specified; becomes Ready only after Slice C Accepted and before D1 edits.
- **Goal:** create the reversible source-grounded paper-subject/category/lexical substrate and freeze
  the benchmark-independent derivative snapshot on which D1 is evaluated.
- **Non-goals:** Type4 planner/fusion/ranking changes, holdout scoring, Milvus writes, Type3, or bulk
  non-category enrichment.
- **Allowed scope:** normalized subject migration/model, retained-source cohort/backfill, alias map,
  reversible PostgreSQL FTS/trigram indexes, query plans, and derivative manifests.
- **Forbidden scope:** title-inferred categories, benchmark-ID cohort selection, canonical paper
  rewrites, incomplete undeclared residuals, retrieval output/ranking edits, or mutable A baseline.
- **Required checks/evidence:** migration/model/alias RED; provenance coverage; frozen cohort SQL,
  snapshot, denominator and ID hash; full processed/excluded/residual worklist; index/query-plan and
  downgrade/delete-by-run proof; before/after manifests; review and immutable diff/artifact hash.
- **Stop/rollback:** stop on absent retained evidence, unbounded/unindexed plans, benchmark leakage,
  irreversible schema/data, or inability to give parent/candidate one derivative. Downgrade indexes/
  subject schema, delete only run-owned category rows, restore alias version, and discard derivative.

### D1 — hybrid retrieval

- **Status:** Specified; becomes Ready only after D0 Accepted.
- **Goal:** implement structured Type4 dense+lexical paper-level retrieval, truthful partial/Web
  policy, and meet sealed precision, grounding, semantic, regression, and latency gates.
- **Non-goals:** changing D0 data, eligibility/index backfill, Type1/Type2/Type3 semantics, or
  production cutover.
- **Allowed scope:** predicate parser/trace, bounded local lexical lane, dense/lexical execution,
  paper aggregation/fusion/filter/rerank, quality penalties, provider fixtures, and rollout flag.
- **Forbidden scope:** query-specific boosts, chunk-final duplicates, ready-first suppression, Web
  satisfying local gates, post-output substrate/oracle edits, or Milvus mutation.
- **Required checks/evidence:** parser/lane/ranking/partial/Web RED; paper-level dedupe; identical
  derivative-snapshot paired outputs; sealed union labels/agreement/adjudication; micro-P@5,
  citation/semantic/regression/p95/p99; planner rollback; review and immutable diff/artifact hash.
- **Stop/rollback:** stop on sealed-protocol/snapshot drift, query-specific tuning, precision or SLO
  failure requiring a product trade-off, or scope expansion. Disable D1 planner and restore the
  accepted pre-D1 provider path while retaining accepted D0 substrate unused.

## Required checks

- Parser matrix for topic plus year/range, category, and recency constraints.
- Retrieval-service integration with deterministic dense/lexical/rerank fixtures and real test
  database paper metadata.
- Dense success/failure, lexical success/failure, timeout, empty, and dual-lane cases with typed
  outcome/degradation assertions.
- Repeated-chunk paper aggregation and no-duplicate final-position tests.
- Ready versus partial-rich ranking matrix with applied penalty and visible quality status; title-only
  negative/degradation cases.
- Local/Web identity and provenance negative tests.
- Two-reviewer blinded sealed-union labels/rationales/adjudication with kappa >=0.60, per-topic P@5
  diagnostics, holdout micro-P@5 >=85% over five local slots/topic, citation 100%, semantic, and
  regression gates; post-unblinding code changes require a fresh sealed holdout.
- Retrieval p95 <=6s and synthesis p95 <=15s in Type4 local-only/local-plus-Web buckets.
- Focused lint/type plus strict OpenSpec/diff checks.

## Evidence to update

- Slice D section in `verification.md` and `acceptance.md`, including parsed predicates, candidate
  lane traces, dedupe/fusion artifacts, relevance judgments, quality disclosures, latency, review,
  immutable hashes, and rollback.
- Tasks/change log/portfolio; make Slice E Ready only after Slice D Accepted.

## Stop conditions

- Slice C is not Accepted.
- The approved subject/lexical migration is not reversible, retained category evidence is
  unavailable for frozen fixtures, or indexed mixed-language query plans cannot meet the gate.
- Cohort selection depends on benchmark queries/expected IDs, the declared cohort is not processed
  or residualized, or parent/candidate cannot use one pre-output-frozen derivative snapshot.
- Frozen topic/rubric/blind-label protocol or snapshot identity must change after candidate results
  are seen, or labels cannot be sealed before score calculation/run unblinding.
- Precision gate can pass only through query-specific boosts or excluding difficult frozen topics.
- Latency cannot meet the gate without an architecture/product trade-off.
- Scope enters Type3, Milvus mutation, canonical paper rewrites, or data/index mutation beyond the
  explicitly approved subject/lexical substrate.

## Done means

- Structured constraints are applied at paper level and traceable.
- Dense and lexical lanes degrade independently and fuse after paper aggregation.
- Partial-rich results can compete with a disclosed penalty; title-only limitations are truthful.
- Web remains a separate supplement and cannot satisfy local gates.
- All Slice D quality/semantic/latency/regression gates pass; independent review, immutable hashes,
  and Accepted status are recorded; isolated commits are linked only when explicitly authorized.
- D0 and D1 each have immutable diff/artifact hashes, separate review/rollback, and Accepted
  decisions; a correct substrate with failed ranking cannot silently become Slice E's dependency.

## Rollback

Return the Type4 planner rollout to the prior accepted path; downgrade the subject migration and
PostgreSQL indexes; delete only Slice-D category rows by run ID; restore the prior alias-map version;
and revert the relevant D checkpoint diff (or explicitly authorized isolated commit). D1 can roll
back while leaving D0 accepted but unused. No Milvus rollback belongs to this slice.
Any real D0/D1 rollback first restores downstream F/E controls as the Epic matrix specifies and
invalidates the listed dependent acceptance/archive states.
