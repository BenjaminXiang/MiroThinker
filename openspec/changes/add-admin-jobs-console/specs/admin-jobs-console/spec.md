# Spec delta: admin-jobs-console (new capability)

## ADDED Requirements

### Requirement: Triggering a task SHALL only ever select a declared white-list entry

The system SHALL expose one declarative task table owned by the code, mapping a task id to a fixed
argv, a working directory, a timeout, a declared cadence, a switch source, a quota class, and a
PostgreSQL requirement. A run SHALL be started with `subprocess` and a token list, never through a
shell. The HTTP surface SHALL accept only a task id and a declared, closed parameter map; any task id
outside the table, any parameter the task does not declare, and any value outside a declared value
set SHALL be refused before any lock, row, or process is created, and no caller-supplied string
SHALL reach a command line.

#### Scenario: unknown task id is refused
- **GIVEN** the admin jobs API
- **WHEN** a trigger names a task id that is not in the table
- **THEN** the response is 404 and no run row is written

#### Scenario: undeclared and injected parameters are refused
- **GIVEN** a task that declares no parameters
- **WHEN** a trigger body supplies `{"params": {"domain": "paper; rm -rf /"}}`
- **THEN** the response is 422 and no process is started

#### Scenario: a declared closed parameter is substituted, never concatenated
- **GIVEN** the Milvus backfill task, whose only declared parameter is `domain` with four allowed values
- **WHEN** a trigger supplies `domain=paper`
- **THEN** the run's recorded command line contains the fixed template with `paper` substituted and every other token unchanged

### Requirement: Manual and periodic triggers SHALL pass the same gate

Every trigger, whatever its source, SHALL pass, in order: the PostgreSQL availability gate, the
breaker, the managed-config switch, the quota cap, and the re-entrancy lock. A manual trigger SHALL
NOT bypass any of them. A trigger that is refused SHALL state a stable reason code; a trigger that is
accepted but suppressed SHALL be recorded as a run with status `skipped` and its reason.

#### Scenario: a second trigger while a run is in flight is refused by the lock
- **GIVEN** a task whose run is currently executing
- **WHEN** a second trigger for the same task arrives
- **THEN** the response is 409 `job_already_running`, no second process starts, and the first run finishes normally

#### Scenario: the lock also excludes another process
- **GIVEN** a lock file held by another process for the same task
- **WHEN** a trigger arrives
- **THEN** it is refused with 409 `job_already_running`

#### Scenario: switch off produces an empty run that is still recorded
- **GIVEN** managed settings with `collection.enabled.<domain> = false`
- **WHEN** a task of that domain is triggered manually
- **THEN** no process is spawned, the response reports `skipped`, and the run history contains a `skipped` row with reason `switch_off` and the operator identity

#### Scenario: quota cap of zero refuses and records
- **GIVEN** managed settings with `max_web_searches_per_run = 0`
- **WHEN** a web-search-gated task is triggered
- **THEN** no process is spawned and the history contains a `skipped` row with reason `quota_exhausted`

#### Scenario: effective quotas reach the child process
- **GIVEN** effective caps of 7 web searches and 9 LLM calls
- **WHEN** a quota-gated task runs
- **THEN** the child process receives them as `MIROTHINKER_MAX_WEB_SEARCHES_PER_RUN` / `MIROTHINKER_MAX_LLM_CALLS_PER_RUN` and the run row stores the caps it ran under

### Requirement: Two consecutive failures SHALL open a breaker that refuses further triggers

The system SHALL count consecutive failed runs per task, reset the counter on success, and open the
breaker once two consecutive failures are recorded. While the breaker is open every trigger (manual
or scheduled) SHALL be refused with 409 `job_breaker_open`. An operator SHALL be able to clear it
through an explicit action that is itself visible in the run history.

#### Scenario: second consecutive failure opens the breaker
- **GIVEN** a task whose last two runs failed
- **WHEN** a trigger arrives
- **THEN** it is refused with 409 `job_breaker_open` and no process starts

