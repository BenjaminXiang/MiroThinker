# Proposal: add-admin-jobs-console

## Why

The authoritative product plan
(`docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §3.2(d), §4 C3, §5.2,
§5.5, §6 W2) scopes a **task-run surface** as the W2 slice of the wrap-up. Today an operator cannot
see or trigger data work from the admin zone at all:

- The §5.3 collection scripts exist and are (mostly) idempotent, but nothing schedules or records
  them, and there is no Web entry point. `crontab` carries only the 03:17 backup and 03:41 purge.
- The two §4‑C3 task-ops actions (Milvus backfill, retrieval validation) live only on the **unmounted**
  legacy SPA router (`backend/api/pipeline.py`), so they are 404 on the V2 shell.
- D1's supplement requires an "立即采集" button per task, and it must pass the **same gate** as the
  periodic run (re-entrancy lock / quota / breaker) — the manual path may not bypass any limit.

Verified read-only before this change (`.agents/runs/admin-jobs-console-w2/current-state.md`):

- `pipeline_run` is a build-time Postgres table and the 18188 process is started with
  `--database-url` as a CLI argument, exporting no `DATABASE_URL`/`CANONICAL_V2_DATABASE_URL`
  environment variable. W1's system-status already reports collection history as unavailable on the
  serving host for exactly this reason. **Run history therefore cannot come from `pipeline_run`.**
- Serving-side operational state already has a boring, proven carrier: one SQLite file per concern
  (`access-logs.sqlite3`, `corrections.sqlite3`), each addressed by an env variable emitted by the
  pinned `serve-18188-command.sh`.
- W1's managed settings schema already carries every value this gate needs
  (`collection.enabled.<domain>`, `collection.max_web_searches_per_run`,
  `collection.max_llm_calls_per_run`, `collection.window_start_hour_utc`,
  `collection.window_end_hour_utc`) — no second configuration source is needed or added.

## What Changes

Behavior-affecting: a new public admin API surface (`/api/canonical-v2/admin/jobs*`), a new operator
page (`/jobs`), a new serving-side SQLite store, and a new shared gate that both the manual trigger
and (from W6) the scheduled entry point must pass. No retrieval, fusion, rerank, answer, or
serving-pack behavior is touched; no collection script is modified; no cron is installed.

**In scope**

1. **Declarative task table** — task id → whitelist command, working directory, timeout, declared
   cadence (display + cron expression), switch source, quota class, PG requirement, window binding.
   Every argv is a fixed token tuple; the only accepted parameters are explicitly declared closed
   enums. No caller-supplied text ever reaches a command line, and no shell is used.
2. **One gate for manual and periodic triggers** — `flock` re-entrancy lock (cross-process, so the
   future cron wrapper shares it), managed-config switch (off ⇒ recorded empty run), quota cap
   (0 ⇒ refuse and record), 2-consecutive-failure breaker (open ⇒ refuse), PG availability probe for
   PG-requiring tasks (unavailable ⇒ 503 + hidden entry).
3. **Run history on the serving side** — one SQLite database (`CANONICAL_V2_JOBS_DB`) with
   `job_run` + `job_task_state`, recording task, trigger source, operator identity, start/finish,
   status, duration, item counts, bounded failure sample (credential-shaped lines redacted), and the
   per-task breaker/last-success state.
4. **`/jobs` page** — task list with cadence + next fire time, per-task switch/quota/PG badges, last
   run with red dot on failure, "立即采集" button, run history with a failure-sample entry.

**Out of scope** (owned elsewhere, listed so the boundary is explicit)

- W6: the OS cron table + install script, the script-side per-call counting, and the periodic runs
  themselves. W2 declares the cadence and provides the gate the cron entry will call.
- W3/W4/W5/W7 surfaces (upload/seed/issues/workbench/audit/publish).
- Syncing run history into `pipeline_run` when a build-time PG is reachable (recorded as a
  follow-up decision, not implemented).
- Provider key resolution from a worktree (the known W6 precondition); W2 does not touch it.

## Impact

| Area | Change |
|---|---|
| New capability | `admin-jobs-console` (spec delta below) |
| New code | `apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py`, `apps/admin-console/backend/api/canonical_v2_jobs.py`, `apps/admin-console/backend/static/jobs.html` |
| Touched | `apps/admin-console/backend/main.py` (router + page), `admin.html`/`logs.html` (one nav link each) |
| Unchanged | every §5.3 collection script, `managed_config.py` schema, all W1/W5 surfaces, `pipeline_run` |
| Rollback | drop two router/page lines; the SQLite file is inert (no migration, no external contract) |
