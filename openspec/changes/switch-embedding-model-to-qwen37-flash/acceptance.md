# Acceptance: switch-embedding-model-to-qwen37-flash

**The acceptance is the recall gate.** Everything else on this page is a
precondition for it being meaningful: a new release whose index was built with the
candidate model, a pack sealed from the serving tree, and a scratch boot carrying
the candidate identity. Once those hold, the switch is shipped only if the
calibrated non-regression gate returns **PASS** against the frozen pre-switch
baseline **and** control; a **FAIL** blocks the cutover outright, and every
**REVIEW** row needs a recorded human decision. Nothing else — not the 4× smaller
index, not the removed GPU dependency — substitutes for that verdict.

## Gate commands (verbatim from `.agents/runs/embedding-model-switch/protocol.md` §3)

```bash
# warm-up pass — fills the web cache, DISCARDED
cd apps/admin-console && UV_OFFLINE=1 uv run python scripts/eval_recall_canonical_v2.py \
  --base-url <switched-instance> --label after-warmup \
  --cases ../../.agents/runs/embedding-model-switch/testset-cases.json \
          ../../.agents/runs/embedding-model-switch/semantic-probes.json \
  --turn-debug-dir <instance CANONICAL_V2_TURN_DEBUG_DIR> \
  --turn-trace-dir <instance TURN_TRACE_DIR> \
  --out /tmp/after-warmup.json

# judged pass
cd apps/admin-console && UV_OFFLINE=1 uv run python scripts/eval_recall_canonical_v2.py \
  --base-url <switched-instance> --label after-qwen37-flash-1024 \
  --cases ../../.agents/runs/embedding-model-switch/testset-cases.json \
          ../../.agents/runs/embedding-model-switch/semantic-probes.json \
  --turn-debug-dir <instance CANONICAL_V2_TURN_DEBUG_DIR> \
  --turn-trace-dir <instance TURN_TRACE_DIR> \
  --out .agents/runs/embedding-model-switch/after.json

# verdicts (exit codes: 0 PASS, 1 FAIL, 2 REVIEW)
cd apps/admin-console && uv run python scripts/eval_recall_canonical_v2.py \
  --diff .agents/runs/embedding-model-switch/baseline.json after.json
cd apps/admin-console && uv run python scripts/eval_recall_canonical_v2.py \
  --diff .agents/runs/embedding-model-switch/control.json after.json
```

Scratch boot recipe (the live 18188 line is never touched):
`serve-18295-command.sh` with only the port and the state paths rebased, plus
`CANONICAL_V2_TURN_DEBUG_DIR` / `TURN_TRACE_DIR` (the baseline recipe did not set
them; the switched run must, or the gate degrades to a coverage REVIEW).

## Frozen gate artifacts (verify before trusting any verdict)

| Artifact | sha256 |
|---|---|
| `baseline.json` (pre-switch, 4096-dim, 37/37 turns) | `7af37a34e57f5fe9f500d1d7810911a1cb7067fa651b27b8ad6867a8b51f99a2` |
| `control.json` (second pre-switch capture = the noise floor) | `54a695ac72c0f8e708ecfde70e2e82b60b148b786a2a3dc1b326f23f8eeb4330` |
| `protocol.md` (verdict rules after calibration) | `dcb3beb69d58f64967d1cb1e161b67d3811c84919cbf9d5adc2867f272101bb0` |
| `noise-floor.md` (measured noise, rule provenance) | `03a943aa6ed0031428f4d7c3d6ebd3221cd7119f831785bf5b603e843e744c51` |
| `testset-cases.json` (25 turns / 17 groups) | `7dd0113f804668ea183ded2802836946daaa4819486456fe8ce8dca3815d7999` |
| `semantic-probes.json` (12 vector-lane probes) | `2093dba97ecc28af9692fc7c39e0263ac46b4bdfb90389a926e307df49f44594` |
| `apps/admin-console/scripts/eval_recall_canonical_v2.py` (harness) | `ed80f818d4f902b3d5044e42910f046fbd6b9ca8ceb395f39386295c123b0e70` |

If any of these bytes changed, the calibration is invalidated and the gate must be
re-argued before it can block or pass a cutover.

## Criteria

| # | Criterion (counts as fixed) | Evidence required | Status |
|---|---|---|---|
| A1 | The candidate identity is frozen and inert on the lane: bundle self-hash == constant; crossed `(hash, dimension)` pairs refused; the pre-switch path untouched | slice 1+2 tests (`test_embedding_model_switch_v2.py`, 31 passed) + the real pack/index refusal test | met (slice 1+2) |
| A2 | The route question is answered with a real call: the compatible route serves the flash model | one authenticated probe: HTTP 200, 1024 dims, 0.311 s (2026-09-21); reproducible by `precheck.sh` | met |
| A3 | The switch line builds and serves from one tree, with F1/F2 applied to both new authorities | T2.1 merge + T2.4/T2.5 tests green in the merged tree | pending |
| A4 | The new release's index was built with the candidate model (policy, matrix meta, pack manifest, serving bundle all agree; 1024 dims; point count unchanged) | T5.3/T5.4/T6.1/T6.3 outputs | pending |
| A5 | The new pack boots on the fast path with the new marker/manifest identity | mount receipt `verification: receipt`, `mount_seconds` in the ~120 s class | pending |
| A6 | **Recall did not regress** (plan §4.4 / `protocol.md` §6): `baseline ↔ after` and `control ↔ after` both PASS, with every REVIEW row decided and recorded | `after.json` + both `--diff` outputs + the decision log (T7.4–T7.6) | pending |
| A7 | The gate was captured under the calibrated conditions: driven twice, second pass judged, debug + trace dirs enabled, web-timeout counts reported | T7.1–T7.3 command lines + the harness aggregate block | pending |
| A8 | The switch changes the embedding identity only: same source manifest, same restore root, object counts/relationships unchanged | T6.4 comparison against the pre-switch release | pending |
| A9 | Cutover is reversible and was drilled: previous command file restored → pre-switch identity served; new artifacts byte-identical after the drill | T8.3 receipt/health output for both directions | pending |
| A10 | The gateway credential lives in its own slot and appears nowhere in artifacts or logs | `precheck.sh` output (`SET` for the slot; no key material found) + the command-file inspection | pending |
| A11 | The credential(s) exposed in cleartext before this change are rotated | operator record (T3.2) | pending |
| A12 | Sizes and latency recorded (index ≈420 MB vs 1.68 GB; per-query embedding ≈0.28–0.31 s) | T8.4 measurements | pending |

## Out of scope (explicitly not accepted here)

- Rank quality inside the vector top-k, answer precision and multi-turn
  referent resolution — `protocol.md` §6/§9 states the harness cannot judge them.
- The third-party gateway's retention/stability commitments (operator decision).
- Deployment automation, systemd units or ports: the cutover is the documented
  operator restart.
- The human-side plan/index/log documents (`docs/plans/`, owned by the orchestrator).
