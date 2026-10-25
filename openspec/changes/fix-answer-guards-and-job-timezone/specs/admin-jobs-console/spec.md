## ADDED Requirements

### Requirement: Next-run display uses the cron wall clock

The jobs list MUST compute each task's `next_run_at` in the timezone the OS
cron entries run in — `MIROTHINKER_JOB_TIMEZONE` when set, otherwise server
local time. A `0 2 * * 1` task on a CST host MUST render 02:00, never 10:00.

#### Scenario: Weekly job on a CST host

- **WHEN** `MIROTHINKER_JOB_TIMEZONE=Asia/Shanghai`
- **AND** the task cadence is `0 2 * * 1`
- **THEN** `next_run_at` is `…T02:00:00+08:00`, not `…T10:00:00+08:00`

#### Scenario: Missing override

- **WHEN** `MIROTHINKER_JOB_TIMEZONE` is unset
- **THEN** the server's local timezone is used, matching the cron table
