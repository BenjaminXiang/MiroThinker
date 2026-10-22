# Proposal: enable-customer-site-collection-task-buttons

## Why

The customer site can now run `company-news-ingest`, but the other six collection buttons on
`/jobs` are either no-ops or fail:

- `company-official-product-capture` reads a default XLSX that the customer bundle does not ship;
- `paper-*` and `professor-*` tasks point at the raw collection DB, which contains only company
  tables, so every run exits 0 with 0 rows;
- `paper-search-backfill` additionally lacks the `paper-search-mcp` package;
- no task has a row bound, so once data exists a single click could run for hours.

The product decision (2026-10-22) is to make the six **collection** buttons usable on the
customer node, while keeping the build/ops/import/seed tasks platform-side.

## What Changes

- Ship a company-product input workbook generated from `company` (200 companies with websites).
- Bootstrap the raw collection DB from the serving pack lookup:
  - 500 papers (200 missing abstract, 200 missing `summary_zh`, 100 DOI-unverified);
  - 200 professors with official homepage rows and 185 seed rows.
- Install `paper-search-mcp==0.1.4` into the service venv.
- Add per-run row bounds to the six collection task definitions:
  - company-product `--limit 50`
  - paper-search `--limit 20`
  - paper-summary `--limit 50`
  - paper-doi `--limit 100`
  - professor-homepage-rescrape `--limit 20`
  - professor-homepage-paper-ingest `--limit 10`
- Restart the service so `/jobs` serves the new argv.

## Capabilities

### Modified Capabilities

- `admin-jobs-console` — customer-site collection task data bootstrap, bounded argv, and
  availability of the six collection buttons.

## Impact

- Writes only to `miroflow_collection_v1`; the serving candidate DB, serving pack, index,
  retrieval and `/chat` are untouched.
- Adds four Python packages to the service venv (`paper-search-mcp`, `pypdf`, `feedparser`,
  `feedparser-sgmllib`).
- Out of scope: `ops-milvus-backfill`, `ops-milvus-backfill-dry-run`,
  `ops-retrieval-validation`, the three upload imports and the two seed-refresh tasks — they need
  a build-time PostgreSQL / upload ledger / seed console DB that the serving node does not have.
- Rollback: restore `jobs.py.bak-limit-*`, remove the generated XLSX, delete the bootstrapped
  rows by `canonical_source`/pilot ids, restart.
