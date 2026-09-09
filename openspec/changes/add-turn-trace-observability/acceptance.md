# Acceptance: add-turn-trace-observability

Verification intents per spec requirement. Evidence is appended as rows when
each item lands (command + artifact path + date). Unit-green alone is NOT
sufficient for RAG/chat items (AGENTS.md §4 TDD boundary).

## Trace requirements

| # | Requirement | Verification intent | Evidence |
|---|---|---|---|
| A1 | One `TurnTrace` per turn, all stages populated | Replay baseline sessions; assert via reader that every turn has session snapshot, lane counts, gate drops, web outcomes, degradation token, answer subject | replay 2026-08-18: every turn carries snapshot/lanes/gate-drops/outcomes/degradation/subject (trace-baseline/) (2026-08-18) |
| A2 | Failure attributable from trace alone | For G1/G3/G5/G7-form failures, read the diverging stage from the trace without code inspection; save per-failure attribution notes | G1/G3 anchor binding, G4 relationship-lane (0,0), G5 expansion base — attribution.md, journal only (2026-08-18) |
| A3 | Healthy path unchanged | G6-form turns: same answers/citations; `degradation: none` | G6 clarification turn degradation=clarification status=ok; smoke status=ok degradation=none (2026-08-18) |
| A4 | Journal + reader | `read_turn_trace.py --session/--degradation/--expand` works against a replay day file | read_turn_trace.py exercised on live journals (summary + --expand) (2026-08-18) |

## Web-lane resilience requirements

| # | Requirement | Verification intent | Evidence |
|---|---|---|---|
| B1 | Retry with backoff (transport/timeout only) | Unit: fake provider failing once then succeeding → result returned, `retried: 1` in trace; auth error → no retry | transport retry test: retried=1 result served; auth/quota non-retried (fault-inj: bocha err=1 retry=0) (2026-08-18) |
| B2 | View+day cache | Unit: same view twice → second is cache-hit; UTC rollover → miss; cache failure → no-cache fallback traced | cache-hit + day-rollover tests; production cache=1 rows in fault-injection journal (2026-08-18) |
| B3 | Circuit breaker replaces sticky disable | Unit: 3 consecutive failures → OPEN (provider skipped); probe after cooldown succeeds → CLOSED; Serper "not enough credits" maps to OPEN-with-reason, recoverable | breaker open@3/skip/probe-recover tests; fault-inj bocha closed->open x34; sticky disable removed (2026-08-18) |
| B4 | Quota watermark + keepwarm | Unit: counter above watermark blocks keepwarm search, allows user-turn search with trace event | watermark test: keepwarm blocked above watermark, user turns proceed; keepwarm through lane transport (2026-08-18) |
| B5 | Fault-injection end-to-end | Kill one provider key; replay suite runs; lane served by survivor/cache; retries/breaker visible in trace; degraded turns tokenized `web-lane-unavailable` | BOCHA_API_KEY invalidated: G2 replay ALL PASS, serper+cache served, breaker visible, no false token (2026-08-18) |

## Regression gate

| # | Requirement | Verification intent | Evidence |
|---|---|---|---|
| C1 | No behavior change on healthy path | Full replay suite vs frozen baseline expectations (G1/G3/G5/G7 still fail-or-pass exactly as before trace — trace must not alter outcomes; G2/G4/G6 unchanged) | 1.2 replay parity: G1/G3/G5 stable RED, G2/G6 PASS preserved; G4/G7 variance within envelope (2026-08-18) |
