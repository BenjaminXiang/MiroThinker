# Tasks: add-admin-jobs-console

Status legend: `[ ]` pending, `[~]` in progress, `[x]` done with evidence.

## 1. Setup (behavior-affecting ⇒ verification contract first)

- [ ] 1.1 Create `openspec/changes/add-admin-jobs-console/` (proposal, design, spec delta, tasks, acceptance).
- [ ] 1.2 Record the read-only current-state findings (§5.2/§5.3 scripts, entry points, `pipeline_run`, storage conventions) in `.agents/runs/admin-jobs-console-w2/current-state.md` before editing code.
- [ ] 1.3 Create `.agents/runs/admin-jobs-console-w2/verification-contract.md` before any production-code edit.
- [ ] 1.4 Capture the pre-change full `apps/admin-console` suite result on this branch (`full-suite-before.txt`, `failures-before.txt`).
- [ ] 1.5 Register the change in `openspec/change-ledger.md`.

## 2. White list (R1)

- [ ] 2.1 `JobTask` + `JOB_TASKS` table: the nine declared entries of design.md §2, each with fixed argv, closed params, cwd, timeout, cadence, switch source, quota class, PG requirement.
- [ ] 2.2 `get_job_task` / `argv_for(args)`: unknown id, undeclared parameter, out-of-set value, and missing placeholder all refused.
- [ ] 2.3 Declared-cadence → next fire time (`cron_next_fire`), minute resolution, local timezone, Vixie day-of-month/day-of-week OR semantics.

## 3. Store (R2)

- [ ] 3.1 `JobRunStore`: hardened SQLite open (no symlink/hard link, 0600, WAL), `job_run` + `job_task_state` + `workspace_meta` schema, idempotent initialization.
- [ ] 3.2 Start/finish/skip/breaker-reset writes; per-task state updates (consecutive failures, breaker, last success/failure).
- [ ] 3.3 Queries: per-task history with status filter, run detail, per-task summary for the list payload (last run, red dot, breaker).
- [ ] 3.4 Bounded excerpt storage with credential-shaped redaction; the child environment is never persisted.

## 4. Gate (R3)

- [ ] 4.1 `JobLock` (flock, non-blocking, held for the whole run) + `PostgresProbe` (DSN order, bounded connect, 30 s TTL, fail-soft).
- [ ] 4.2 `JobRuntime.trigger` gate order of design.md §3 with stable reason codes; skipped runs recorded without taking the lock.
- [ ] 4.3 Execution: token-list `subprocess.run`, per-task timeout, `job_summary` parsing, quota env export, failure/success bookkeeping, breaker open at 2 consecutive failures.
- [ ] 4.4 Breaker reset.

## 5. HTTP + page (R4)

- [ ] 5.1 `backend/api/canonical_v2_jobs.py`: list / trigger / history / run detail / reset, with stable error codes and storage+PG degradation.
- [ ] 5.2 Mount the router and the `/jobs` page in `backend/main.py`.
- [ ] 5.3 `static/jobs.html`: task list with cadence + next fire + gate badges + red dot + trigger button, history table, failure-sample panel, degradation banner.
- [ ] 5.4 Shared nav: add the `任务运维` link to `admin.html`, `logs.html`, and the new page.

## 6. Verification

- [ ] 6.1 RED run captured on pre-change code (all four test modules fail for the stated reason).
- [ ] 6.2 GREEN: `tests/test_canonical_v2_jobs_{registry,store,runner,api}.py` all pass.
- [ ] 6.3 Scratch-port interaction (18291, stub registry, scratch DB/settings): trigger → duplicate refused → history → two failures → breaker + red dot → switch-off/quota skips → PG degradation → page 200.
- [ ] 6.4 Full `apps/admin-console` suite after, diffed against the before-run (`comm`) — no new failures.
- [ ] 6.5 Write `.agents/runs/admin-jobs-console-w2/verification.md` with the layered report.

## 7. Documentation and close-out

- [ ] 7.1 `docs/plans/2026-09-14-jobs-console-log.md` (Chinese round log: 做了什么 / 发现 / 怎么验证 / 影响哪些问题).
- [ ] 7.2 Append one line to `docs/plans/index.md` (this worktree only).
- [ ] 7.3 Update `openspec/change-ledger.md` status row to `in-verification` with the evidence summary.
- [ ] 7.4 Staged commits: implementation snapshot, smoke evidence, documentation.
