# Verification: add-admin-jobs-console (W2)

Branch `feat/admin-jobs-console` (worktree `.worktrees/admin-jobs-console`, parent `feat/admin-audit-logs`
@ `08b8e4d9`). Contract: `verification-contract.md` (written before any production-code edit).
Current-state evidence: `current-state.md`.

## 1. RED → GREEN

RED was captured on the pre-change code (before `jobs.py` existed):

```
$ cd apps/admin-console && uv run pytest -q tests/test_canonical_v2_jobs_{registry,store,runner,api}.py
E   ModuleNotFoundError: No module named 'src.data_agents.canonical_v2.jobs'
ERROR tests/test_canonical_v2_jobs_registry.py
ERROR tests/test_canonical_v2_jobs_store.py
ERROR tests/test_canonical_v2_jobs_runner.py
ERROR tests/test_canonical_v2_jobs_api.py
!!!!!!!!!!!!!!!!!!! Interrupted: 4 errors during collection !!!!!!!!!!!!!!!!!!!!
4 errors in 0.38s
```

→ `red-run-before-change.txt`. After implementation:

```
$ cd apps/admin-console && uv run pytest -q tests/test_canonical_v2_jobs_registry.py \
      tests/test_canonical_v2_jobs_store.py tests/test_canonical_v2_jobs_runner.py \
      tests/test_canonical_v2_jobs_api.py
78 passed in 4.01s
```

## 2. New tests written in this slice (78)

| Cluster | File | n | What it locks | Fixture source |
|---|---|---|---|---|
| R1 white list | `tests/test_canonical_v2_jobs_registry.py` | 35 | the declared table is the §5.3+C3 set; every declared script path exists in the repo; argv is a fixed token tuple; unknown task / undeclared parameter / out-of-set value / missing required parameter all refused; ops tasks carry no cadence and require PG; the professor rescrape declares `--apply --confirm-real-db`; no shell metacharacter can appear in a command display; cron next-fire (weekly/monthly/step/list/DOM-or-DOW/future-and-bounded/malformed) | constructed scenarios over the real `JOB_TASKS` |
| R2 run history | `tests/test_canonical_v2_jobs_store.py` | 11 | start/finish round-trip with duration + counts; skip rows carry reason + operator; history filter/order/pagination + `total`; per-task summaries drive the red dot; 2 consecutive failures open the breaker and a success resets it; skipped runs do not touch the breaker; breaker reset is visible in history; reopen keeps history; symlinked database path refused; excerpts bounded + redacted + absent from the database file | constructed rows + sentinel `sk-local` string |
| R3 gate + execution | `tests/test_canonical_v2_jobs_runner.py` | 20 | success records run + parsed `job_summary` counts; second in-flight trigger refused (same process) and refused while **another process** holds the flock; lock releases immediately; switch off ⇒ recorded skip with no spawn; quota 0 ⇒ recorded skip; quota-exempt task still runs with caps 0; effective caps reach the child env and the run row; breaker after 2 failures; success resets the counter; scheduled run outside the window skipped; manual run records window state without blocking; timeout ⇒ failed/124 with a sample; PG-required task unavailable/available (injected probe, TTL-cached, fail-soft); unknown task + invalid params; task views expose cadence/gates/next fire; child environment never persisted | programmable spawn stub (with blocking events), real `flock` child process, injected PG connector |
| R4 HTTP + degradation | `tests/test_canonical_v2_jobs_api.py` | 12 | the real declared table is what the list endpoint serves (cadence, next fire, gates, PG unavailable, param sets); 202 trigger lands in history with operator identity; 409 `job_already_running` on a duplicate; 404 unknown task; 422 injected parameter; failure red dot + failure-sample endpoint; breaker 409 then reset reopens; PG task 503 + no run row; unknown run 404; reset on unknown task 404; `/jobs` page served; unset storage ⇒ 503 `jobs_storage_unavailable` | real subprocess stubs + `app.state` runtime, real `TestClient` |

## 3. Pre-existing regression suites (full `apps/admin-console`)

| Run | Command | Result |
|---|---|---|
| before | `cd apps/admin-console && uv run pytest -q` (HEAD `08b8e4d9` + docs only) | `96 failed, 1052 passed, 29 skipped, 122 errors in 191.61s` → `full-suite-before.txt`, failure set `failures-before.txt` (218 entries) |
| after | same command on `feat/admin-jobs-console` | `96 failed, 1130 passed, 29 skipped, 122 errors in 188.45s` → `full-suite-after.txt`, failure set `failures-after.txt` (218 entries) |

Failure-set diff (`comm -13 failures-before.txt failures-after.txt` = **new** failures):

```
(none — the diff is empty; also recorded in failures-new.txt / failures-fixed.txt)
```

Counts reconcile exactly: failure and error totals are identical before/after (96 failed, 122 errors)
and `passed` grew by 78, which is precisely the new test count of this slice.

Pre-existing failures are unchanged and unrelated to this slice (they concern the legacy
professor/dashboard/seed API surfaces, the review HTTP origin checks, and tests needing a live
Postgres/seed fixture); they are reported here as they were, not silently absorbed.

## 4. Real-interaction evidence (scratch port 18291, stub tasks)

