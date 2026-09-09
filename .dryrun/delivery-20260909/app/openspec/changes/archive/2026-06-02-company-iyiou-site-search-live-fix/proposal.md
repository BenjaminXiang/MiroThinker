## Why

The archived Company enrichment closure introduced a named Yiou adapter, but live validation showed the first company returned zero Yiou rows. Investigation found the root cause: the adapter delegated to Serper's `/news` endpoint with news-keyword query tails. Yiou company/profile/product/funding pages are often ordinary web-search organic results under `data.iyiou.com`, not Google News results.

## What Changes

- Clarify that Yiou enrichment means Web Search constrained by `site:data.iyiou.com`, not a native Yiou API or direct Yiou crawler.
- Route Yiou discovery through Serper web search organic results instead of the news endpoint.
- Add PitchHub discovery through Web Search constrained by `site:pitchhub.36kr.com`, using the same source-adapter pattern as Yiou.
- Generate source-specific query terms from the XLSX company name, normalized name, project name, description-derived aliases, founder names, and domain keywords.
- Fetch accepted PitchHub project and organization pages through the reader fallback so financing, product, industrial/commercial, and team sections can become enrichment evidence.
- Keep generic company news discovery on the existing Serper news endpoint.
- Update live E2E validation to scan a bounded sample of companies and report aggregate Yiou hit counts instead of treating the first company as representative.
- Keep `source_adapter='iyiou'` or `source_adapter='pitchhub_36kr'` and extraction diagnostics on accepted source records.

## Capabilities

### Modified Capabilities

- `company-enrichment-source-closure`: clarify and strengthen Yiou/PitchHub site-filter web-search behavior and live validation.

## Impact

- Affected code: `apps/miroflow-agent/src/data_agents/company/news_connectors/serper.py`, `news_connectors/iyiou.py`, `news_connectors/__init__.py`, `scripts/run_company_news_ingest.py`, `scripts/run_company_enrichment_e2e.py`.
- Affected tests: company Serper connector tests, company news ingest CLI tests, company enrichment E2E script tests.
- Affected runtime: Yiou and PitchHub live discovery should use Serper `/search` organic results with site filters, improving company profile/product/funding page discovery while preserving source provenance.
