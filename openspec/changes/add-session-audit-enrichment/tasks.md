# Tasks: add-session-audit-enrichment

Status legend: `[ ]` pending, `[~]` in progress, `[x]` done with evidence.

## 1. Setup (behavior-affecting ⇒ verification contract first)

- [x] 1.1 Create `openspec/changes/add-session-audit-enrichment/` (proposal, design, spec delta, tasks, acceptance).
- [x] 1.2 Record the read-only current-state findings against the two live access-log databases (schema, counts, `query_type` values, indexes) before editing code.
- [x] 1.3 Create `.agents/runs/admin-audit-logs-w5/verification-contract.md` before any production-code edit.
- [x] 1.4 Capture the pre-change full `apps/admin-console` suite result on this branch (`full-suite-before.txt`, `failures-before.txt`).

## 2. Record side

- [x] 2.1 `AccessLogTurnRecord.user_identity` + `normalize_user_identity()` (trim, 120-char cap, blank → `anonymous`).
- [x] 2.2 `record_turn` persists the identity inside the existing single transaction (fail-open unchanged).
- [x] 2.3 `canonical_v2_chat.py` `_record_access_turn` reads `X-Remote-User` at the single choke point; no IP/cookie/user-agent is read.
- [x] 2.4 Reads normalize legacy `NULL`/empty to `anonymous` via `COALESCE(NULLIF(...))`; no tri-state on any surface.

## 3. Migration

- [x] 3.1 Detect the identity column structurally (`PRAGMA table_info`) and `ALTER TABLE` it in when missing, inside the schema transaction.
- [x] 3.2 Keep the schema marker at the base value so pre-W5 code still opens a migrated database (rollback path).
- [x] 3.3 Verify losslessness, idempotency, and old-reader compatibility with a real v1 fixture database.

## 4. Query side

- [x] 4.1 `list_sessions` accepts `since`, `until`, `query_type`, `identity`; AND-combined with `q`/`status`.
- [x] 4.2 Session summaries expose `identities` (sorted distinct, derived like `statuses`); turn details expose `user_identity`.
- [x] 4.3 HTTP parameter validation: date or offset-bearing ISO datetime, `since <= until`, bounded text, 422 otherwise.

## 5. Export

- [x] 5.1 Store-level bounded export query returning the matching sessions' turns in page order.
- [x] 5.2 `GET /access-logs/export?format=csv|jsonl` with attachment headers (sessions, turns, truncated).
- [x] 5.3 Field set identical to what the page renders; sample compared against the session-detail endpoint.

## 6. Statistics

- [x] 6.1 Store-level aggregates over matching turns: totals, per-day sessions/turns, query types, identities, Top queries, error rate.
- [x] 6.2 `GET /access-logs/stats` with a documented 30-day default window, `top_limit`, deterministic ordering.
- [x] 6.3 Reconciliation test: every reported number equals the same aggregate computed by direct SQL on `turns`.

## 7. Retention

- [x] 7.1 `deploy/purge-access-logs.sh`: stdlib-only resolution (arg > env > managed file > 90), source reported, invalid value warns and falls back.
- [x] 7.2 Integration test running the real script against scratch database + settings file for all four levels.
- [x] 7.3 `deploy/README.md` retention notes updated to the configurable behavior.

## 8. Page

- [x] 8.1 `logs.html`: filter row (time range, query type, identity, status, search), export buttons, overview panel, retention line, identity labels.
- [x] 8.2 No `innerHTML`; same static-page conventions; no new page.

## 9. Verification

- [x] 9.1 New: `tests/test_canonical_v2_access_log_migration.py` (lossless upgrade, idempotency, old-reader compatibility).
- [x] 9.2 New: `tests/test_canonical_v2_access_log_filters_export_stats.py` (combined filters, 4xx matrix, export-vs-page equality, SQL reconciliation, fail-open identity recording).
- [x] 9.3 New: `tests/test_purge_access_logs_retention.py` (real script, four precedence levels).
- [x] 9.4 Scratch-port smoke on **18289** with scratch database/config: page load, `X-Remote-User` write → filtered query → export → stats.
- [x] 9.5 Full `apps/admin-console` suite after the change; before/after failure-set diff recorded.
- [x] 9.6 `.agents/runs/admin-audit-logs-w5/verification.md` with layered evidence.

## 10. Documentation

- [x] 10.1 `docs/plans/2026-09-14-session-audit-log.md` (Chinese, append-only: done / findings / verification / affected issues).
- [x] 10.2 `docs/plans/index.md` — append one line only.
- [x] 10.3 `openspec/change-ledger.md` — append the change row.

## 11. Commit

- [x] 11.1 Commit on `feat/admin-audit-logs` (no push).
