# Design: add-turn-trace-observability

## Grounding (code recon 2026-08-18)

- Turn entry: `backend/api/canonical_v2_chat.py` (`/chat`, `/chat/stream`,
  `/chat/session/reset`) → `backend/services/canonical_v2_chat.py`
  `answer()/answer_stream() → _answer_locked()` (holds session lock, session
  state: active anchor, referent history, displayed ids).
- Serving: `canonical_v2/knowledge_serving_isolated.py` (5736 lines) — query
  views (`_serving_query_views`), `_DualWebLaneAdapter` (dual provider submit,
  `except Exception: return []` per provider at `_search_provider`,
  `ThreadPoolExecutor(8)`), gates (`_apply_web_subject_consistency`,
  eligibility), prose renderers.
- Existing output-level observability: `AccessLogStore.record_turn`
  (`AccessLogTurnRecord`: query/answer/citations/latency, best-effort, silent
  failures). No stage-level data anywhere. Keepwarm loop runs 2 real searches
  every 300 s idle via `canonical_v2_keepwarm.py`.

## TurnTrace record (additive, Pydantic)

One record per turn, written at turn end (and finalized on error):

```text
trace_id, session_id, turn_ordinal, ts_start, ts_end
query_raw, question_frame, inferred_domains, subject_candidates[]
session_snapshot: active_anchor{id,name}, displayed_id_count, referent_hint
lanes: {local: {in, retained, filtered}, web: {in, retained, filtered}}
gate_drops: {<gate_name>: <count>}          # e.g. web_subject_consistency
web_outcomes: [{provider, view, attempted, errored, timed_out, retried,
                cache_hit, breaker_state_before, breaker_state_after}]
degradation: none | web-lane-unavailable | no-local-evidence |
              subject-gate-empty | clarification | error
answer_subject, citation_count, status(ok|degraded|error), error_detail?
```

Filled via a `TurnTraceCollector` (context object) passed down as an optional
argument — serving-layer functions accept an optional collector and report
lane/gate/web events; absence of a collector must be a no-op so isolated build
paths (and tests) are untouched. The service constructs the collector in
`_answer_locked`, attaches the session snapshot, and emits the record to the
journal on exit.

## Journal store + reader

- Storage: append-only JSONL, one file per UTC day, under
  `var/turn-trace/YYYY-MM-DD.jsonl` relative to the backend working dir
  (configurable via env `TURN_TRACE_DIR`). Retention: keep 14 days, prune on
  write (configurable `TURN_TRACE_RETENTION_DAYS`).
- Writer failures are recorded in the application logger but NEVER fail a turn
  (same best-effort contract as AccessLogStore, but counted — a writer failure
  must not be silent forever).
- Reader: `apps/admin-console/scripts/read_turn_trace.py` — filters
  `--session`, `--degradation`, `--status`, `--date`; default one line per turn;
  `--expand <trace_id>` prints the full record. Line-streaming only.

## Web-lane resilience (inside `_DualWebLaneAdapter`)

1. **Retry**: one retry per provider per view with 250 ms backoff, only on
   transport errors/timeouts — not on auth/quota errors (pointless).
2. **Cache**: SQLite file `var/turn-trace/web_cache.sqlite`, table
   `(provider, view_key, day, payload_json, fetched_at)`, PK
   `(provider, view_key, day)`; `view_key = sha256(normalized view text)`;
   day = UTC date. Port of the legacy V017 `web_search_cache` pattern. TTL =
   the day boundary itself (no intra-day expiry). Cache read/write failures
   degrade to no-cache behavior and are traced.
3. **Circuit breaker** (per provider, in-memory, seeded CLOSED): open after
   3 consecutive failures; probe after 60 s cooldown with one real request;
   close on probe success. While OPEN: skip the provider's submissions entirely
   (thread-pool pressure and deadline budget saved), lane served by the healthy
   provider or cache. State transitions are traced. Sticky Serper disable
   ("not enough credits") maps to OPEN-with-reason and is NOT permanent —
   probe recovery replaces it (removes today's process-lifetime sticky
   disable).
4. **Quota watermark**: per-provider per-day request counters in the same
   SQLite; default watermark (env `WEB_LANE_DAILY_QUOTA`, default 4000/provider
   from Bocha/Serper plan headroom). Above watermark: keepwarm skips the
   provider; user-turn searches still proceed (availability first) but the
   event is traced. Keepwarm loop consults breaker state + counters before
   firing.

## Deliberate non-goals

- No answer-text changes on degradation (Phase 2.2 owns wording).
- No changes to healthy-path retrieval semantics, gates, or ranking.
- No distributed tracing / OpenTelemetry: JSONL + CLI only (boring,
  agent-legible, zero new deps).
- No serving-pack format change; no new heavy dependencies.

## Risks

- Trace volume: bounded by turns/day; JSONL + 14-day retention keeps disk
  trivial. Reader streams line-by-line.
- Adapter test surface: resilience logic is unit-testable with injected
  provider fakes (deterministic); fault-injection acceptance covers the wiring.
- Thread-safety: collector events may arrive from lane threads — collector uses
  a lock and append-only dicts; breaker/counters are lock-guarded.
