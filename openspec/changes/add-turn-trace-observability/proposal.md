# Proposal: add-turn-trace-observability

> Phase 1 of Epic `fix-round-1-serving-pipeline` (drafted 2026-08-18, authorized
> by the user; awaiting review before any production-code edits).
> Human docs (Chinese, authoritative narrative), per AGENTS.md §3:
> plan `docs/plans/2026-08-17-systematic-fix-round-1.md` ·
> log `docs/plans/2026-08-17-systematic-fix-round-1-log.md`.
> Behavior-affecting: YES (web-lane failure-path behavior + additive trace).
> Capability: `canonical-v2-chat`.

## Why

Two verified gaps block every later phase of fix round 1:

1. **Observability is effectively zero.** The serving stack has ~7 logger calls
   total; the existing `AccessLogStore` records only turn outputs (query, answer
   text, citations, latency). Lane counts, gate drops, web-provider attempts,
   anchor decisions, and degradation reasons are invisible — failures cannot be
   attributed to a stage. Every phase P2–P8 needs per-stage attribution to
   verify its fix.
2. **The web lane has no resilience.** Verified 2026-08-17:
   `_DualWebLaneAdapter._search_provider` swallows all provider exceptions
   (`except Exception: return []`), there is no retry, no result cache, no
   circuit breaker, and no quota accounting. A channel outage silently zeroes
   the lane and the answer degrades with no trace — the G2 incident form
   (channel outage phrased as "未找到该机构").

## What Changes

- **Turn trace (Epic 1.1)**: one structured `TurnTrace` per turn — session
  snapshot (ordinal, active anchor, displayed ids), interpretation inputs and
  outputs (query frame, subject candidates), per-lane in/out/filtered counts,
  gate drop counts, web fetch outcomes (per provider: attempt/timeout/error/
  cache-hit), degradation reason, final answer subject. Stored as append-only
  JSONL journals with a reader CLI.
- **Trace verified by replay (Epic 1.2)**: replaying the frozen baseline
  sessions, each failure's stage must be readable from the trace alone.
- **Web-lane resilience (Epic 1.3)**: single retry with backoff per provider per
  query view (search is idempotent); web-result cache keyed by normalized view +
  day (port of the legacy V017 `web_search_cache` pattern); per-provider health
  circuit-breaker (consecutive-failure open, probe recovery, preference bias);
  quota-watermark counters; keepwarm loop must respect the watermark and breaker
  state. All resilience events are recorded in the trace.
- Scope boundary: answer WORDING on lane failure ("通道不可用 ≠ 世界没有") is
  owned by Phase 2 (`enforce-never-refuse-contracts` §2.2), not here. This
  change makes failure-path behavior resilient and visible, not yet reworded.

## Impact

- `apps/admin-console/backend/services/canonical_v2_chat.py` — turn-boundary
  trace hook (session snapshot, interpretation, answer subject).
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_serving_isolated.py`
  — lane/gate/web-outcome trace callbacks; `_DualWebLaneAdapter` resilience
  (retry, cache, breaker, quota counters).
- `apps/admin-console/backend/api/canonical_v2_chat.py` — turn-trace store
  wiring alongside the existing access-log store.
- New: turn-trace journal store + `apps/admin-console/scripts/` reader tool.
- No change to: serving pack format, classification A–G semantics, answer
  generation on the healthy path, session cookie semantics.
