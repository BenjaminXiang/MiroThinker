# Design: add-admin-jobs-console

## 1. Placement (why the gate lives in `miroflow-agent`)

The gate must be shared by two callers that live in different processes:

1. the serving app (`apps/admin-console/backend/api/*`) answering the manual trigger;
2. the future cron entry point (W6) that launches the same tasks.

W1 already set the precedent that a value shared by both sides lives in
`apps/miroflow-agent/src/data_agents/canonical_v2/` (`managed_config.py`) and is imported by
admin-console as `src.data_agents.canonical_v2.…`. W2 follows it with one deep module:

```
apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py
    JOB_TASKS / get_job_task          -> the closed white list
    JobRunStore                       -> serving-side SQLite history + per-task state
    JobLock                           -> flock re-entrancy lock
    PostgresProbe                     -> cached, fail-soft availability probe
    JobRuntime                        -> the gate + subprocess execution
```

Everything else (HTTP, page) stays in admin-console. The module exposes decisions, not internals:
callers get a task view or a typed error, never a lock handle, connection, or SQL.

## 2. White list model (closed by construction)

```python
@dataclass(frozen=True)
class JobTask:
    task_id: str
    label: str                        # Chinese operator label
    description: str
    domain: str | None                # company/paper/patent/professor; None for ops tasks
    argv_template: tuple[str, ...]    # fixed tokens; may contain {param} placeholders
    params: Mapping[str, tuple[str, ...]]  # param -> closed value set (empty = no params accepted)
    cwd_relative: str                 # resolved against the repo root of the checkout
    timeout_seconds: int
    schedule_cron: str | None         # None = manual only
    schedule_display: str
    collection_gated: bool            # True => switch is managed_config collection.enabled[domain]
    quota: Literal["web_search", "llm"] | None
    requires_postgres: bool
    window_bound: bool                # nightly window applies to scheduled runs
```

Three properties make the white list closed:

1. `argv_template` is a code-owned tuple; every element is either a literal token or a `{name}`
   placeholder whose value must be a member of `params[name]`.
2. `params` is a closed set of literal values (`{"domain": ("company", "paper", "patent",
   "professor")}`). Values are substituted by membership, never concatenated from caller text.
3. There is no shell: the runner spawns `subprocess.run(list(argv), shell=False)`.

Requests carry only `{"params": {...}}`. A parameter that the task does not declare, a value outside
the declared set, a missing required placeholder, or an unknown task id is refused with 422/404
before any lock, row, or process is created.

### The declared table

| task_id | domain | fixed argv (cwd `apps/miroflow-agent` unless stated) | cadence (declared) | switch | quota | PG |
|---|---|---|---|---|---|---|
| `company-news-ingest` | company | `uv run python scripts/run_company_news_ingest.py` | `0 2 * * 1` 每周一 02:00 | collection.company | web_search | no |
| `company-official-product-capture` | company | `uv run python scripts/run_company_official_product_capture.py` | `30 3 * * 1` 每周一 03:30 | collection.company | web_search | no |
| `paper-search-backfill` | paper | `uv run python scripts/run_paper_search_backfill.py` | `0 2 * * 3` 每周三 02:00 | collection.paper | web_search | no |
| `paper-summary-zh-backfill` | paper | `uv run python scripts/run_paper_summary_zh_backfill.py` | `30 3 * * 3` 每周三 03:30 | collection.paper | llm | no |
| `paper-doi-verify` | paper | `uv run python scripts/run_paper_doi_verify.py` | `30 3 * * 3` 每周三 03:30 | collection.paper | llm | no |
| `professor-homepage-rescrape` | professor | `uv run python scripts/run_profile_bio_rescrape.py --apply --confirm-real-db` | `0 2 1 * *` 每月 1 日 02:00 | collection.professor | llm | no |
| `professor-homepage-paper-ingest` | professor | `uv run python scripts/run_homepage_paper_ingest.py --resume` | `0 3 1 * *` 每月 1 日 03:00 | collection.professor | web_search | no |
| `ops-milvus-backfill` | — | `uv run python scripts/run_milvus_backfill.py --domain {domain} [--dry-run]` | manual | none | llm | **yes** |
| `ops-retrieval-validation` | — | `bash apps/admin-console/scripts/host_e2e_agentic_rag.sh` (cwd repo root) | manual | none | llm | **yes** |

