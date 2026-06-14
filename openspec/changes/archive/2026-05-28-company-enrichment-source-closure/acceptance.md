## Acceptance Evidence

### Company release exposes optional publish fields

- Status: verified.
- Evidence: `uv run pytest tests/data_agents/company/test_release.py -q -n0 --no-cov` passed as part of the focused Company test run.
- Result: `CompanyRecord` and released `core_facts` now expose optional `credit_code`, `legal_representative`, `registered_capital`, and `patent_count`; missing values remain optional.

### Company key persons preserve structured background

- Status: verified.
- Evidence: `tests/data_agents/company/test_release.py` asserts `description`, `education_structured`, and `work_experience` from XLSX team raw text.
- Real XLSX evidence: `run_company_enrichment_e2e.py --output -` reported `key_person_coverage.total=1297`, `with_description=1296`, `with_education=98`, and `with_work_experience=86`.

### Yiou enrichment is a named source adapter

- Status: verified for adapter contract; live discovery skipped.
- Evidence: `tests/data_agents/company/test_yiou_adapter.py` and `tests/scripts/test_run_company_news_ingest.py` passed.
- Fixture result: `fixture_checks.iyiou_adapter.records=1`, with diagnostics `adapter=iyiou`, `site_filter=data.iyiou.com`, `items_seen=1`, `items_accepted=1`.
- Live blocker: `SERPER_API_KEY` is not set, so live Yiou discovery was skipped by `run_company_enrichment_e2e.py --live --output -`.

### Official website product capture stores product evidence

- Status: verified for bounded crawler/extractor/writer and small live dry-run.
- Evidence: `tests/data_agents/company/test_official_product_capture.py` and `tests/scripts/test_run_company_official_product_capture.py` passed.
- Storage evidence: migration `V033_add_company_enrichment_product_tables.py` adds `company_product`, `company_product_evidence`, and source-provenance columns on `company_news_item`.
- Live dry-run: `run_company_official_product_capture.py --dry-run --limit 3 --max-pages 2 --timeout-seconds 5 --sleep-seconds 0 --output -` completed with `companies_considered=3`, `companies_with_products=1`, `products_extracted=3`, `products_inserted=0`. Extracted products were review-needed candidates: `MetaCor™`, `MetaAI™`, and `The Smart Badge`.
- Regression: a false-positive regression was added and fixed so navigation, follow-us text, and recruiting sections are not emitted as products.

### Company XLSX E2E proves enrichment closure

- Status: deterministic E2E passed; live Yiou skipped because credential is absent.
- Command: `uv run python scripts/run_company_enrichment_e2e.py --output -`
- Result: `deterministic_status=passed`, `company_rows_parsed=1025`, `released_record_count=1025`, `with_website=621`.
- Optional-field coverage: `credit_code=0`, `legal_representative=1025`, `registered_capital=1025`, `patent_count=1025`.
- Fixture checks: Yiou adapter passed with one accepted `data.iyiou.com` record; official product capture passed with one product fixture.
- Smoke: first released object had core facts and the new optional keys.

## Skipped / Remaining Live Checks

- Yiou live source discovery was skipped because `SERPER_API_KEY` is not set.
- No non-dry-run product DB insertion was performed in this session; writer and migration are covered by tests, and the official-site live sample was run in dry-run mode to avoid mutating a dirty local database without an explicit run ID cleanup plan.
