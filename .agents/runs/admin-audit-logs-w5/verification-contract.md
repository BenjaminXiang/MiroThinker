# Verification contract: add-session-audit-enrichment (W5)

Created before any production-code edit (2026-09-14), per AGENTS.md §4 TDD boundary and
`openspec/config.yaml`.

## Deliverable under test

Extend the Canonical V2 access-log audit surface (store + HTTP + `/logs` page + purge script) with
identity capture, time-range/`query_type`/identity filtering, CSV/JSONL export, overview statistics,
and configurable retention — without breaking the fail-open recording chain or the two live
databases.

## Acceptance line (from `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §6, W5 row)

> 新老库无损升级（旧行身份为空显示匿名）；组合过滤（时间+状态+query_type+身份）结果正确；
> 导出与页面所见一致（抽样比对）；统计数字与 turns 表 SQL 对账一致

## RED artifacts (written before / with the implementation, must fail on the pre-change code)

| # | Artifact | Locks |
|---|---|---|
| R1 | `tests/test_canonical_v2_access_log_migration.py` | A genuine pre-W5 v1 database opens, gains the identity column in place, keeps every row/value, reads legacy rows as `anonymous`, stays readable by the pre-W5 reader, and is idempotent across opens. |
| R2 | `tests/test_canonical_v2_access_log_filters_export_stats.py` | Combined `since`/`until`/`query_type`/`identity`/`status` filtering; 4xx matrix; export = page-visible content (sample comparison); statistics reconciled against direct SQL over `turns`; fail-open recording with and without `X-Remote-User`. |
| R3 | `tests/test_purge_access_logs_retention.py` | The real `deploy/purge-access-logs.sh` resolves retention as arg > env > managed file > 90 and deletes exactly the rows outside the resolved window. |

Pre-change code must fail R1–R3 for the stated reasons (no identity column, no filter params, no
`/stats`, no `/export`, hard-coded 90). The RED run is captured in `verification.md`.

## GREEN evidence required

1. **New tests** (R1–R3) all pass, with a per-cluster statement of what each locks.
2. **Pre-existing regression suites**: full `apps/admin-console` pytest before and after, with the
   failure-set diff (`comm`) — no new failures, and pre-existing failures named.
3. **Real-interaction evidence**: scratch port **18289** (never 18188), scratch database and scratch
   managed-settings file, started from this worktree: `/logs` page 200, `X-Remote-User` write →
   filtered list → CSV/JSONL export → statistics, plus one 4xx case.
4. **Reconciliation**: statistics numbers compared to `sqlite3` aggregates over the same fixture
   database (in-test, not by eye).
5. **Privacy check**: an explicit assertion that no IP/cookie/user-agent value can reach the record
   payload or any API/export response.

## Explicit non-goals for verification

- No retrieval/answer/replay assertion: no RAG behavior is touched (the change is storage, admin
  read surface, and one page).
- No load/perf assertion: exports are bounded by `max_turns`; the store keeps a single writer lock
  as before.

## Failure policy

Any of the following stops the slice and is reported instead of worked around: the migration cannot
be made lossless; a pre-existing live database is damaged by a test run; the fail-open chain turns
into a fail-closed one; or the full suite gains a new failure attributable to this change.
