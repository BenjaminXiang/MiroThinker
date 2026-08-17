# Tasks: add-turn-trace-observability

Slices are independently testable; do not start a slice before the previous one
reaches Candidate. RED definitions live in
`.agents/runs/add-turn-trace-observability/verification-contract.md`.

## 1.1 Turn trace

- [x] 1.1.1 `TurnTrace` Pydantic model + `TurnTraceCollector` (thread-safe,
       optional-pass, no-op when absent) + JSONL journal store with day-file
       layout, retention pruning, and env-configurable dir.
       Evidence: `apps/admin-console/tests/test_canonical_v2_turn_trace_store.py`
       RED (collection error) → GREEN 11/11 on 2026-08-18. Implemented as
       dataclasses matching `canonical_v2_access_log` style (design.md updated).
- [x] 1.1.2 Service turn-boundary hook in
       `services/canonical_v2_chat.py::_answer_locked`: construct collector,
       attach session snapshot + interpretation fields, emit record on
       success/degradation/error; wire store into the FastAPI app alongside the
       access-log store.
       Evidence: `tests/test_canonical_v2_turn_trace_hook.py` RED (3 failed:
       constructor/store absent) → GREEN 4/4; frozen S11A boundary preserved
       via post-construction `attach_turn_trace` (http-adapter contract suite
       128/128). Production wiring: `canonical_v2_admin.py` aggregate attaches
       `TurnTraceJournalStore()`. 2026-08-18.
- [ ] 1.1.3 Serving-layer reporting: lane in/retained/filtered counts, named
       gate drops, web provider outcomes (attempt/error/timeout/retry/cache),
       degradation token selection.
- [ ] 1.1.4 Reader CLI `apps/admin-console/scripts/read_turn_trace.py`
       (`--session/--degradation/--status/--date/--expand`), line-streaming.

## 1.2 Trace verified by replay

- [ ] 1.2.1 Run the frozen baseline sessions against the traced build; for each
       failing assertion (G1/G3/G5/G7 form) record the stage attribution read
       from the trace alone; save evidence under
       `.agents/runs/add-turn-trace-observability/trace-baseline/`.
- [ ] 1.2.2 Confirm healthy sessions (G6 form) produce `degradation: none` and
       unchanged answers.

## 1.3 Web-lane resilience

- [ ] 1.3.1 SQLite web-result cache (provider, view_key sha256, UTC day),
       read-through on view submit; cache events traced.
- [ ] 1.3.2 Single retry + 250 ms backoff per provider per view on
       transport/timeout errors only; retried attempts traced.
- [ ] 1.3.3 Per-provider circuit breaker (open @3 consecutive failures, 60 s
       probe cooldown, close on success); replaces Serper sticky disable;
       transitions traced.
- [ ] 1.3.4 Quota-watermark counters per provider/day; keepwarm consults
       breaker + watermark before searching (no quota burn above watermark).
- [ ] 1.3.5 Fault-injection acceptance: invalidate one provider key, run the
       replay suite — surviving provider/cache serves the lane, retries and
       breaker visible in trace, degraded turns carry
       `web-lane-unavailable` (wording itself unchanged — Phase 2.2 scope).

## Close-out

- [ ] Unit suites for collector/journal/cache/breaker green; full replay suite
      green vs baseline expectations; no regression on G2/G4/G6.
- [ ] Evidence rows appended to `acceptance.md`; Epic
      `fix-round-1-serving-pipeline` Phase 1 items ticked; human log + index
      updated per AGENTS.md §3.