Scratch instance: `scratch_18291_server.py` on `127.0.0.1:18291` (never 18188), scratch storage
`/var/tmp/w2-jobs-smoke-18291/{jobs.sqlite3,settings.json,locks/}`, scratch managed-settings file,
**no** `DATABASE_URL*` in the process environment, registry = the real declared table + four stub
tasks. Driver: `scratch-18291-smoke.sh`; raw console transcript `scratch-18291-smoke-transcript.txt`.
No real collection task was triggered; no web-search/LLM quota was spent.

| # | Assertion | Result | Evidence |
|---|---|---|---|
| 1 | whitelist task triggers and lands in history (with duration + item count) | PASS — 202, then `status=succeeded duration_ms=3015 exit_code=0 operator=smoke-operator trigger=manual`; a second stub run reports `items_processed=2 duration_ms=18` | `scratch-18291-trigger-slow.json`, `scratch-18291-history-slow.json`, `scratch-18291-trigger-ok.json`, `scratch-18291-history-ok.json` |
| 2 | duplicate trigger while running is refused by the lock with a clear message | PASS — 409 `{"detail":"job_already_running"}`; the in-flight run is visible in the meantime | `scratch-18291-locked.json`, `scratch-18291-history-while-running.json` |
| 3 | history visible after completion and the failure-sample entry is retrievable | PASS — run detail returns the command plus `stderr_excerpt` | `scratch-18291-run-detail-failed.json` |
| 4 | a failing task shows the red dot | PASS — `failure_flag=True`, `last_run.status=failed`, `exit_code=1` | `scratch-18291-list-after-failures.json` |
| 5 | two consecutive failures fuse the breaker | PASS — `breaker_open=True consecutive_failures=2`, and the next trigger is 409 `job_breaker_open`; the operator reset clears it and is recorded | `scratch-18291-breaker.json`, `scratch-18291-reset.json` |
| 6 | PG-dependent ops actions degrade without failing the service | PASS — stub PG task, real `ops-milvus-backfill`, real `ops-retrieval-validation` all 503 `job_postgres_unavailable`; the list marks them `available=false` (page hides the button); `/api/health` stayed `ok` and the process never restarted | `scratch-18291-pg-stub.json`, `scratch-18291-pg-milvus.json`, `scratch-18291-pg-e2e.json`, `scratch-18291-list-after-failures.json` |
| 7 | switch off produces a recorded empty run | PASS — 202 `{"status":"skipped","skip_reason":"switch_off"}`; also quota 0 ⇒ `skipped(quota_exhausted)` | `scratch-18291-skip-switch-off.json`, `scratch-18291-skip-quota.json` |
| + | parameter white list on the **real** ops task | PASS — `{"domain":"paper; rm -rf /"}` ⇒ 422 `job_invalid_params`; unknown task ⇒ 404 | `scratch-18291-injection.json`, `scratch-18291-unknown.json` |
| + | `/jobs` page served with the shared nav | PASS — 200, contains `任务运维` | `scratch-18291-page-jobs.html` |
| + | credential hygiene in stored excerpts | PASS — sentinel written by the stub as `api_key=smoke-sentinel` is stored and returned as `api_key=[redacted]`; the database file does not contain the sentinel (unit test R2 asserts the same for the whole file) | `scratch-18291-run-detail-failed.json`; `test_canonical_v2_jobs_store.py::test_excerpts_are_bounded_and_redacted` |

Environment after the run: scratch server stopped, `18291` has no listener; the 18188 service was
never touched (same pid before and after the slice's smoke runs).

## 5. Acceptance mapping

`openspec/changes/add-admin-jobs-console/acceptance.md` carries the clause-by-clause mapping from the
plan's §6 W2 acceptance line, §3.2(d), §4 C3 and §5.5 to the evidence files listed above.

## 6. Not verified / limitations (stated, not hidden)

1. **No real collection run.** Every §5.3 script is only *declared* in the white list; none was
   executed. Consequence: the end-to-end behavior of a real `run_company_news_ingest.py` run under
   this gate (its own logging, idempotency, runtime) is not observed here.
2. **The `{"job_summary": ...}` reporting contract is new** (`jobs.py::parse_job_summary`). No existing
   §5.3 script emits it yet, so `items_processed` will be `—` until W6 adds the line to the scripts;
   the parsing itself is covered by tests and by the stub.
3. **Quota is enforced at the gate, not inside the scripts** (see `current-state.md` §6.5). W2 proves
   cap-0 refusal, cap export and per-run recording; it does not prove call counting.
4. **No cron installed.** `deploy/cron/mirothinker-collect` and the periodic path are W6. `next_run_at`
   is computed from the *declared* cadence, which is why the page labels it as a plan.
5. **Window enforcement applies to scheduled triggers only** (design.md §3 decision). Scheduled
   window enforcement is covered by a unit test; there is no scheduler yet to observe it live.
6. **No `pipeline_run` write** and no sync with a future build-time PG; the ops tasks' parent-run
   bookkeeping of the legacy SPA router is intentionally dropped.
7. **W1 system-status freshness integration not wired**: `job_task_state.last_success_at` is the
   serving-host freshness source this surface produces, but the status panel still reports
   `collection_history: unavailable`. Cross-slice follow-up, recorded in the human log §发现 7.
8. **Static page is not browser-automated**: it was served and its JSON contract exercised, but no
   headless-browser assertion of the rendered table exists (the repo has no browser harness for these
   static pages).
