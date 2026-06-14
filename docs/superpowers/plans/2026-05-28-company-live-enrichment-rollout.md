# Company Live Enrichment Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run and close live Company enrichment for recent news/funding/product updates across the XLSX company set, with Yiou live discovery, official-site product writes, DB persistence, and acceptance evidence.

**Architecture:** Keep XLSX/canonical company rows as the skeleton. Use named external adapters to write additive `company_news_item` rows, extract normalized events into `company_signal_event`, and write official-site products into `company_product` plus `company_product_evidence`. Yiou is implemented as Web Search with a `site:data.iyiou.com` filter wrapped by `YiouNewsConnector`; it is not a native Yiou crawler. Treat live failures as per-company diagnostics, not global success.

**Tech Stack:** Python 3.12, uv, pytest, Ruff, Postgres/Alembic, psycopg, Serper API, BeautifulSoup, existing `apps/miroflow-agent` Company scripts.

---

## Current State

- `company-enrichment-source-closure` is archived and synced to `openspec/specs/company-enrichment-source-closure/spec.md`.
- Schema exists for:
  - `company_news_item.source_adapter`
  - `company_news_item.extraction_diagnostics`
  - `company_signal_event`
  - `company_product`
  - `company_product_evidence`
- Deterministic XLSX E2E passed:
  - `company_rows_parsed=1025`
  - `released_record_count=1025`
  - `with_website=621`
  - key-person coverage: `total=1297`, `with_description=1296`, `with_education=98`, `with_work_experience=86`
- Live gaps:
  - `SERPER_API_KEY` was absent, so Yiou live was skipped.
  - Official product capture was only dry-run sampled, not DB-written.
  - No full-company recent-news/funding/product backfill has been run.

## Preconditions

- [ ] Create a new OpenSpec change before behavior-affecting code or runbook changes, for example `company-live-enrichment-rollout`.
- [ ] Confirm target DB:
  - Use `DATABASE_URL_TEST` for first full run.
  - Do not run non-dry-run against `miroflow_real` until sample acceptance passes and rollback scope is documented.
- [ ] Set external credentials:
  - `SERPER_API_KEY` is required for Serper/Yiou live discovery. Store it in `apps/miroflow-agent/.env`; the company live-enrichment scripts load that file.
  - Tushare/CNStock are optional and should not block Serper/Yiou.
- [ ] Apply Alembic through V033 in the target DB.
- [ ] Use `docs/专辑项目导出1768807339.xlsx` as source input; do not modify it.

## Phase 1: Live Credential And DB Readiness Gate

**Files:**
- Modify: `apps/miroflow-agent/scripts/run_company_enrichment_e2e.py`
- Test: `apps/miroflow-agent/tests/scripts/test_run_company_enrichment_e2e.py`
- Evidence: `.agents/runs/company-live-enrichment-rollout/verification.md`

- [ ] Add a readiness mode to `run_company_enrichment_e2e.py`, for example `--readiness-only`.
- [ ] The readiness report must include:
  - `serper_api_key_status`
  - selected DB DSN redacted host/db name
  - whether V033 tables/columns exist
  - count of companies, companies with website, existing news rows, existing signal rows, existing product rows
- [ ] Add tests that readiness reports `SERPER_API_KEY` missing as `blocked` instead of silently skipping.
- [ ] Run:

```bash
cd apps/miroflow-agent
uv run pytest tests/scripts/test_run_company_enrichment_e2e.py -q -n0 --no-cov
uv run python scripts/run_company_enrichment_e2e.py --readiness-only --output -
```

Expected:
- With no key: report says Yiou/Serper live is blocked.
- With key: report says live source discovery is ready.

## Phase 2: Yiou Live Sample Backfill

**Files:**
- Use: `apps/miroflow-agent/scripts/run_company_news_ingest.py`
- Use: `apps/miroflow-agent/src/data_agents/company/news_connectors/iyiou.py`
- Test: `apps/miroflow-agent/tests/scripts/test_run_company_news_ingest.py`
- Evidence: `.agents/runs/company-live-enrichment-rollout/verification.md`

- [ ] Run a dry-run sample first:

```bash
cd apps/miroflow-agent
SERPER_API_KEY=... DATABASE_URL_TEST=... \
uv run python scripts/run_company_news_ingest.py \
  --connector iyiou \
  --priority top200 \
  --since 2026-01-01 \
  --limit 10 \
  --serper-fetch-article-text \
  --serper-article-max-chars 1800 \
  --sleep-seconds 0.5 \
  --dry-run
```

- [ ] Inspect the JSON report:
  - `connectors_enabled` contains `iyiou`
  - `news_fetched > 0` or clear per-company zero-result evidence
  - no crash count
