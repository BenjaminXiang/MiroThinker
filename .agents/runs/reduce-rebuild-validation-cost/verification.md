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
| 6 | `validate_identity_resolution_release` (14 mounts) | ≈704,760 | 1,647,000 µs/row | unchanged | **different disease** — release-level topology re-derived per row; see §5 |
| 7 | `validate_domain_inclusion_assertion_owner` | 424,440 | 1.67 µs/row | 1.5 µs/row | **not the disease** (already index-backed; the analysis' sibling guess is measured and answered) |
| 8 | `validate_identity_action_allocation` (5 mounts) | ≈188,000 | 183 µs/row | 183 µs/row | same class as #5: index-backed, residual is per-row re-derivation |
| 9 | `validate_current_relationship_decision` (1 mount) | 10,897 | 72 µs/row | 72 µs/row | negligible |

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

Sum of every deferred row-level validator on the decision-batch tables
(measured µs/row × run15 event counts from `sweep-run15.json`):

| mount table | events | before | after C2_0014 |
|---|---|---|---|
| `canonical_decision_assertion` — review binding ① | 846,986 | **9.86 h** | **24.3 s** |
| `canonical_decision_assertion` — temporal | 846,986 | 129.6 s | 134.7 s (unchanged mechanism) |
| `canonical_decision` — review binding | 423,493 | 19.5 s | 9.3 s |
| `canonical_decision` — temporal | 423,493 | 64.8 s | 67.3 s |
| `relationship_decision_assertion` — review binding ① + temporal | 21,546 | 48.2 s | 4.0 s |
| identity tables — review binding (9 mounts) | 532,708 | **54.0 min** | **11.7 s** |
| identity tables — action allocation (5 mounts) | ≈188,000 | 34.4 s | 34.4 s |
| `current_relationship_projection` | 10,897 | 0.8 s | 0.8 s |
| **decision batch total (excl. the unproven #6)** | | **≈11.1 h** (run15 measured 12 h 40 m once worker start-up is included) | **≈4.0 min** |

Honest reading: the 12 h 40 m collapses to **≈4 min**, and ~3.4 min of that
residual is the *temporal* validator family (#5) plus ~34 s of identity action
allocation (#8) — both index-backed already, both candidates for the granularity
workstream (F2), not for another index. The projected numbers are copy-DB
measurements extrapolated linearly; **run16 must record the real phase timing**.

## 5. Sibling recorded, not fixed (different disease)

`validate_identity_resolution_release` is mounted on 14 tables and re-validates
the release-wide identity topology (identity decisions, lineage, memberships,
output allocations) for **every inserted row**: 1.65 s/event on the run15 copy,
≈704,760 events. If that per-event cost held in the real pipeline the identity
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

See `python-scan-before-after.md` and `bench-identity-validation.txt`:

- iteration counts (RED/GREEN): the assertion tuple is iterated once per
  validation instead of once per source — **5 iterations at 4 sources / 33 at 32
  before, 1 after** (new gated test, `test_identity_request_validation_…`);
- time: `validate_identity_resolution_result` on 500 / 2,000 / 10,000 sources is
  **1.17× / 1.53× / 1.95×** faster (the removed work is the per-source rescan);
- same-shape siblings swept: per-verdict re-filtering of all assertions and all
  sources in `validate_identity_resolution_result` replaced by a pre-built
  `source_id → assertion_ids` map plus a positional order index (run15: 491
  verdicts × 620,798 assertions ≈ 3×10⁸ element tests removed; ordering preserved
  exactly so component hashes are unchanged);
- `cProfile` after the change shows the residual is pydantic revalidation / JSON
  encoding / `_require_unique`, not scanning.
- All 60 identity-resolution contract tests pass (58 pre-existing + 2 new
  parametrised cases).

## 9. Merge integration + head-pin guard (2026-09-15, data-line merge)

F3 was integrated into the data launch line (`data/p4-serving-pack-rebuild`)
together with D0-a/D0-b and C1. The integration check found the migration had
been added **without** moving `_EXPECTED_ALEMBIC_REVISION` (still `C2_0013`).

Why it mattered: the launcher (`build-run15.sh`, template for run16) migrates
the fresh candidate database with `alembic upgrade head` (now `C2_0014`), and
`_RealBoundary.validate_fresh_targets` → `_assert_fresh_database` asserts
**exact equality** with the constant. The run16 build would therefore abort
with "candidate database migration revision differs from the live single head"
before doing any work.

Fix + guard (`10b646ac`):

- `_EXPECTED_ALEMBIC_REVISION` `C2_0013` → `C2_0014`;
- new `tests/canonical_v2/test_canonical_revision.py::test_build_expected_revision_matches_the_migration_head`
  pins the constant to the loaded migration head — RED before the bump, GREEN
  after (file 8 passed).

Cross-line checks in the merged tree: 6 targeted files (publication cleaning
batch2, applicant-binding relationship seeds, patent↔company binding
reconciliation, identity-resolution contract, patent applicant linking,
publication cleaning batch1) = **168 passed**; `test_canonical_revision.py` =
8 passed. The PG-gated suites upgrade to their own pinned revision (not head),
so the bump does not touch them. Pre-existing red unchanged:
`test_knowledge_build_isolated.py` fixtures mock `C2_0012` (12-failure class),
`F402` lint in `knowledge_build_isolated.py` (present since `5078678b`).
