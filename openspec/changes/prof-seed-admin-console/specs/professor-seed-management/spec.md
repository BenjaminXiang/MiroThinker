# Spec: professor-seed-management

> Capability: centralized management of Professor-domain seed URLs
> (school/department roster pages) via an admin console, with per-seed
> manual trigger and run-status visibility.
>
> Per `docs/Professor-Requirement-Review-2026-05-10.md §1`, this capability
> inherits the system-wide invariant: the system is a 科创检索 system and
> does NOT vouch for data truth. This spec governs *seed management*
> behavior; downstream pipeline correctness (parsing, identity gates) is
> covered by other capabilities (e.g. `professor-paper-patent-from-page-
> flow`).

## ADDED Requirements

### Requirement: Seed table schema

The system MUST persist Professor-domain seed information in a single
relational table `professor_seed` with exactly five user-facing columns
plus standard surrogate primary key.

Columns:

| Column | Type | Constraint | Source | Notes |
|---|---|---|---|---|
| `id` | bigint | PK, auto-increment | system | Surrogate; not exposed to admin UI |
| `school` | text | NOT NULL | admin manual | School name; e.g. "SUSTech", "SZU" |
| `department` | text | NULL allowed | admin manual | Department name; NULL when seed represents a school-wide unified roster page |
| `seed_url` | text | NOT NULL | admin manual | Roster page URL; format-validated as URL on insert/update |
| `last_run_at` | timestamptz | NULL allowed | system auto | Set when a pipeline run against this seed completes |
| `last_run_status` | text (enum) | NOT NULL, default `'never_run'` | system auto | One of `success / failure / in_progress / never_run / adapter_missing` |

The system MUST NOT add columns for `discipline_tag`, `granularity`,
`created_by`, `updated_by`, `is_active`, or any other field beyond the six
above in MVP.

The system MAY add `created_at` and `updated_at` (timestamptz, auto) for
debugging; these are not user-facing fields and not surfaced in the admin
UI.

#### Scenario: Department-level seed

- **GIVEN** an admin entering a department-level seed
- **WHEN** they fill `school="SZU"`, `department="计算机与软件学院"`,
  `seed_url="https://cse.szu.edu.cn/teachers"`
- **THEN** the row persists with `last_run_status='never_run'`
- **AND** `last_run_at` is NULL

#### Scenario: School-wide unified roster seed

- **GIVEN** an admin entering a school-wide seed (such as SUSTech all-faculty
  page)
- **WHEN** they fill `school="SUSTech"`, `department=""` (or omit),
  `seed_url="https://faculty.sustech.edu.cn"`
- **THEN** the row persists with `department=NULL` (empty string is
  normalized to NULL on insert)
- **AND** `last_run_status='never_run'`

#### Scenario: Reject invalid URL

- **GIVEN** an admin entering a seed
- **WHEN** they fill `seed_url="not-a-url"`
- **THEN** the system MUST reject the request with HTTP 422 and a clear
  error message identifying the URL field

### Requirement: Seed CRUD endpoints

