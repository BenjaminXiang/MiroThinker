# Verification Contract: add-turn-trace-observability

Created 2026-08-18 before production-code edits (AGENTS.md §4 TDD boundary).
RED definitions below are written FIRST; implementation proceeds only after the
RED artifacts exist and fail for the right reason.

## Mode

- Unit-level TDD (RED → GREEN) is permitted and encouraged for the
  deterministic pieces: trace collector, JSONL journal, cache, breaker, quota
  counters, retry policy. These are plain Python objects with injected fakes.
- RAG/chat-level GREEN additionally requires replay/fault-injection evidence —
  a unit test alone is NOT GREEN for tasks 1.2.x and 1.3.5.

## RED definitions

### RED-1: no trace exists (task 1.1)

- Command: `uv run python scripts/read_turn_trace.py --date <today>` (after the
  reader is written, against the current untraced build).
- Expectation BEFORE implementation: no journal dir/file exists; reader exits
  with "no trace files". After 1.1.x: baseline replay turns appear with all
  stages populated.

### RED-2: failures not attributable (task 1.2)

- Before 1.1.x lands, replay G1/G3/G5/G7-form sessions and attempt stage
  attribution from logs alone → impossible (only output-level access log).
- GREEN: per-failure attribution notes written from `read_turn_trace.py --expand`
  output only, saved under `trace-baseline/`.

### RED-3: silent swallow (task 1.3)

- Unit (write first, must FAIL against current adapter): fake Bocha provider
  raising `ConnectionError` once then returning one result → assert result is
  returned and outcome records `retried: 1`. Current adapter: `_search_provider`
  swallows the exception → result list is empty → assertion fails. That failure
  IS the RED artifact.
- Companion REDs: cache-hit assertion (no cache today), breaker-skip assertion
  (no breaker today), keepwarm-watermark assertion (no counters today).

### RED-4: fault injection (task 1.3.5)

- Scenario: set `BOCHA_API_KEY` to an invalid value for a local serve instance;
  run `scripts/replay_fix_round1.py` against it.
- GREEN requires ALL of: suite completes without crash; at least one turn shows
  cache-hit or serper-served web evidence in trace; breaker OPEN transition for
  bocha appears in trace; any web-degraded turn carries `web-lane-unavailable`
  (answer text itself unchanged — Phase 2.2 owns wording).

## GREEN gates (all must hold before Candidate)

1. New unit suites green (collector / journal / cache / breaker / quota /
   retry) — `apps/admin-console` and/or `apps/miroflow-agent` nearest suites.
2. RED-4 fault-injection scenario passes with trace evidence saved.
3. Replay suite vs frozen baseline: outcome parity (G1/G3/G5/G7 fail exactly as
   baseline — trace must not change outcomes; G2/G4/G6 behavior unchanged).
4. Evidence rows appended to `acceptance.md`; Epic Phase 1 items ticked.

## Out of scope for GREEN here

- Answer wording on lane failure (Phase 2.2).
- Any retrieval/ranking/gate semantic change on the healthy path.
