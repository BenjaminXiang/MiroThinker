# Acceptance Evidence

## 2026-05-28

### Requirement: Yiou site-filter discovery uses web-search organic results

- Status: Verified.
- Evidence:
  - `SerperSearchConnector` uses `https://google.serper.dev/search` and parses `organic` results.
  - Yiou CLI wiring wraps `SerperSearchConnector` with `YiouNewsConnector` and `site_filters=["data.iyiou.com"]`.
  - Organic search queries do not append generic news keyword tails.
  - Organic search queries do not apply news-style `tbs` recency filters by default.
  - Yiou adapter attempts registered/canonical names plus normalized-name fallback terms.
  - Yiou adapter rejects offsite URLs, generic Yiou landing/list paths, and name-mismatched Yiou detail pages.

### Scenario: Yiou profile page is found through organic search

- Status: Verified.
- Test evidence:
  - `tests/data_agents/company/test_serper_news_connector.py::test_search_connector_parses_organic_items_for_site_filtered_sources`
  - `tests/scripts/test_run_company_news_ingest.py::test_build_connectors_yiou_wraps_serper_search_with_data_iyiou_filter`
- Live evidence:
  - Command: `uv run python scripts/run_company_enrichment_e2e.py --live --live-limit 20 --output -`
  - Result: `deterministic_status=passed`, `live_checks.status=passed`.
  - XLSX rows parsed: `1025`.
  - Companies checked: `20`.
  - Companies with company-confirmed Yiou records: `2`.
  - Accepted company-confirmed Yiou records: `2`.
  - `深圳旭宏医疗科技有限公司`: `1` accepted Yiou record at `https://data.iyiou.com/company/details/d3b4498fbc8ce101bd078c08f94e2066/profile?source=iyiou.comdetail&from=more-data`.
  - `深圳元戎启行科技有限公司`: `1` accepted Yiou intelligence record.

### Scenario: Yiou record is found by normalized-name fallback

- Status: Verified.
- Test evidence:
  - `tests/data_agents/company/test_yiou_adapter.py::test_yiou_adapter_retries_normalized_name_query_terms`
- Live evidence:
  - The live report records `query_terms` and `records_by_query` for each company.

### Scenario: Generic Yiou pages are not accepted as company evidence

- Status: Verified.
- Test evidence:
  - `tests/data_agents/company/test_yiou_adapter.py::test_yiou_adapter_filters_generic_yiou_pages_and_reports_diagnostics`
- Live evidence:
  - The final live sample reported `items_rejected_irrelevant_path` for companies where Serper returned generic Yiou pages.
  - Example: `安创生态发展（深圳）有限公司` saw `items_seen=4`, `items_accepted=0`, `items_rejected_irrelevant_path=2`, `items_rejected_name_mismatch=2`.

### Scenario: Name-mismatched Yiou detail page is rejected

- Status: Verified.
- Test evidence:
  - `tests/data_agents/company/test_yiou_adapter.py::test_yiou_adapter_rejects_name_mismatch_records`
- Live evidence:
  - `深圳市路可为科技有限公司` saw `items_seen=13`, `items_accepted=0`, `items_rejected_name_mismatch=13`.
  - Manual follow-up confirmed several returned Yiou pages were about unrelated companies, such as `RoboSense速腾聚创` and `墨芯人工智能科技（深圳）有限公司` for the `深圳景赛智能科技有限公司` query.

### Scenario: Live validation samples multiple companies

- Status: Verified.
- Test evidence:
  - `tests/scripts/test_run_company_enrichment_e2e.py::test_parse_args_accepts_live_limit`
- Live evidence:
  - `live_checks.companies_checked=20`.
  - Zero-result samples are reported per company without failing the adapter globally.

### Scenario: Description and founder context produce source-search query terms

- Status: Verified.
- Test evidence:
  - `tests/data_agents/company/test_yiou_adapter.py::test_yiou_adapter_uses_description_alias_and_founder_query_terms`
  - `tests/data_agents/company/test_yiou_adapter.py::test_yiou_adapter_does_not_use_generic_product_phrases_as_aliases`
  - `tests/scripts/test_run_company_enrichment_e2e.py::test_build_live_yiou_context_uses_xlsx_description_team_and_project`
- Evidence:
  - Query context now includes company name, normalized name, project name, description, and team rows.
  - Deterministic alias extraction accepts explicit short-name style descriptions such as `公司简称ExampleBot`.
  - Generic product/service/technology phrases are not emitted as standalone aliases.

### Requirement: PitchHub site-filter discovery uses web-search organic results

- Status: Verified.
- Evidence:
  - `PitchHubNewsConnector` uses `site:pitchhub.36kr.com` through `SerperSearchConnector`.
  - PitchHub accepts only detail-like project and organization paths.
  - Accepted PitchHub records keep `source_adapter='pitchhub_36kr'`, source URL, raw text, and extraction diagnostics.
  - Accepted PitchHub detail pages are fetched through the reader fallback after URL/path/name confirmation.

### Scenario: PitchHub project page is found and enriched through detail fetch

- Status: Verified.
- Test evidence:
  - `tests/data_agents/company/test_yiou_adapter.py::test_pitchhub_adapter_fetches_detail_text_after_acceptance`
- Live evidence:
  - Command: `uv run python scripts/run_company_enrichment_e2e.py --live --live-limit 2 --output -`
  - Result: `deterministic_status=passed`, `live_checks.status=passed`.
  - `深圳旭宏医疗科技有限公司`: `2` accepted PitchHub records.
  - Accepted URLs included `https://pitchhub.36kr.com/project/1678475362006017` and `https://pitchhub.36kr.com/organization/1678213442122752`.
  - PitchHub detail fetch attempts: `2`; successes: `2`; fetched content characters: `3537`.

### Scenario: PitchHub discovery uses the same context query strategy as Yiou

- Status: Verified.
- Test evidence:
  - `tests/data_agents/company/test_yiou_adapter.py::test_pitchhub_adapter_uses_same_context_queries_and_provenance`
  - `tests/scripts/test_run_company_news_ingest.py::test_cli_dry_run_passes_snapshot_context_to_pitchhub_connector`
  - `tests/scripts/test_run_company_news_ingest.py::test_build_connectors_pitchhub_wraps_serper_search_with_pitchhub_filter`
- Evidence:
  - Ingest and E2E scripts pass snapshot/project/description/team context to source adapters.
  - Diagnostics record `query_terms`, `records_by_query`, accepted counts, and rejection counts.

### Scenario: PitchHub live validation reports source-level coverage

- Status: Verified.
- Live evidence:
  - Command: `uv run python scripts/run_company_enrichment_e2e.py --live --live-limit 20 --output ../../.agents/runs/company-iyiou-site-search-live-fix/company-live-20-2026-05-28.json`
  - Result: `deterministic_status=passed`, `live_checks.status=passed`.
  - XLSX rows parsed: `1025`.
  - Companies checked: `20`.
  - Yiou: `3` companies with records, `7` accepted records, `541` content characters.
  - PitchHub: `9` companies with records, `16` accepted records, `29523` content characters.
  - `深圳旭宏医疗科技有限公司` retained accepted PitchHub project and organization URLs.