The admin console backend MUST expose five endpoints under `/api/seeds`
implementing standard create / read / update / delete operations.

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/seeds` | List all seeds; returns array sorted by (`school`, `department NULLS FIRST`, `id`) |
| GET | `/api/seeds/{id}` | Read single seed by id; returns 404 if absent |
| POST | `/api/seeds` | Create new seed; body validates against schema; returns 201 + new row |
| PUT | `/api/seeds/{id}` | Update mutable fields (`school`, `department`, `seed_url`); admin cannot directly mutate `last_run_at` or `last_run_status`; returns 200 + updated row |
| DELETE | `/api/seeds/{id}` | Hard delete; returns 204 |

The endpoints MUST NOT require authentication in MVP. The endpoints MUST
NOT support bulk operations (no `POST /api/seeds/bulk`, no Excel import)
in MVP.

#### Scenario: Hard delete

- **GIVEN** a seed with `id=42` exists
- **WHEN** admin issues `DELETE /api/seeds/42`
- **THEN** the row is removed from `professor_seed` permanently
- **AND** the response is HTTP 204 with empty body

#### Scenario: Admin cannot mutate run status

- **GIVEN** a seed with `last_run_status='in_progress'`
- **WHEN** admin issues `PUT /api/seeds/{id}` with body containing
  `last_run_status='success'`
- **THEN** the system MUST ignore the `last_run_status` field in the request
- **AND** return HTTP 200 with the row's actual current `last_run_status`
  unchanged
- (Admin can only mutate `school` / `department` / `seed_url`; status
  fields are pipeline-managed)

### Requirement: Per-seed manual trigger button + endpoint

The admin console frontend MUST render a per-row "立即爬取" button that, on
click, invokes a backend endpoint to run the Professor-domain pipeline
asynchronously against that single seed URL.

Endpoint: `POST /api/seeds/{id}/trigger`

Behavior:

- On invocation, the backend MUST set the row's `last_run_status` to
  `in_progress` synchronously (before returning the HTTP response).
- The backend MUST return HTTP 202 Accepted with a JSON body of the form
  `{"run_id": "<uuid>", "seed_id": <id>, "status": "in_progress"}`.
- The actual pipeline runs asynchronously (background task / job queue;
  implementation choice in `design.md`).
- On pipeline completion, the row's `last_run_status` MUST be updated to
  `success` or `failure` AND `last_run_at` MUST be set to the completion
  timestamp.

#### Scenario: Trigger flips status synchronously

- **GIVEN** a seed with `last_run_status='success'`
- **WHEN** admin clicks "立即爬取"
- **THEN** by the time the HTTP response returns, the row in
  `professor_seed` shows `last_run_status='in_progress'`
- **AND** an async pipeline task has been enqueued

#### Scenario: Trigger is idempotent under double-click

- **GIVEN** a seed with `last_run_status='in_progress'`
- **WHEN** admin clicks "立即爬取" again (or via tab refresh causing double-fire)
- **THEN** the system MUST NOT enqueue a second pipeline run
- **AND** the endpoint MUST return HTTP 409 Conflict with body
  `{"error": "already_in_progress", "seed_id": <id>}`

#### Scenario: Trigger on `adapter_missing` is blocked

- **GIVEN** a seed with `last_run_status='adapter_missing'`
- **WHEN** admin clicks "立即爬取"
- **THEN** the endpoint MUST return HTTP 422 Unprocessable Entity with body
  `{"error": "adapter_missing", "seed_id": <id>, "school": <school>,
  "department": <department or null>}`
- **AND** `last_run_status` remains `adapter_missing`
- **AND** no pipeline task is enqueued

### Requirement: `last_run_status` enum values

The system MUST use exactly these five string values for `last_run_status`:

- `never_run` — initial state when a seed is created; no pipeline has run
  yet.
- `in_progress` — a pipeline run is currently executing for this seed.
- `success` — the most recent pipeline run completed without raising an
  uncaught exception or producing a fatal pipeline_issue marker.
- `failure` — the most recent pipeline run completed with an uncaught
  exception or fatal pipeline_issue. Pipeline error details are surfaced
  via `pipeline_issue` table (V006) cross-reference; not stored on
  `professor_seed`.
- `adapter_missing` — the seed's (`school`, `department`) pair has no
  registered per-school adapter; pipeline cannot run. This is set by the
  adapter resolution step at the start of a pipeline run, before any
  parsing happens.

The system MUST NOT use any other value. New states require an explicit
spec change.

#### Scenario: Cron skips `adapter_missing` seeds

- **GIVEN** the cron job is iterating over all seeds for monthly re-crawl
- **AND** a seed has `last_run_status='adapter_missing'`
- **THEN** the cron MUST skip it without setting `in_progress`
- **AND** the seed's `last_run_at` and `last_run_status` are unchanged

### Requirement: Pipeline upsert semantics

The pipeline MUST treat the roster from a single-seed run as upsert input
against the existing professor canonical, applying these rules when
executing against a single seed URL:

- A roster entry whose (canonical_name_zh + institution + department)
  matches an existing professor row → **update** that professor's fields
  using the new evidence.
- A roster entry not matching any existing professor → **insert** a new
  professor row.

The pipeline MUST NOT:

- Delete professors who exist in the canonical but are absent from the
  current roster (deletion / archival is governed by
  `prof-lifecycle-state`, a separate change).
- Treat the seed URL as authoritative source for fields outside the roster
  page (downstream Tier 2 / Tier 3 parsing handles that, per
  `prof-paper-patent-from-page-flow` / `prof-school-adapter-framework`).

#### Scenario: Existing professor field update

- **GIVEN** a professor row with `name="张三"`, `institution="SZU"`,
  `department="计算机与软件学院"`, `title="副教授"`
- **AND** the roster on the seed URL now lists the same professor with
  `title="教授"`
- **WHEN** the pipeline runs
- **THEN** the professor row's `title` is updated to "教授"
- **AND** the existing `id` is preserved
- **AND** `professor.evidence` records the new source

#### Scenario: New professor insert

- **GIVEN** the canonical contains no professor matching the roster entry
- **WHEN** the pipeline runs
- **THEN** a new professor row is created
- **AND** new `id` is assigned

### Requirement: Cron monthly re-crawl

The system MUST run a cron job on a monthly schedule (configurable;
default 1st of each month at 02:00 local server time) that triggers a
pipeline run for every seed whose `last_run_status` is not
`adapter_missing` and not `in_progress`.

The cron job MUST:

- Iterate seeds in stable order (by `id` ascending) to make runs
  reproducible.
- For each eligible seed, set `last_run_status='in_progress'` before
  enqueuing the pipeline task.
- Respect a global concurrency cap (default: 4 concurrent seed runs) to
  avoid overwhelming the data-agent runtime; cap is configurable via
  Hydra.
- NOT block waiting for runs to complete; cron returns after enqueueing.

The cron job MUST coexist with manual triggers without race conditions:

- A seed already `in_progress` (whether from manual trigger or earlier
  cron) is skipped.
- A seed manually triggered after cron has enqueued it MUST return HTTP
  409 (per the trigger idempotency scenario above).

#### Scenario: Cron skips in-progress seeds

- **GIVEN** seeds A and B both eligible
- **AND** seed A is already `in_progress` (admin triggered 5 min ago)
- **WHEN** cron fires
- **THEN** cron enqueues only seed B
- **AND** seed A's status is unchanged

### Requirement: Adapter-missing detection

When the pipeline begins a run against a seed, it MUST first check
whether a per-school adapter is registered for the seed's
(`school`, `department NULLS FIRST`) pair. If no adapter is registered,
the pipeline MUST:

1. Set `last_run_status='adapter_missing'` on the seed row.
2. Set `last_run_at` to the current timestamp.
3. Write one entry to `pipeline_issue` (V006) with kind `adapter_missing`
   and a structured payload `{seed_id, school, department}`.
4. Return without invoking any parser, network call, or LLM.

Adapter resolution rules are out of scope for this spec; the
`prof-school-adapter-framework` change defines them. This spec only
defines the *interface contract* — that the pipeline MUST gate on adapter
existence and report the result via `last_run_status`.

#### Scenario: New school added without adapter

- **GIVEN** admin adds a seed with `school="<NewSchoolName>"`,
  `department=NULL`
- **AND** no adapter is registered for `<NewSchoolName>`
- **WHEN** admin clicks "立即爬取" or cron fires
- **THEN** the seed's `last_run_status` becomes `adapter_missing`
- **AND** `pipeline_issue` gains a new row with `kind='adapter_missing'`
- **AND** no Tier 2 / Tier 3 parsing or network calls are attempted

#### Scenario: Adapter registered later

- **GIVEN** a seed with `last_run_status='adapter_missing'`
- **WHEN** a developer registers a new adapter matching the seed's
  (school, department) pair
- **AND** admin clicks "立即爬取"
- **THEN** the trigger endpoint accepts the request (returns HTTP 202)
- **AND** the seed's `last_run_status` flips to `in_progress`
- **AND** the pipeline runs normally
