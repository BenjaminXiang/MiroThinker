# Verification contract: add-admin-jobs-console (W2)

Created before any production-code edit (2026-09-14), per AGENTS.md §4 TDD boundary and
`openspec/config.yaml`.

## Deliverable under test

A whitelist-driven task-run surface for the Canonical V2 admin zone: a declarative task table
(fixed argv only), a shared gate (flock re-entrancy lock + managed-config switch + quota cap +
2-consecutive-failure breaker + PG probe), serving-side SQLite run history, `GET/POST` job APIs,
a `/jobs` static page, and graceful degradation of the two PG-dependent task-ops actions.

## Acceptance line (from `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §6, W2 row)

> 任选白名单任务手动触发成功并入历史；运行中重复触发被锁拒绝并提示；失败任务红点

## RED artifacts (written before / with the implementation, must fail on the pre-change code)

| # | Artifact | Locks |
|---|---|---|
| R1 | `apps/admin-console/tests/test_canonical_v2_jobs_registry.py` | The white-list table is closed: every declared task's argv is built from fixed tokens (or a declared closed enum), unknown tasks and undeclared parameters are refused, no `shell=True` path exists, and every declared script path exists in the repo. Also locks the declared-cadence → next-fire-time calculator. |
| R2 | `apps/admin-console/tests/test_canonical_v2_jobs_store.py` | Run history persists (start/finish/skip), is queryable per task and per status, reports per-task last-run/red-dot/breaker state, opens idempotently, and stores no environment/secrets. |
| R3 | `apps/admin-console/tests/test_canonical_v2_jobs_runner.py` | The shared gate: second concurrent trigger refused while a run is in flight; switch off ⇒ recorded empty run; quota cap 0 ⇒ refused-and-recorded; 2 consecutive failures ⇒ breaker open and further triggers refused; success resets the counter; effective quotas reach the child env; failure excerpt and item count are recorded; PG-required task unavailable without a DSN. |
| R4 | `apps/admin-console/tests/test_canonical_v2_jobs_api.py` | HTTP surface: task list payload, 202 trigger, 409 already-running, 404 unknown task, 422 injected parameter, run history + failure-sample endpoint, PG-degraded 503 + hidden entry, storage-unavailable 503. |

Pre-change code must fail R1–R4 by collection error (`ModuleNotFoundError`/404) — the modules do not
exist before this slice. The RED run is captured in `verification.md`.

## GREEN evidence required

1. **New tests** (R1–R4) all pass, with a per-cluster statement of what each locks.
2. **Pre-existing regression suites**: full `apps/admin-console` pytest before and after this
   branch's edits, with the failure-set diff (`comm`) — no new failures; pre-existing failures named.
3. **Real-interaction evidence**: a scratch server on port **18291** (never 18188) started from this
   worktree, with a scratch jobs DB, scratch managed-settings file, and a **stub task registry** (no
   real collection run, no search/LLM quota consumed): trigger → duplicate trigger while running is
   refused → history visible after completion → two failures open the breaker + red dot → switch-off
   and quota-zero runs are recorded as skipped → PG task degraded. Served page `/jobs` returns 200.
4. **Layered report**: new-test clusters, pre-existing suite diff, and the scratch transcript are
   reported separately (no aggregate "all green").
5. **Secret hygiene check**: an assertion that the run record and the API never carry the child
   environment and that credential-shaped output lines are redacted in stored excerpts.

## Explicit non-goals for verification

- No retrieval/answer/replay assertion: no RAG behavior is touched (the surface triggers existing
  scripts; it does not change retrieval).
- No real collection run: every E2E trigger executes a stub command. Real §5.3 scripts are only
  *declared*, never executed here.
- No cron installation: §5.2's declarative cron table and W6's automatic runs are out of scope.
- No `pipeline_run` write: PG stays read-probe-only on this surface.

## Failure policy

Any of the following stops the slice and is reported instead of worked around: the white-list cannot
be made closed (some path admits caller text into argv); the lock does not hold across processes; a
pre-existing live database or the 18188 service is touched; or the full suite gains a new failure
attributable to this change.