Notes that must stay visible rather than implicit:

- `professor-homepage-rescrape` is dry-run by default, so the write intent
  (`--apply --confirm-real-db`) is *declared in the table*; the operator sees it in the page label
  and in the run's recorded command line.
- The two `ops-*` tasks are §4-C3 actions de-risked from the legacy SPA router: their fixed argv is
  the same command the SPA built, minus the parent-`pipeline_run` bookkeeping that cannot exist on
  the serving host. Both remain PG-requiring, so on a serving host without PG they degrade (503 +
  hidden entry) rather than fail.
- `--milvus-uri` is intentionally **not** a parameter: the script's own default (`./milvus.db` of the
  agent directory) plus the ambient `MILVUS_URI`/`CHAT_MILVUS_URI` remain the single source, so the
  Web surface cannot point a backfill at an arbitrary Milvus file.

## 3. The gate (single implementation, ordered)

`JobRuntime.trigger(task_id, params, operator, trigger_source)`:

```
1 resolve task            -> 404 job_unknown_task
2 params validation       -> 422 job_invalid_params      (before any state change)
3 PG gate                 -> 503 job_postgres_unavailable (requires_postgres only)
4 breaker gate            -> 409 job_breaker_open
5 switch gate (collection)-> 202 skipped, reason=switch_off  (recorded, no lock)
6 quota gate              -> 202 skipped, reason=quota_exhausted (recorded, no lock)
7 flock (LOCK_EX|LOCK_NB) -> 409 job_already_running
8 write running row + spawn
```

Rationale for the order: everything a caller can fix by reading the message is decided before any
side effect; the lock is taken immediately before the run row so that "in flight" is exactly
"lock held or a `running` row exists". Gates 3–6 read one snapshot of the managed settings document,
so a scheduled and a manual trigger of the same instant see the same limits — **the manual path has
no bypass** (D1).

**Window semantics (decision, flagged for ratification).** `collection.window_*_hour_utc` is the
nightly collection window. It is enforced for `trigger_source="schedule"` (the W6 cron entry) and
recorded — not enforced — for manual triggers, whose whole purpose is "operator asks now". Manual
triggering still passes switch, quota, lock and breaker unchanged, which is what §3.2(d) enumerates.
The run row stores `window_bound` + `inside_window` so the deviation is visible in history.

**Quota semantics.** The effective caps come from W1's managed settings. A quota-gated task whose cap
is `0` is refused and recorded (`quota_exhausted`); otherwise the effective caps are exported to the
child as `MIROTHINKER_MAX_WEB_SEARCHES_PER_RUN` / `MIROTHINKER_MAX_LLM_CALLS_PER_RUN` and stored on
the run row, so the value each run was allowed to spend is auditable. Counting *inside* the scripts
is W6 work (§5.5 instrumentation); W2 owns the gate and the audit.

**Breaker.** `job_task_state.consecutive_failures` increments on `failed`, resets on `succeeded`.
`>= 2` ⇒ `breaker_open=1` and every later trigger is refused with 409 `job_breaker_open` until an
operator calls `POST …/reset`, which clears the counter and appends a `breaker_reset` row to history
(operation visible in the audit trail, not a silent mutation).

**Locking.** One lock file per task (`<jobs-dir>/locks/<task_id>.lock`), `fcntl.flock(fd,
LOCK_EX|LOCK_NB)` with the descriptor held for the whole run. `flock` is per open-file-description,
so it excludes both another process (the W6 cron wrapper) and another concurrent request in the same
process. No lock is taken for a skipped run.

## 4. Run history store

