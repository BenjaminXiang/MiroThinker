# Proposal: fix-web-lane-read-outer-wait

> Follow-up slice to `fix-web-lane-timeout-and-utf8-truncation` (same failure
> surface: G7 replay + waseda query). Human docs:
> `docs/plans/2026-08-28-web-lane-timeout-utf8-fix-log.md` (E2E section).

## Why

E2E after the three-chain fix left one dominant failure mode: the web lane's
72 results never reach the answer on many turns. Full chain (verified live
2026-08-28 with SSE + turn traces):

1. `knowledge_serving_isolated.py` builds `universal_web_policy` with
   `timeout_ms=bundle.web_timeout_ms` = **1 500 ms** — intended as the
   provider-search budget.
2. `knowledge_read.execute` (line ~7580) reuses that same value as the
   **outer wait for the whole web-lane future**: `future.result(timeout=1.5s)`.
3. The web lane's real workload (4 view searches × 2 providers + enumeration
   refinement round + `fetch_depth=8` page fetches + LLM gap judge) is
   designed to take 2–40 s → almost always exceeds 1.5 s.
4. On timeout the read layer records `status="unavailable", candidates=0`,
   drops ALL fetched results (the lane thread keeps running — hence turn
   traces show `web in=72 retained=72` while the evidence set has zero), and
   appends the `current_web_unavailable` limitation.
5. Downstream: `_web_lane_unavailable_from_traces` fires the outage rewrite
   on thin answers (waseda), and web-fused enumerations collapse to
   local-only lists missing the required names (G7 missing 优必选).

## What Changes

- `knowledge_read.py`: the web lane's outer wait gets a floor —
  `_WEB_LANE_OUTER_WAIT_FLOOR_SECONDS = 20.0` —
  `max(policy.timeout_ms / 1000, floor)`. 20 s covers the lane's design
  budget (2 provider rounds incl. Serper ~3 s + refinement + depth-8
  fetches + gap judge) while staying well under the 90 s chat-LLM timeout.
- No bundle change (values hash-locked); no provider change; the 1.5 s
  value continues to govern provider-level budgets where it was intended.

## Impact

- Affected code: `apps/miroflow-agent/src/data_agents/canonical_v2/
  knowledge_read.py` (one computation + constant).
- Behavior: turns whose web lane does real work now WAIT for it (progress
  events keep UX alive) instead of silently degrading to local-only at
  1.5 s. TTFT on such turns increases by the lane's real runtime (typically
  2–10 s, enumerations more) — accepted under the quality-first ruling
  (2026-08-28, user: 可以超过 30 秒，但是要有交互，然后结果质量优先).
- Non-goals: gap-judge latency, fetch-depth tuning, G3 pronoun handling
  (separate family), bundle value revision.
