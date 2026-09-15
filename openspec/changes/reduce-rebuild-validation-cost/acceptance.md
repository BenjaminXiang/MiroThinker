# Acceptance: reduce-rebuild-validation-cost

Evidence root: `.agents/runs/reduce-rebuild-validation-cost/`
(`verification.md` indexes every artefact). Step 1 is implemented on
`perf/rebuild-trigger-fix`; step 2 has not started.

| # | Criterion (counts as fixed) | Evidence required | Status |
|---|---|---|---|
| A1 | Decision-batch `COMMIT` drops from **~12h40m to minutes** on identical input | before/after phase timings + identical row counts | **candidate** — copy-DB measurement: assertion-branch 846,986 rows × 41,900 µs/row → 28.7 µs/row (≈9.9 h → ≈24 s) plus the decision/time mounts; **run16 records the real phase timing** |
| A2 | Identity-resolution phase drops from hours to minutes | before/after phase timings | **partial** — Python per-entity scans fixed and pinned by a RED/GREEN test (time benchmark 1.17×/1.53×/1.95× at 500/2,000/10,000 sources, `cProfile` residual is pydantic revalidation); DB-side identity validators 6,083 → 22 µs/row; pipeline phase timing pending run16 |
| A3 | The release authority is no longer parsed + canonicalised three times per release | sealer phase table before/after | pending (step 2, not in this slice) |
| A4 | Identical inputs produce a **byte-comparable envelope** (or equal projection digests + row counts) | diff / digest artefact | pending (step 2). Step-1 equivalence is argued at predicate level instead: identical predicates, identical error codes/messages, byte-identical bodies modulo the guard (`check_function_bodies.py`) |
| A5 | Reviewed-field immutability still rejects (ERRCODE 23514) | new regression test, RED before / GREEN after | **satisfied** — `test_canonical_decision_postgres.py` reviewed-release fixtures re-run at migration head (`pytest-head-revision.txt`): 7/7 review-provenance tests pass, including origin-evidence immutability and the late-edge race; Python side pinned by a new RED/GREEN test |
| A6 | `apps/miroflow-agent` canonical_v2 suites green **and** one full rebuild passes end-to-end | suite output + envelope receipt | **partial** — Python suites green (60 identity-contract + 46 decision-postgres at the pinned revision); 4 PG-gated suites at head: 98 passed / 2 pre-existing revision-pin failures (isolation evidence in `pytest-pin-isolation.txt`: both fail at C2_0013 too). Full rebuild pending run16 |
| A7 | No fail-closed validator was weakened, deleted, or bypassed | reviewer checklist against §12.5 / §13.5 | **satisfied** — no trigger removed or re-scoped, no deferral mode changed, every `RAISE … 23514` and its predicate byte-identical; the guard's early return is a *necessary-condition* short-circuit for every rejection branch (argued per function in design.md), and the with-reviews rejection path is re-verified at head |

## Out of scope

Served data, release contents, the serving-pack contract, and query
classification A–G semantics. No migration is rewritten; C2_0014 upgrades and
downgrades cleanly (`verification.md` §7).

## Follow-ups (recorded, not accepted here)

- F1 `validate_identity_resolution_release`: per-row re-derivation of a
  release-level fact (probe 1.65 s/event; not proven faithful against run15's
  phase timestamps). Instrument in run16 before designing a fix.
- F2 `validate_field_temporal_binding`: 1.27 M events at 153 µs/row (≈54 min),
  index-backed parts already cheap — same granularity workstream as F1.
- F3 The two revision-pinned tests in `test_canonical_decision_postgres.py`
  (`EXPECTED_REVISION = "C2_0008"`) fail at any revision above C2_0008; bumping
  that pin (and fixing those two assumptions) belongs to whoever advances the
  migration head.
