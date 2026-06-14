## Why

The Company domain is useful for basic search, but it is not complete: external enrichment, product/official-site capture, key-person structure, publish-field coverage, and E2E acceptance are not closed. This prevents the platform from honestly supporting product, founder-background, and source-grounded company analysis beyond the XLSX skeleton.

## What Changes

- Add a first-class external company enrichment source path, starting with `data.iyiou.com`, instead of treating `site:data.iyiou.com` Serper search as the final source adapter.
- Preserve source evidence in `company_news_item` / `company_signal_event` and structured enrichment outputs, with source URLs and extraction diagnostics.
- Add an official website/product-page capture path that can populate product-oriented company enrichment records from official pages or stable third-party source pages.
- Extend Company publish contracts so PRD-required fields such as credit code, legal representative, registered capital, patent count, and richer key-person fields can be exposed when present.
- Promote captured team/person raw intro into structured key-person fields: description, education hints, and work-experience hints.
- Add E2E verification using `docs/专辑项目导出1768807339.xlsx`, including import, enrichment/backfill, release, and retrieval smoke checks.
- Keep the implementation honest about source limits: page-only or low-confidence enrichments must remain reviewable and must not overwrite XLSX/canonical fields without evidence.

## Capabilities

### New Capabilities

- `company-enrichment-source-closure`: Close the Company-domain external enrichment loop for Yiou/source adapters, official website/product capture, key-person structure, publish-field coverage, and XLSX-backed E2E acceptance.

### Modified Capabilities

- None. Company requirements have not yet been migrated into active OpenSpec specs; this change creates the first Company enrichment closure capability.

## Impact

- Affected code: `apps/miroflow-agent/src/data_agents/company/`, `apps/miroflow-agent/scripts/run_company_*.py`, Company release/contracts, and related tests.
- Affected storage: may require additive migration(s) for product/enrichment evidence or publishable fields if existing tables cannot safely represent them.
- Affected E2E: `scripts/run_company_import_e2e.py`, `scripts/run_company_release_e2e.py`, news/signal/narrative scripts, Milvus backfill, and `/api/chat` or retrieval smoke checks where available.
- Source data: `docs/专辑项目导出1768807339.xlsx` is the required real XLSX E2E input and must not be modified.