- [ ] Run non-dry-run only on the same 10-company sample:

```bash
SERPER_API_KEY=... DATABASE_URL_TEST=... \
uv run python scripts/run_company_news_ingest.py \
  --connector iyiou \
  --priority top200 \
  --since 2026-01-01 \
  --limit 10 \
  --serper-fetch-article-text \
  --serper-article-max-chars 1800 \
  --sleep-seconds 0.5
```

- [ ] Verify DB:

```sql
SELECT source_adapter, count(*)
  FROM company_news_item
 WHERE source_adapter = 'iyiou'
 GROUP BY source_adapter;

SELECT source_url, title, extraction_diagnostics
  FROM company_news_item
 WHERE source_adapter = 'iyiou'
 ORDER BY fetched_at DESC
 LIMIT 20;
```

Acceptance:
- Yiou live sample writes `company_news_item` rows with `source_adapter='iyiou'`.
- `source_url` is on `data.iyiou.com`.
- `extraction_diagnostics.adapter='iyiou'`.
- The implementation remains Web Search site-filter based; do not replace it with an unsupported native Yiou crawler in this rollout.

## Phase 3: Recent Event Extraction For News/Funding/Product Launch

**Files:**
- Use: `apps/miroflow-agent/scripts/run_company_signal_extract.py`
- Use: `apps/miroflow-agent/src/data_agents/company/signal_event_extractor.py`
- Test: `apps/miroflow-agent/tests/data_agents/company/test_signal_event_extractor.py`
- Evidence: `.agents/runs/company-live-enrichment-rollout/verification.md`

- [ ] Run signal extraction for the sample news rows:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=... \
uv run python scripts/run_company_signal_extract.py \
  --limit 100 \
  --log-level INFO
```

- [ ] Verify event distribution:

```sql
SELECT event_type, count(*)
  FROM company_signal_event
 GROUP BY event_type
 ORDER BY count(*) DESC;

SELECT event_type, event_date, event_summary, confidence
  FROM company_signal_event
 WHERE event_type IN ('funding', 'product_launch')
 ORDER BY event_date DESC
 LIMIT 30;
```

Acceptance:
- News-derived events write to `company_signal_event`.
- Funding and product-launch events are distinguishable by `event_type`.
- Events have `event_date`, `event_summary`, `confidence`, and `primary_news_id` when news-backed.

## Phase 4: Official Product Capture Sample Write

**Files:**
- Use/modify: `apps/miroflow-agent/scripts/run_company_official_product_capture.py`
- Use: `apps/miroflow-agent/src/data_agents/company/official_product_capture.py`
- Test: `apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py`
- Test: `apps/miroflow-agent/tests/scripts/test_run_company_official_product_capture.py`
- Evidence: `.agents/runs/company-live-enrichment-rollout/verification.md`

- [ ] Add a DB safety guard to refuse non-dry-run when V033 tables are absent.
- [ ] Add a `--company-id` or `--company-name-contains` filter if current `--limit` is too coarse for targeted validation.
- [ ] Run dry-run sample:

```bash
cd apps/miroflow-agent
uv run python scripts/run_company_official_product_capture.py \
  --dry-run \
  --limit 20 \
  --max-pages 3 \
  --timeout-seconds 8 \
  --sleep-seconds 0.5 \
  --output -
```

- [ ] Manually inspect at least 10 emitted product candidates:
  - reject obvious navigation/recruiting/company-section false positives
  - accept low-confidence product candidates only when source span is traceable
- [ ] Run non-dry-run sample against test DB:

```bash
DATABASE_URL_TEST=... \
uv run python scripts/run_company_official_product_capture.py \
  --limit 20 \
  --max-pages 3 \
  --timeout-seconds 8 \
  --sleep-seconds 0.5 \
  --output -
```

- [ ] Verify DB:

```sql
SELECT count(*) FROM company_product;
SELECT count(*) FROM company_product_evidence;

SELECT p.company_id, p.canonical_name, p.short_description, p.quality_status,
       e.source_url, e.evidence_span
  FROM company_product p
  JOIN company_product_evidence e USING (product_id)
 ORDER BY p.updated_at DESC
 LIMIT 30;
```

Acceptance:
- Products are inserted into `company_product`.
- Every sampled product has at least one evidence row.
- `quality_status` remains `needs_review` unless a stricter verification rule is added.

## Phase 5: Full Test-DB Rollout

**Files:**
- Use: `run_company_news_ingest.py`
- Use: `run_company_signal_extract.py`
- Use: `run_company_official_product_capture.py`
- Evidence: `.agents/runs/company-live-enrichment-rollout/full-test-rollout.md`

- [ ] Run Yiou/Serper for all companies in batches:

```bash
SERPER_API_KEY=... DATABASE_URL_TEST=... \
uv run python scripts/run_company_news_ingest.py \
  --connector iyiou \
  --priority all \
  --since 2026-01-01 \
  --serper-fetch-article-text \
  --serper-article-max-chars 1800 \
  --sleep-seconds 0.5
