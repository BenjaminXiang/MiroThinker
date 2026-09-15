# Verification — reduce-rebuild-validation-cost step 1 (trigger / validator hot paths)

Slice branch: `perf/rebuild-trigger-fix` (base `data/p4-serving-pack-rebuild`
@ `1ee824a7`). Change: `openspec/changes/reduce-rebuild-validation-cost`.
Contract: `verification-contract.md` (written before the production edits).

All measurements were taken on **copies**:
`miroflow_tgfix_probe` = `CREATE DATABASE miroflow_tgfix_probe TEMPLATE
miroflow_candidate_v2_20260913_r1` (5.8 GB, the run15 candidate). The live
serving database and `/var/tmp/mirothinker-data-v2/` were never written.

## 1. Sibling sweep (tasks 1.1)

`measure_trigger_commit.py` mounts each **real** validator function on a scratch
table that only carries the columns the function reads from `NEW`, then times a
deferred `COMMIT` of N inserted rows. It never writes to the measured tables, so
the measured work is exactly the function body plus PostgreSQL's deferred-event
dispatch.

| # | validator (mount tables) | events at run15 scale | before | after | verdict |
|---|---|---|---|---|---|
| 1 | `validate_field_human_review_binding`, branch ① (`canonical_decision_assertion`) | 846,986 | **41,900 µs/row** (≈9.9 h) | **28.7 µs/row** (≈24 s) | fixed |
| 2 | same function, decision mount (`canonical_decision`) | 423,493 | 46 µs/row | 22 µs/row | fixed |
| 3 | `validate_relationship_human_review_binding`, branch ① | 21,546 | 2,086 µs/row | 26 µs/row | fixed |
| 4 | `validate_identity_human_review_binding` (9 mounts) | ≈532,000 | 6,083 µs/row | 22 µs/row | fixed |
| 5 | `validate_field_temporal_binding` (2 mounts) | 1,270,479 | 153 µs/row (≈54 min) | 159 µs/row | same-cost: index already used; residual is the selected-evidence join, not a scan of the decision table |
| 6 | `validate_identity_resolution_release` (14 mounts) | ≈500,000 | 1,647,000 µs/row | unchanged | **different disease** — release-level topology re-derived per row; see §5 |
| 7 | `validate_domain_inclusion_assertion_owner` | 424,440 | 1.67 µs/row | 1.5 µs/row | **not the disease** (already index-backed; the analysis' sibling guess is measured and answered) |

Raw data: `sweep-run15.json` (catalog sweep: 36 deferred row-level mounts on 20
tables), `measure-before-after.jsonl`.

## 2. EXPLAIN ANALYZE before / after (`explain-analyze-before.txt`, `explain-analyze-after.txt`)

| predicate (verbatim from the validator) | before | after | plan change |
|---|---|---|---|
| field branch ① `EXISTS (… method='human_review' AND case.release_id=… AND case.originating_record_id=…)` | **43.061 ms** | **0.015 ms** (2,870×) | `Gather → Parallel Seq Scan` (141,164 rows removed × 3 workers) → `Index Scan` |
| release-level guard term (same predicate minus the record id) | 42.651 ms | 0.007 ms | same |
| relationship branch ① | 4.807 ms | 0.008 ms (600×) | `Seq Scan` → `Index Scan` |
| identity first `EXISTS` (3-table LEFT JOIN) | 7.717 ms | 0.038 ms (203×) | `Seq Scan on identity_decision` (47,068 rows) → `Index Scan on ix_knowledge_identity_decision_human_review` |
| domain-inclusion owner lookup | 0.024 ms | 0.023 ms | unchanged, already `pk_knowledge_current_source_identity_assignment` |
| field temporal decision probe | 0.052 ms | 0.051 ms | unchanged, already index-backed |

## 3. Which part pays? (guard vs index)

Dropping the six indexes while keeping the guarded functions (state
`guard-only`) reproduces the original per-row cost: field 42,884 µs/row,
identity 6,328 µs/row, relationship 2,107 µs/row — i.e. **the index is the
load-bearing part**; the guard alone changes nothing. The guard's value is
robustness and legibility, and it is the mechanism the change contract asked
for; the design document records this honestly rather than pretending the guard
is the win.

## 4. Projected effect at run15 scale (deferred `COMMIT`)

| mount | events | before | after |
|---|---|---|---|
| `canonical_decision_assertion` (field + relationship + identity + temporal) | 846,986 | 846,986 × 41.9 ms ≈ **9.9 h** (run15 measured 12 h 40 m end-to-end for this commit) | ≈ 24 s |
| `canonical_decision` (field + temporal) | 423,493 | ≈ 25 min | ≈ 10 s |
| identity tables (9 mounts × 6 families of identity validators) | ≈ 500k | ≈ 1 h | ≈ 20 s |

The run16 rebuild re-measures the real phase; no full rebuild was run in this
slice.

## 5. Sibling recorded, not fixed (different disease)

`validate_identity_resolution_release` is mounted on 14 tables and re-validates
the release-wide identity topology (identity decisions, lineage, memberships,
output allocations) for **every inserted row**: 1.65 s/event on the run15 copy,
≈500k events. If that per-event cost held in the real pipeline the identity
phase alone would exceed the whole run15 wall clock, and the run15 phase
timestamps (`identity_resolution_run` 02:28 +0800 → `relationship_projection_run`
18:55 +0800, with the decision `COMMIT` inside that window) do not leave room for
it, so the probe is **not proven faithful** for this family — the real insert
window may see partially-empty tables. It is recorded as the largest open
structural risk (per-row re-derivation of a release-level fact) and needs
in-pipeline instrumentation during run16 before any fix is designed. It is
*not* an index problem: no index removes the per-row re-derivation.

`validate_field_temporal_binding` (1.27 M events, 153 µs/row ⇒ ≈54 min) also
re-derives work per row; the probe shows its index-backed part is already cheap.
It is a candidate for the same granularity workstream as §5, not for another
index.

## 6. Behaviour equivalence

- `tests/canonical_v2/test_canonical_decision_postgres.py` (reviewed-release
  fixtures built by the engine, i.e. real `human_review_resolution` payloads)
  was re-run **at migration head** with the evidence-only plugin
  `bump_revision_plugin.py` (`EXPECTED_REVISION` → `C2_0014`), which is the only
  way those fixtures exercise the new function bodies:
  `pytest-head-revision.txt` = **98 passed, 2 failed**.
- Both failures are **pre-existing revision-pin artifacts**, not C2_0014
  regressions: re-running the same two tests with the pin set to **C2_0013**
  (one revision before this change) fails identically
  (`pytest-pin-isolation.txt`), while at the file's own pin (`C2_0008`) the full
  suite is green. Cause: those two tests assert surfaces that any higher
  revision changes — `test_missing_parents_…` asserts the exact set of
  `current_*` tables (C2_0009/C2_0010 add more), and
  `test_store_and_c2_0007_downgrade_share_release_first_lock_order` asserts a
  55000 refusal during a concurrent downgrade whose lock footprint grows with
  every intervening revision (observed `40P01` deadlock).
- The review-provenance subset is green at head, including
  `test_direct_sql_review_rows_reject_null_hash_and_relational_cross_wiring[field]`
  (origin-evidence immutability → `23514`) and
  `test_concurrent_late_origin_edge_and_review_cannot_both_commit[field|relationship]`.
- The `guard-only` and `after` scratch measurements show the *skip* path
  committing 100/2,000 rows without rejection, and the before/after plans show
  the same predicate evaluated (index access) rather than a weakened predicate.
- `check_function_bodies.py` proves the installed bodies are the C2_0007 bodies
  plus the guard, token-for-token (whitespace-normalised), and that
  `alembic downgrade C2_0013` restores the C2_0007 bodies exactly.

## 7. Migration reversibility

`alembic upgrade C2_0014` on the copy: 1.5 s.
`alembic downgrade C2_0013`: bodies back to baseline (`check_function_bodies.py
… baseline` → PASS), indexes dropped, per-row cost back to 40,438 µs/row
(±4 % of the original baseline). `alembic upgrade C2_0014` again → guarded
bodies (PASS). No historical migration was rewritten; C2_0014 adds six indexes
and replaces three functions.

## 8. Python side (`canonical_identity_resolution.py`)

See `python-scan-before-after.md`: the assertion tuple is iterated once per
validation instead of once per source (RED: 5 iterations at 4 sources, 33 at 32;
GREEN: 1). Grouping in `validate_request` is a single pass
(`assertion_ids_by_source`), and `_has_evidence_bound_internal_identifier` now
takes a `(source_id, field_path)` index built once per entry point.
All 58 identity-resolution contract tests pass.