One SQLite file, opened with the same hardening as `AccessLogStore` (no symlink, no hard link,
mode 0600, WAL, `busy_timeout`). Path resolution order:

1. `CANONICAL_V2_JOBS_DB` (explicit, mirrors `CANONICAL_V2_ACCESS_LOG_DB`);
2. `<dir of CANONICAL_V2_ACCESS_LOG_DB>/jobs.sqlite3` — the "same directory, same pattern" default
   from §3.3/§5.2 so the serving line works without touching the pinned launch command file;
3. unset ⇒ the surface answers 503 `jobs_storage_unavailable` and the page shows the reason.

```sql
job_run(run_id PK, task_id, trigger_source, operator, status, skip_reason,
        started_at, finished_at, duration_ms, exit_code,
        items_processed, items_failed, summary_json,
        stdout_excerpt, stderr_excerpt, window_bound, inside_window)
job_task_state(task_id PK, consecutive_failures, breaker_open, breaker_opened_at,
               last_run_id, last_status, last_failure_at, last_success_at)
workspace_meta(key PK, value)      -- schema_version row for future slices
```

Child reporting contract: the child may print a final line `{"job_summary": {...}}`; `items_processed`
/ `items_failed` are taken from it when present, otherwise `NULL` and the page shows `—`. Excerpts are
bounded (4 000 chars each, stored once, tail-kept) and credential-shaped matches
(`api_key|token|secret|password|credential` followed by a value) are replaced with `[redacted]`
before storage: the child environment is never persisted.

## 5. HTTP surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/canonical-v2/admin/jobs` | task views (cadence, next fire, gates, availability, last run, red dot) + storage/PG status |
| POST | `/api/canonical-v2/admin/jobs/{task_id}/run` | manual trigger; 202 accepted (running or recorded skip), 409 refused, 404/422 bad request, 503 unavailable |
| GET | `/api/canonical-v2/admin/jobs/{task_id}/runs` | history page for one task (`limit`, `status`) |
| GET | `/api/canonical-v2/admin/jobs/runs/{run_id}` | one run including the failure sample (excerpts + command) |
| POST | `/api/canonical-v2/admin/jobs/{task_id}/reset` | clear an open breaker (recorded as a `breaker_reset` history row) |

Error detail strings are stable snake_case codes (`job_already_running`, `job_breaker_open`,
`job_postgres_unavailable`, `job_quota_exhausted`…); the page maps them to Chinese operator text.
Bodies never echo the child environment and never echo a credential.

## 6. Degradation (plan §2.4)

- **No PG**: `PostgresProbe` resolves a DSN from `CANONICAL_V2_DATABASE_URL` → `DATABASE_URL` →
  `DATABASE_URL_TEST` and tries one bounded connect (`connect_timeout=2`), cached for 30 s, and
  fail-soft (any launch/environment problem is simply "unavailable"; it never raises into the app).
  PG-requiring tasks are then `available: false` in the list payload (the page hides their trigger
  button) and their POST answers 503. **No probe runs at process start**, so a PG-less serving host
  cannot fail to boot; the 30 s TTL re-probes by itself when PG comes back, which a boot-time-only
  probe would not do. Core W2 behavior (history, locks, breaker, non-PG tasks) is unaffected.
- **No jobs DB / unwritable storage**: 503 + page banner; every other admin surface keeps working.
- **No managed settings file**: W1's documented defaults apply (all domains on, quota 200/500).

## 7. Baseline / precedent check

`JobRuntime` is the same shape as `AccessLogStore` + its API router: constructor-injected clock and
environment, pure functions for policy, SQLite for state, typed errors at the boundary. No new
framework, no new front-end stack, no change to any collection script or to `managed_config.py`.

## 8. Verification surface

Deterministic module ⇒ RED is unit/contract tests (`tests/test_canonical_v2_jobs_*.py`), plus a real
interaction check on a scratch port with a stub registry (no real collection run, no search/LLM
quota). Detail: `.agents/runs/admin-jobs-console-w2/verification-contract.md`.
