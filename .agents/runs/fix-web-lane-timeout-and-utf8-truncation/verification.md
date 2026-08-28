# Verification Evidence: fix-web-lane-timeout-and-utf8-truncation

Verification contract: `verification-contract.md` (written before edits).

## Unit level (GREEN)

- Agent app — `uv run pytest tests/canonical_v2/test_web_snapshot_utf8_truncation.py
  tests/canonical_v2/test_dual_web_lane_provider_timeouts.py` → **9/9**.
  - utf8 truncation: old byte-slice crash locked as documented regression;
    `_utf8_truncated` decodable at every cap 1..119 + 16383/16384/16385 +
    len-1; prefix-preserving; 16 384-cap contract round-trip survives.
  - timeouts: main lane bocha 2.0 s / serper 4.0 s; probe lane 2.7/4.0;
    outer waits 2.5/4.5; explicit providers not overridden.
- Admin console — `uv run pytest tests/test_canonical_v2_budget_degradation_grading.py`
  → **5/5**: within-budget None; wall-time-only → "wall_time" (kept);
  provider_calls / cost / retry overruns → "resource" (stripped).

## Regression (no new failures)

- `tests/canonical_v2/test_knowledge_serving_isolated.py`: 236 pass,
  1 pre-existing fail (prose-renderer prompt wording, fails at HEAD).
- `tests/canonical_v2/test_serving_supplemental_person_criteria.py` +
  `test_ambiguity_gate_serving.py` + `test_ambiguity_switch_execution.py` +
  `test_web_lane_resilience.py`: 71 pass, 0 fail.
- `tests/canonical_v2/test_llm_query_rewrite.py`: 31 pass, 2 pre-existing
  fail at HEAD (enumeration-refinement view drift).
- Admin `tests/test_canonical_v2_chat_http_adapter.py`: 96 pass / 37 fail —
  identical 37 fail at HEAD (stash roundtrip: 91 pass / 37 fail pre-change).
- One legacy assertion updated (old 0.675 s timeout → new Serper floor 4.0 s)
  in `test_dual_web_lane_reuses_request_transport_...`.

## Live replay (18188 restarted with the fix, 2026-08-28)

Raw: `/tmp/live-replay-after-fix.json`; traces `var/turn-trace/2026-08-28.jsonl`.

| Query | Result |
|---|---|
| waseda ×3 | PASS 12.7 s / PASS 12.4 s / OUTAGE 25.3 s (cold-cache first turn) |
| CN117873146A | PASS 7.1 s |
| 优必选专利 | PASS 13.7 s (2/2 kp) |
| 华力创 | PASS 6.8 s (2/2 kp) |
| PCB 打板 | PASS 16.3 s |

- internal_error: **0/3** (crash chain eliminated; was 5/8 historically).
- Waseda keypoints (早稻田|许晋诚|帕西尼): **2/3**, first-ever correct answers
  on this stack (“…企业家主要有帕西尼创始人许晋诚”).
- Grading fix observed live: log line `supplemental budget wall-time overrun —
  keeping late web evidence (elapsed_ms=12204 …)`.
- Residual (documented, not this slice): cold-cache first turn trace
  `f-xa59Ap` — web lane in=71 all cache-hit, breaker closed, no strip
  warning, yet SSE reported web=0 and outage wording fired; drop happens in
  the read-layer merge/sufficiency path.

## E2E (2026-08-28, post-fix, 18188)

**Test set (16 questions, `run_testset.py`)**: 16/16 answered, 0
self-narration. Single-turn 11/12 — the only miss is the waseda query
(outage wording, same read-layer residual; trace shows web in=71, 12 cache
hits + 2 fresh, zero errors). Notable: 酒店送餐机器人 went EMPTY → 2/2 PASS
(the fix also unblocked this enumeration query). Multi-turn questions
(4) fail without session context — script limitation, unchanged.

**Official replay gate (`replay_fix_round1.py`, 7 sessions)**: 17/19.
- G3 person-pronoun T2 fail (P4-family multi-turn pronoun, pre-existing).
- G7 enumeration: first run 2/3 pass; `--only G7` rerun 3/3 FAIL
  (优必选 missing). All 7 G7 traces today show web lane in=72 retained=72,
  zero errors/timeouts — failing turns simply delivered 0 web items to the
  answer (local-only 594-char list vs 1023-char web-fused list on passes).
  Same read-layer drop family as the waseda residual; PRE-EXISTING (the
  pre-fix 09:43 waseda trace already showed in=71 + outage answer), exposed
  now that the three fixed chains no longer mask it.

**Gate implication**: replay gate is NOT green (G7 flaky-to-red) → no hot
update to `release/customer-test` from this state; read-layer drop is the
blocking gap for the next slice.
