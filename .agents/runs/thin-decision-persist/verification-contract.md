# Verification contract: thin-decision-persist (Stage 2)

Written BEFORE production edits.

## Behavior under test

B1 (column verification): persist reads back written tables as raw tuples
and compares multisets; a tampered row (post-persist external UPDATE then
replay-persist) MUST raise the replay-conflict error naming evidence.

B2 (idempotent replay): a second persist of an identical batch returns
without invoking the full `_load_result` rebuild (spy) and returns a result
equal to the input.

B3 (round-trip): persist→load still produces an object equal to the input
(existing 46-test PG file is the net; must stay green).

B4 (supersession): existing supersession error tests (new root for existing
lineage; wrong head; already-superseded) still raise — via the set-based
implementation.

B5 (canary): post-commit rebuild check runs on a bounded sample by default;
`CANONICAL_V2_DECISION_REBUILD_CHECK=off` disables; `full` restores the
old always-full behavior.

B6 (performance, informational): synthetic batch (2k decisions with
assertions/outcomes/roles) persist wall time before vs after — expect an
order-of-magnitude-plus drop driven by the removed per-decision recursive
CTEs; recorded, not asserted as a hard gate (machine-dependent).

## Test levels

L1: PG-backed unit tests in `test_thin_decision_persist.py` (same
CANONICAL_V2_TEST_* env gating as the existing decision PG tests):
- replay equal → returns without full load (spy on `_load_result`)
- tampered replay → raises replay conflict
- canary default on; off env honored
L2: full `test_canonical_decision_postgres.py` (46 tests) stays green —
covers B3/B4 through existing fixtures.
L3: timing script comparing persist wall time pre/post on a synthetic
batch; numbers recorded in verification.md.

## Fix surface

`apps/miroflow-agent/src/data_agents/canonical_v2/canonical_decision_postgres.py`
(persist, _require_exact_supersession_heads, new raw-tuple helpers).

## Rollback

Single-commit revert restores the audit-grade path (and its known
no-completion-path behavior at full volume).