```

- [ ] Run generic Serper if Yiou coverage is too low:

```bash
SERPER_API_KEY=... DATABASE_URL_TEST=... \
uv run python scripts/run_company_news_ingest.py \
  --connector serper \
  --priority all \
  --since 2026-01-01 \
  --serper-fetch-article-text \
  --serper-article-max-chars 1800 \
  --sleep-seconds 0.5
```

- [ ] Run event extraction:

```bash
DATABASE_URL_TEST=... \
uv run python scripts/run_company_signal_extract.py \
  --include-processed \
  --limit 5000 \
  --log-level INFO
```

- [ ] Run official product capture:

```bash
DATABASE_URL_TEST=... \
uv run python scripts/run_company_official_product_capture.py \
  --limit 621 \
  --max-pages 3 \
  --timeout-seconds 8 \
  --sleep-seconds 0.5 \
  --output -
```

- [ ] Record:
  - companies processed
  - companies with news
  - news rows inserted
  - event rows inserted by type
  - products inserted
  - product evidence rows
  - fetch failures by domain
  - top false-positive classes if any

Acceptance:
- Full test DB has live news rows and product rows.
- Funding/product-launch event counts are non-zero or documented as source coverage limitations.
- Failure list is reviewable and not silently swallowed.

## Phase 6: Retrieval / Consumer Smoke

**Files:**
- Inspect before changing: `apps/miroflow-agent/src/data_agents/service/retrieval.py`
- Inspect before changing: `apps/admin-console/backend/api/domains.py`
- Possible tests:
  - `apps/miroflow-agent/tests/data_agents/service/test_retrieval_company_patent.py`
  - admin-console company detail tests if company products are exposed there

- [ ] Check whether current retrieval/detail endpoints expose:
  - latest `company_signal_event`
  - `company_product`
  - `company_news_item`
- [ ] If not exposed, create a separate OpenSpec change for presentation/serving. Do not silently broaden the ingestion change.
- [ ] Run smoke SQL at minimum:

```sql
SELECT c.canonical_name, e.event_type, e.event_date, e.event_summary
  FROM company_signal_event e
  JOIN company c USING (company_id)
 ORDER BY e.event_date DESC
 LIMIT 20;

SELECT c.canonical_name, p.canonical_name AS product_name, p.short_description
  FROM company_product p
  JOIN company c USING (company_id)
 ORDER BY p.updated_at DESC
 LIMIT 20;
```

Acceptance:
- Data is queryable from DB.
- If UI/chat serving is not wired, explicitly mark it as a follow-up presentation change.

## Phase 7: Production / Real-DB Run Gate

- [ ] Only after test DB acceptance, prepare real DB runbook:
  - command list
  - expected volume
  - rate limits
  - rollback SQL scoped by `refresh_run_id`, `source_adapter`, and product IDs
- [ ] Take DB backup or snapshot.
- [ ] Run with conservative batches first:
  - Yiou top 50
  - generic Serper top 50
  - product top 50 websites
- [ ] Review sample.
- [ ] Continue to all companies.

Acceptance:
- Real DB has live enrichment rows.
- Acceptance report distinguishes:
  - completed full run
  - skipped providers
  - blocked domains
  - review-needed product candidates

## Final Verification Commands

```bash
cd apps/miroflow-agent
uv run pytest tests/data_agents/company tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_enrichment_e2e.py -q -n0 --no-cov
uv run ruff check src/data_agents/company scripts/run_company_news_ingest.py scripts/run_company_official_product_capture.py scripts/run_company_enrichment_e2e.py tests/data_agents/company tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_enrichment_e2e.py
openspec validate company-live-enrichment-rollout --strict
```

Expected:
- Company tests pass.
- Ruff passes.
- OpenSpec validates.

## Acceptance Definition

The work is complete only when all of the following are true:

- `SERPER_API_KEY` is present or live search is formally blocked with evidence.
- Yiou live sample writes `company_news_item.source_adapter='iyiou'`.
- Recent-news ingest has run against all 1025 companies or an explicitly bounded company set approved for this stage.
- Signal extraction has run and produced a typed event report for `funding` and `product_launch`.
- Official product capture has performed non-dry-run writes to test DB and produced product evidence rows.
- Full run report records counts and failure reasons.
- Serving/UI/chat exposure is either verified or explicitly split into a separate presentation change.
