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
- [x] 1.1.3 Serving-layer reporting: lane in/retained/filtered counts, named
       gate drops, web provider outcomes (attempt/error/timeout/retry/cache),
       degradation token selection.
- [x] 1.1.4 Reader CLI `apps/admin-console/scripts/read_turn_trace.py`
       (`--session/--degradation/--status/--date/--expand`), line-streaming.
       Evidence: `tests/test_read_turn_trace.py` 4/4 green; exercised against
       the live journal during 1.2 (summary + --expand on real turns).

## 1.2 Trace verified by replay

- [x] 1.2.1 Run the frozen baseline sessions against the traced build; for each
       failing assertion (G1/G3/G5/G7 form) record the stage attribution read
       from the trace alone; save evidence under
       `.agents/runs/add-turn-trace-observability/trace-baseline/`.
       Evidence: replay 2026-08-18 vs baseline — stable lines identical (G1/G3/G5
       RED, G2/G6 PASS), variance lines within envelope (G4 FAIL today = P5
       defect form; G7 PASS 3/3); all four failures attributed from journal
       alone: G1/G3 anchor binding (news headline), G4 relationship-lane (0,0)
       data gap, G5 expansion-base drift. See `trace-baseline/attribution.md`.
- [x] 1.2.2 Confirm healthy sessions (G6 form) produce `degradation: none` and
       unchanged answers.
       Evidence: G6 clarification turn traced `degradation=clarification,
       status=ok`, session PASS; smoke turn `status=ok, degradation=none`.

## 1.3 Web-lane resilience

- [x] 1.3.1 SQLite web-result cache (provider, view_key sha256, UTC day),
       read-through on view submit; cache events traced.
       Evidence: test_web_lane_resilience cache-hit/day tests; production
       fault-injection shows cache=1 rows.
- [x] 1.3.2 Single retry + 250 ms backoff per provider per view on
       transport/timeout errors only; retried attempts traced.
       Evidence: transport-retry test (provider called twice, retried=1,
       result served); auth/quota classified non-retryable.
- [x] 1.3.3 Per-provider circuit breaker (open @3 consecutive failures, 60 s
       probe cooldown, close on success); replaces Serper sticky disable;
       transitions traced.
       Evidence: breaker open/skip/probe-recovery tests; production
       fault-injection bocha closed→open ×34 then skipped; Serper sticky
       disable removed (provider test updated to new contract).
- [x] 1.3.4 Quota-watermark counters per provider/day; keepwarm consults
       breaker + watermark before searching (no quota burn above watermark).
       Evidence: watermark test (keepwarm blocked above watermark, user turns
       proceed); keepwarm rerouted through lane transport.
- [x] 1.3.5 Fault-injection acceptance: invalidate one provider key, run the
       replay suite — surviving provider/cache serves the lane, retries and
       breaker visible in trace, degraded turns carry
       `web-lane-unavailable` (wording itself unchanged — Phase 2.2 scope).
       Evidence: BOCHA_API_KEY invalidated → G2 replay ALL PASS (serper +
       cache served the lane); 72 web-outcome rows; bocha auth errors
       non-retried + breaker open; gate drops visible; no false degradation
       token while serper alive. `.agents/runs/add-turn-trace-observability/
       fault-injection/`.

## Close-out

- [x] Unit suites for collector/journal/cache/breaker green; full replay suite
      green vs baseline expectations; no regression on G2/G4/G6.
      Evidence: agent 269 passed (serving+resilience+reporting+runtime);
      admin 15 store/hook + 148 adapter suites; 1.2 replay parity documented;
      fault-injection G2 ALL PASS. Two contract-locked tests updated to the
      resilience contract (keepwarm-through-lane-transport; no sticky disable)
      with rationale in-test.
- [x] Evidence rows appended to `acceptance.md`; Epic
      `fix-round-1-serving-pipeline` Phase 1 items ticked; human log + index
      updated per AGENTS.md §3.
