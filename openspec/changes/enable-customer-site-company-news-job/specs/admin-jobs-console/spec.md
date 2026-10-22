# Admin Jobs Console — customer-site company news delta

## ADDED Requirements

### Requirement: Customer-site company-news job uses a local collection database

The system SHALL provide `company-news-ingest` on the customer site with a dedicated raw
collection database (`miroflow_collection_v1`) containing `company`, `company_snapshot` and
`company_news_item`, and SHALL pass that database to the child as `DATABASE_URL`.

#### Scenario: Manual run succeeds
- **WHEN** an authenticated operator triggers `company-news-ingest` from `/jobs`
- **THEN** the child runs with the service venv Python (not `uv`), receives the collection DB
  DSN, completes with `succeeded`, and `company_news_item` gains rows.

### Requirement: Weekly scheduled trigger

The system SHALL install a weekly trigger for `company-news-ingest` (Monday 02:00 server-local
time) that invokes the same gate with `trigger_source=schedule`, and the run history SHALL record
that trigger.

#### Scenario: Scheduled run is recorded
- **WHEN** the cron wrapper runs for `company-news-ingest`
- **THEN** a `job_run` row with `trigger_source='schedule'` is written and its status is
  `succeeded` (or a recorded skip reason).

### Requirement: Local-time next fire display

The `next_run_at` displayed by `/jobs` SHALL be computed in the configured local timezone
(`MIROTHINKER_JOB_TIMEZONE`, default host local), so `0 2 * * 1` reads as 02:00.

#### Scenario: Display matches schedule
- **WHEN** the task list is rendered on the customer site (CST)
- **THEN** `next_run_at` is a Monday 02:00 local timestamp.

### Requirement: Scope limited to company-news-ingest

Other collection/import/seed/ops tasks SHALL NOT be enabled by this change; their existing
availability and platform-side ownership remain unchanged.

#### Scenario: Other tasks stay out of scope
- **WHEN** the operator opens `/jobs`
- **THEN** only `company-news-ingest` is locally runnable; the other tasks retain their previous
  availability/unavailable state.
