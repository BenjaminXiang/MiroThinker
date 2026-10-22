# Spec delta: admin-jobs-console (customer-site collection buttons)

## ADDED Requirements

### Requirement: Customer-site collection tasks are runnable and bounded

The customer serving node SHALL run the seven collection tasks (`company-news-ingest`,
`company-official-product-capture`, `paper-search-backfill`, `paper-summary-zh-backfill`,
`paper-doi-verify`, `professor-homepage-rescrape`, `professor-homepage-paper-ingest`) against the
raw collection database, and each non-news task SHALL pass a per-run row bound so a single click
cannot run unbounded.

#### Scenario: Collection button starts a bounded run

- **WHEN** an operator clicks “立即运行” on a collection task
- **THEN** the run command resolves to the service venv Python and includes the declared
  `--limit` value
- **AND** the child receives `DATABASE_URL=miroflow_collection_v1`

#### Scenario: Task has data to process

- **WHEN** the raw collection DB has papers/professors bootstrapped from the serving pack
- **THEN** paper/professor tasks process at least one row and exit 0
- **AND** the run summary reports the processed count

#### Scenario: Build-only tasks remain unavailable

- **WHEN** the console has no build-time PostgreSQL DSN
- **THEN** the three ops tasks keep `available=false` with `postgres_unavailable`
- **AND** the import/seed tasks remain linked to their pages rather than showing a run button