#### Scenario: success resets the counter
- **GIVEN** a task with one recorded failure
- **WHEN** its next run succeeds
- **THEN** `consecutive_failures` is 0 and the next trigger is accepted

#### Scenario: reset is recorded
- **GIVEN** an open breaker
- **WHEN** the operator calls the reset endpoint
- **THEN** the breaker is cleared and a `breaker_reset` row carrying the operator identity appears in the history

### Requirement: Run history SHALL be durable, queryable, and expose failure samples

The system SHALL persist one row per trigger in a serving-side SQLite store, holding task id, trigger
source, operator identity, start and finish instants, status (`running`/`succeeded`/`failed`/
`skipped`/`breaker_reset`), skip reason, duration, exit code, item counts, and bounded failure
excerpts. The store SHALL be queryable per task and by status, SHALL survive reopening, and SHALL
never persist the child environment. Excerpts SHALL have credential-shaped values redacted.

#### Scenario: a successful run is queryable with duration and item count
- **GIVEN** a triggered run that exits 0 and reports `{"job_summary": {"items_processed": 3}}`
- **WHEN** the task history is queried
- **THEN** the run appears with status `succeeded`, a non-null duration, and `items_processed = 3`

#### Scenario: a failed run exposes a bounded, redacted sample
- **GIVEN** a run that fails and prints a credential-shaped line plus a traceback on stderr
- **WHEN** the run detail is requested
- **THEN** the excerpt is present, length-bounded, and contains no credential value

#### Scenario: history survives a store reopen
- **GIVEN** a store with recorded runs
- **WHEN** the store is opened again
- **THEN** every run is still readable with its original values

### Requirement: The task list SHALL show cadence, next fire time, gates, and failure state

`GET /api/canonical-v2/admin/jobs` SHALL return, per declared task, its label and domain, the declared
cadence (display text and cron expression), the next fire time computed from that expression, whether
it is gated by the collection switch, its quota class, whether it requires PostgreSQL, its
availability, its last run, whether its last run failed (red dot), and its breaker state. The page
SHALL render this list with a manual trigger control per available task and a history view with a
failure-sample entry.

#### Scenario: next fire time follows the declared cadence
- **GIVEN** a task declaring `0 2 * * 1` (Mondays 02:00 local)
- **WHEN** the list is requested
- **THEN** `next_run_at` is the next Monday 02:00 in the server's local timezone and is later than now

#### Scenario: a failed task shows a red dot
- **GIVEN** a task whose latest run failed
- **WHEN** the list is requested
- **THEN** that task's failure flag is true and the page renders the failure marker

### Requirement: PostgreSQL-dependent tasks SHALL degrade without failing the service

Tasks whose fixed command requires the build-time PostgreSQL SHALL be probed for availability with a
bounded, cached, fail-soft probe. When PostgreSQL is unavailable the task SHALL report
`available: false` and its trigger SHALL answer 503 `job_postgres_unavailable`; no probe SHALL be
able to fail process start. The remaining tasks, the history, and the rest of the admin surface SHALL
keep working.

#### Scenario: no PostgreSQL configured
- **GIVEN** an environment with no `CANONICAL_V2_DATABASE_URL`, `DATABASE_URL`, or `DATABASE_URL_TEST`
- **WHEN** the task list is requested
- **THEN** PostgreSQL-requiring tasks report `available: false` and every other task is unaffected

#### Scenario: triggering an unavailable task degrades to 503
- **GIVEN** the same environment
- **WHEN** a PostgreSQL-requiring task is triggered
- **THEN** the response is 503 `job_postgres_unavailable` and no process is started

### Requirement: Unset job storage SHALL degrade to a bounded 503

When the jobs database cannot be resolved or opened, the jobs API SHALL answer
503 `jobs_storage_unavailable` and the page SHALL show that reason, without affecting any other
canonical-v2 surface.

#### Scenario: storage unset
- **GIVEN** an environment with neither `CANONICAL_V2_JOBS_DB` nor `CANONICAL_V2_ACCESS_LOG_DB`
- **WHEN** the jobs list is requested
- **THEN** the response is 503 with detail `jobs_storage_unavailable`
