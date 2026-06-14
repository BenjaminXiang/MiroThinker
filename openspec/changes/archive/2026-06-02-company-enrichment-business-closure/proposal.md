## Why

Yiou and PitchHub site-filter discovery now returns company-confirmed source evidence, but the evidence is not yet closed into the Company business surfaces. Operators still cannot reliably see recent financing/product signals on company detail pages, and RAG can miss newly enriched company facts until products, events, and vectors are refreshed together.

## What Changes

- Convert accepted Yiou/PitchHub `company_news_item` rows into `company_signal_event` rows for financing, product, partnership, team, award, and milestone-style signals.
- Extract product/service candidates from accepted source-profile body text and persist them into `company_product` plus `company_product_evidence`.
- Expose recent events, products, source URLs, fetched timestamps, and evidence on company release/detail API payloads used by the admin console.
- Include product and event snippets in the company Milvus payload so RAG can answer questions about recent financing and products.
- Add scripts and E2E checks that run the source ingest, signal extraction, product extraction, company Milvus refresh, and company/chat smoke checks in a bounded, resumable way.
- Add upload-scoped enrichment batch state, per-company checkpoints, query/miss audit, official-site product capture integration, LLM fallback extraction, stale-run cleanup, and product/scenario review actions.

## Capabilities

### New Capabilities

- `company-enrichment-business-closure`: closes source-discovered company enrichment into events, products, release/detail surfaces, and retrieval refresh.

### Modified Capabilities

- `company-enrichment-source-closure`: source evidence discovered from Yiou/PitchHub must be consumable by downstream event/product/retrieval pipelines, not only inserted as raw news rows.

## Impact

- Affected code: company signal/product extraction modules and scripts, admin-console company domain APIs, frontend company detail rendering, Milvus company backfill, and chat/retrieval smoke paths.
- Affected storage: existing `company_news_item`, `company_signal_event`, `company_product`, and `company_product_evidence` tables plus new enrichment batch/checkpoint/search-audit/review-action tables.
- Affected validation: focused unit tests, script tests, OpenSpec strict validation, bounded live DB/source E2E, company Milvus dry-run or refresh, and company chat smoke queries.
