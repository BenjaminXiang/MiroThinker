# Verification contract — reduce-rebuild-validation-cost, step 1

Change: `openspec/changes/reduce-rebuild-validation-cost` (step 1 only, trigger /
validator hot paths). Owner slice: `perf/rebuild-trigger-fix`.

Written **before** the production-code edits of this slice. Step 2 (envelope /
authority contract) is explicitly out of this slice.

## Goal / expected behaviour

Same fail-closed semantics, no rejected row lost, and the deferred-commit cost of
the decision batch no longer scales as O(assertions × decisions):

1. the per-row deferred `validate_field_human_review_binding` family must stop
   paying a full scan of `knowledge.canonical_decision` /
   `knowledge.relationship_decision` for every inserted row;
2. `validate_identity_human_review_binding` (mounted on 9 identity tables,
   202,725 assertion rows) must stop paying a per-row scan of
   `knowledge.identity_decision` for every inserted row;
3. the two Python-side per-entity rescan sites in
   `canonical_identity_resolution.py` must become one-pass indexes with identical
   validation outcomes.

## RED assertions (must fail before the change, pass after)

Every assertion is measured on a **copy** of the run15 candidate database
(`miroflow_tgfix_probe`, `CREATE DATABASE ... TEMPLATE
miroflow_candidate_v2_20260913_r1`). The live serving DB and the production data
directory are never written.

| # | RED assertion (fails on today's code) | Instrument |
|---|---|---|
| R1 | one execution of the assertion-table branch of `validate_field_human_review_binding` costs ≥ 10 ms on the 423,493-row decision table | `EXPLAIN (ANALYZE, TIMING OFF, BUFFERS)` of the exact predicate on the copy |
| R2 | a deferred commit of N inserted assertion rows costs ≈ N × R1 (per-row scan), measured end to end on the copy with the real trigger function mounted on a scratch table | `measure_trigger_commit.py` |
| R3 | `validate_identity_human_review_binding`'s first `EXISTS` costs a per-row scan of `knowledge.identity_decision` (47,068 rows) × 202,725 deferred events | `EXPLAIN (ANALYZE)` + `measure_trigger_commit.py` |
| R4 | `assertions_by_source` / `_has_evidence_bound_internal_identifier` rescan the full assertion set per source/decision (`canonical_identity_resolution.py:423-430`, `:1099-1106` → `:2414`) | micro-benchmark on the real assertion counts, recorded in `python-scan-before-after.md` |

## GREEN assertions (must hold after the change)

| # | GREEN assertion | Evidence |
|---|---|---|
| G1 | same predicate, same literals: execution time drops by ≥ 3 orders of magnitude and the plan becomes an index access on a `method = 'human_review'` partial index | before/after `EXPLAIN (ANALYZE)` captured in `explain-analyze-*.txt` |
| G2 | deferred commit of the same N rows drops from ≈ N × 43 ms to ≈ N × µs, and the projected 846,986-row commit is minutes-to-seconds instead of ~10 h | `measure_trigger_commit.py` before/after |
| G3 | behaviour equivalence: with a human-review decision present, inserting an assertion that is an origin of a review case still raises `23514` (ERRCODE unchanged), including when the review case lives in a *later* release than the assertion (the release-level guard must not fail open); with no human-review decision the same insert commits | the reviewed-release fixtures of `tests/canonical_v2/test_canonical_decision_postgres.py` re-run **at migration head** via the evidence-only plugin `bump_revision_plugin.py` (`pytest-head-revision.txt`); the skip path is shown by the scratch-table commits in `measure-after.jsonl` |
| G4 | the existing reviewed-field immutability coverage still rejects: `test_direct_sql_review_rows_reject_null_hash_and_relational_cross_wiring` and `test_concurrent_late_origin_edge_and_review_cannot_both_commit` stay green | `tests/canonical_v2/test_canonical_decision_postgres.py` |
| G5 | identity resolution produces identical decisions/assertions with the indexed lookup (same error messages, same fail-closed rejects) | `tests/canonical_v2/` identity suites + the contract test added in this slice |
| G6 | the new migration applies **and** downgrades cleanly on the copy database, leaving the previous trigger/index state intact | `alembic upgrade C2_0014` + `alembic downgrade C2_0013` run against `miroflow_tgfix_probe` |

## Do-not-weaken checklist (§12.5 / A7)

- Every `RAISE EXCEPTION ... ERRCODE = '23514'` in the three validators keeps its
  message text and its predicate; only *when* the predicate is evaluated changes.
- No validator is deleted, disabled, made non-deferred, or bypassed.
- No trigger is removed; the row-level deferred mount points stay.
- The Python change keeps every validation branch and error string.

## Out of scope

Step 2 (envelope slimming); real rebuild timing (run16 re-measures in-pipeline);
`domain_inclusion_decision_assertion` repair only if it turns out to share the
defect — otherwise it is recorded as a measured non-issue.

## Post-implementation note (2026-09-15, same slice)

The contract above was written before the code. One deviation from the drafting
detail, recorded for the record: G3's "new gated test file" was **not** written.
Instead the already-existing reviewed-release fixtures of
`test_canonical_decision_postgres.py` were re-run at migration head with the
evidence-only plugin `bump_revision_plugin.py`, which exercises the C2_0014
guard through *real* `human_review_resolution` payloads (the new file would have
had to fabricate the same payloads by hand — more code, weaker fixtures).
The new test added in this slice is on the Python side
(`test_identity_request_validation_indexes_assertions_by_source_once`, RED
5/33 iterations → GREEN 1).
