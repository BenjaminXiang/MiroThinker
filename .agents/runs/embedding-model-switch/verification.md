# Verification — recall-regression harness + pre-switch baseline

Slice: `feat/recall-regression` (worktree `.worktrees/recall-regression`, base `delivery-v1`
= `36df47b8`). Scope: the harness and the frozen baseline only — the embedding switch and the
index rebuild are a different slice.

## Layer ① — tests written in this slice

`apps/admin-console/tests/test_eval_recall_canonical_v2.py` — **19 hermetic tests**, no network,
no live instance. Fixtures are constructed records/streams (no transcript fixtures exist for this
surface; the realistic fixtures are the two committed case files, also asserted here).

| Cluster | Tests | Locks |
|---|---|---|
| SSE parsing | 1 | named `event:`/`data:` pairs survive an empty last line; per-lane counts reach the record |
| scoring | 3 | alias matching, whitespace/case normalisation, forbidden-entity detection, candidate-layer tri-state (`True`/`False`/`None` when unavailable), the candidate-layer name sources (handles + committed names + protected slots + web items) |
| sessions | 3 | one session per turn group (a group's follow-ups must not lose their antecedent), the serving process's 12-char debug-dump suffix rules, and the guard that rejects a `--run-id` that would collide after that truncation |
| ordering | 1 | group first-seen order preserved, turns ordered inside a group |
| aggregates | 1 | vector median/min/max over the cases that have a vector lane, citation local/web mix, candidate-layer counters |
| diff verdicts | 9 | PASS on identical input; FAIL for a labeled answer regression; FAIL for a labeled candidate-layer regression; FAIL for the >30 % median vector drop; REVIEW for a probe GT loss; REVIEW for a probe vector drop >50 % *without* a median move; REVIEW for a missing candidate layer; FAIL-by-default for concept regressions and REVIEW with `--lenient-concepts`; REVIEW on a case-set mismatch |
| committed case sets | 1 | 25 turns / 17 groups for the test set, 10–15 probes with `labeled` carrying entities and `structural` carrying none, globally unique case ids |

`cd apps/admin-console && uv run pytest tests/test_eval_recall_canonical_v2.py -q` → **19 passed**.
`uv run ruff check scripts/eval_recall_canonical_v2.py tests/test_eval_recall_canonical_v2.py` →
**All checks passed**.

## Layer ② — pre-existing suites

`uv run pytest tests/test_eval_recall_canonical_v2.py tests/test_read_turn_trace.py -q` →
**20 passed, 3 failed**. The three failures are pre-existing and unrelated (this slice adds two
new files and touches nothing else): `tests/test_read_turn_trace.py` hard-codes
`TODAY = datetime(2026, 8, 18)` while `scripts/read_turn_trace.py --date` defaults to *today* (UTC),
so those three tests only pass on 2026-08-18. Not touched, not silenced.

## Layer ③ — live evidence for the RAG-level claim

Everything below ran against the real `POST /api/chat/stream` path on the scratch instance
(port 18295, booted from the live pack — the live 18188 process was never restarted or killed).

1. Boot: `.agents/runs/embedding-model-switch/serve-18295-command.sh`, up in ~300 s,
   `/api/health` 200. Its only difference from the live command file is the port and the state
   paths (`diff` of the argument vectors: exactly one token, `18188` → `18295`).
2. Smoke 1 — one probe (`s02`): turn 8.75 s, `vector=16`, candidate layer Y, SSE lane counts
   identical to the turn-trace journal lane counts.
3. Smoke 2 — test-set group 问题1 (`q1t1`, `q1t2`): the follow-up resolved 丁文伯 → 深圳无界智航
   科技有限公司, i.e. the multi-turn session handling works and the second turn's debug dump was
   found and parsed.
4. **Baseline capture: 37/37 turns ok, 0 errors, 698.7 s** (`baseline.json`); 34/37 turns had a
   vector lane; all 37 had a candidate layer; 35/37 answers were LLM-synthesized.
5. `--diff baseline.json baseline.json` → **PASS, 0 fail-level, 0 review-level** — the diff path is
   not noisy on identical input.
6. Two real defects were found and fixed by these live runs, and locked by tests: the per-case
   session bug (follow-ups answered with no retrieval in 0.86 s) and the case-file ordering.

## Not verified / limits

* The *after-switch* direction is unverified by construction (no switched index exists yet);
  `--diff` is exercised on real and synthetic captures.
* The same-configuration noise floor (a second baseline run) was **not** captured — it would
  double the pre-switch quota spend. See `protocol.md` §7/§10; it is the one open decision.
* Recall is measured as entity presence, not rank or answer quality (`protocol.md` §9).
