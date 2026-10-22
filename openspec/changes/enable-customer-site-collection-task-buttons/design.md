# Design: enable-customer-site-collection-task-buttons

## Data bootstrap

The serving pack (`/var/tmp/mirothinker-data-v2/serving-pack-fembed-v3-synthdepth/lookup.sqlite3`)
contains 24,520 papers and 3,958 professors as `lookup_document.document_json`. A bounded slice is
projected into the raw collection tables:

| Source | Target | Rows | Mapping |
|---|---|---|---|
| paper lookup docs missing `abstract` | `paper` `quality_status=needs_enrichment` | 200 | id/title/doi/arxiv/authors/citation/year |
| paper lookup docs with abstract, missing `summary_zh` | `paper` `quality_status=ready` | 200 | same; `summary_zh=NULL` |
| paper lookup docs with DOI | `paper` `identity_status=unverified` | 100 | same |
| professor lookup docs with `homepage` | `professor` + `source_page` | 200 | id/name/aliases/profile summary; homepage as `official_profile` |
| professor homepages | `professor_seed` | 185 (unique URLs) | school/department/url |

`canonical_source` is set to `openalex`/`crossref`/`web_search` from the available identifiers.
Existing rows are preserved with `ON CONFLICT DO NOTHING`.

## Limits

Each task gets a per-run bound so one click cannot run for hours:

| Task | Bound | Expected runtime |
|---|---|---|
| company-product | 50 companies | 5–15 min |
| paper-search | 20 papers | 5–10 min |
| paper-summary | 50 papers | 3–5 min |
| paper-doi | 100 papers | 1–3 min |
| professor-rescrape | 20 professors | 1–3 min |
| professor-homepage-paper | 10 professors | 2–5 min |

The job timeout remains 3600s (5400s for ops only).

## Packaging

`paper-search-mcp==0.1.4` is installed into `/root/deploy/fullstack-v2/.venv`; it pulls
`pypdf`, `feedparser`, `feedparser-sgmllib` only. No service restart is needed for the package
itself, but the service restart is needed for the new task argv.

## Out of scope

The three ops tasks need a build-time PostgreSQL DSN and the index rebuild toolchain; the three
upload imports need a writable build DB and upload ledger; the two seed-refresh tasks need the
seed console DB. Those remain disabled / linked to their pages.
