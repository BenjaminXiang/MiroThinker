## Verification

### OpenSpec

- `openspec validate company-enrichment-source-closure --strict`
  - Result: passed.

### Focused Unit / Contract Tests

- `uv run pytest tests/data_agents/company/test_release.py tests/data_agents/company/test_yiou_adapter.py tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_enrichment_e2e.py tests/storage/test_v033_migration.py tests/storage/test_alembic_revision_lineage.py -q -n0 --no-cov`
  - Result: passed, 33 tests.

- `uv run pytest tests/data_agents/company tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_enrichment_e2e.py -q -n0 --no-cov`
  - Result: passed, 121 tests.

### Lint

- `uv run ruff check src/data_agents/contracts.py src/data_agents/company/models.py src/data_agents/company/import_xlsx.py src/data_agents/company/canonical_import.py src/data_agents/company/enrichment.py src/data_agents/company/release.py src/data_agents/company/news_connectors/base.py src/data_agents/company/news_connectors/iyiou.py src/data_agents/company/news_connectors/__init__.py src/data_agents/company/official_product_capture.py src/data_agents/canonical/company.py scripts/run_company_news_ingest.py scripts/run_company_official_product_capture.py scripts/run_company_enrichment_e2e.py tests/data_agents/company/test_release.py tests/data_agents/company/test_yiou_adapter.py tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_enrichment_e2e.py tests/storage/test_v033_migration.py tests/storage/test_alembic_revision_lineage.py`
  - Result: passed.

### Real XLSX E2E

- `uv run python scripts/run_company_enrichment_e2e.py --output -`
  - Result: passed.
  - Key output: `company_rows_parsed=1025`, `with_website=621`, `released_record_count=1025`, `deterministic_status=passed`.
  - Optional-field coverage: `credit_code=0`, `legal_representative=1025`, `registered_capital=1025`, `patent_count=1025`.
  - Key-person coverage: `total=1297`, `with_description=1296`, `with_education=98`, `with_work_experience=86`.

### Live / External Checks

- `uv run python scripts/run_company_enrichment_e2e.py --live --output -`
  - Result: deterministic checks passed; live Yiou skipped.
  - Blocker: `SERPER_API_KEY` is not set.

- `uv run python scripts/run_company_official_product_capture.py --dry-run --limit 3 --max-pages 2 --timeout-seconds 5 --sleep-seconds 0 --output -`
  - Result: passed.
  - Output: `companies_considered=3`, `companies_with_products=1`, `products_extracted=3`, `products_inserted=0`.
  - Review-needed candidates: `MetaCor™`, `MetaAI™`, `The Smart Badge`.

### Notes

- A live dry-run initially exposed product false positives from navigation/recruiting sections. Added regression coverage and tightened product-title/source-span filters before accepting the live dry-run result.
- No non-dry-run product inserts were performed because this session did not establish a real product-capture run ID or cleanup plan for local DB mutation.
