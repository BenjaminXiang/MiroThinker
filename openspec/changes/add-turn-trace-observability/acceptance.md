# Acceptance: add-turn-trace-observability

Verification intents per spec requirement. Evidence is appended as rows when
each item lands (command + artifact path + date). Unit-green alone is NOT
sufficient for RAG/chat items (AGENTS.md §4 TDD boundary).

## Trace requirements

| # | Requirement | Verification intent | Evidence |
|---|---|---|---|
| A1 | One `TurnTrace` per turn, all stages populated | Replay baseline sessions; assert via reader that every turn has session snapshot, lane counts, gate drops, web outcomes, degradation token, answer subject | _pending_ |
| A2 | Failure attributable from trace alone | For G1/G3/G5/G7-form failures, read the diverging stage from the trace without code inspection; save per-failure attribution notes | _pending_ |
| A3 | Healthy path unchanged | G6-form turns: same answers/citations; `degradation: none` | _pending_ |
| A4 | Journal + reader | `read_turn_trace.py --session/--degradation/--expand` works against a replay day file | _pending_ |

## Web-lane resilience requirements

| # | Requirement | Verification intent | Evidence |
|---|---|---|---|
| B1 | Retry with backoff (transport/timeout only) | Unit: fake provider failing once then succeeding → result returned, `retried: 1` in trace; auth error → no retry | _pending_ |
| B2 | View+day cache | Unit: same view twice → second is cache-hit; UTC rollover → miss; cache failure → no-cache fallback traced | _pending_ |
| B3 | Circuit breaker replaces sticky disable | Unit: 3 consecutive failures → OPEN (provider skipped); probe after cooldown succeeds → CLOSED; Serper "not enough credits" maps to OPEN-with-reason, recoverable | _pending_ |
| B4 | Quota watermark + keepwarm | Unit: counter above watermark blocks keepwarm search, allows user-turn search with trace event | _pending_ |
| B5 | Fault-injection end-to-end | Kill one provider key; replay suite runs; lane served by survivor/cache; retries/breaker visible in trace; degraded turns tokenized `web-lane-unavailable` | _pending_ |

## Regression gate

| # | Requirement | Verification intent | Evidence |
|---|---|---|---|
| C1 | No behavior change on healthy path | Full replay suite vs frozen baseline expectations (G1/G3/G5/G7 still fail-or-pass exactly as before trace — trace must not alter outcomes; G2/G4/G6 unchanged) | _pending_ |
