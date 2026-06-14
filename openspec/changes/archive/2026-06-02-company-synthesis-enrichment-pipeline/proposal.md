## Why

Company records imported from XLSX are currently usable as identity data but the
Company domain still treats most rows as review-gated because enrichment quality
is tied to generated narratives and source-backed product rows. Operators need
the XLSX baseline to publish automatically while crawled evidence enriches
products, scenarios, customer targets, financing updates, team structure, and
retrieval text with explicit provenance.

The existing Yiou/PitchHub and official-site work also lacks a single synthesis
contract. This change defines the upload-scoped, source-tiered, LLM-assisted
pipeline that turns trusted XLSX data plus official/high-quality crawled sources
and gated generic web search into publishable company business facts.

## What Changes

- Treat XLSX company baseline fields as trusted publish input for company
  identity and base profile readiness.
- Separate company base publish status from review status for products,
  application scenarios, and external-source signal events.
- Fix company detail/release summary semantics so synthesized
  `company.profile_summary` and `company.technology_route_summary` are exposed
  before falling back to XLSX snapshot `description` and `business`.
- Generate longer company profiles suitable for both detail display and RAG
  retrieval; keep XLSX fields as source facts and use LLM only for synthesis,
  structuring, and attribution.
- Structure XLSX `team_raw` into key-person facts with role, background,
  experience highlights, and company/product relevance while preserving raw
  text.
- Extract products, product descriptions, product category, technical tags,
  target customers, and application scenarios from XLSX description/business
  plus official website materials when external sources miss.
- Crawl official websites for companies with websites, collecting bounded
  homepage/about/product/service/solution/case/customer/news pages as high-trust
  synthesis material.
- Keep Yiou and 36Kr/PitchHub as high-quality source adapters for products,
  financing, project profiles, and team evidence.
- Change generic Serper web search to identity queries only: company full name,
  registered name, XLSX project/short name, and trusted LLM-extracted aliases.
  Generic queries MUST keep `gl="cn"` and `hl="zh-cn"`.
- Add a ReAct-style two-step generic web search workflow: search snippets first,
  fetch full pages only when LLM judges snippets insufficient, then LLM-gate
  company identity and fact attribution before any source material is accepted.
- Use the system LLM profile configured for this rollout as an
  OpenAI-compatible DeepSeek endpoint, with `deepseek-v4-pro` as the active
  non-thinking synthesis model and credentials supplied through environment
  variables.
- Allow crawled financing evidence to create newer funding signals when the
  source is attributable to the company and newer than the XLSX funding
  baseline; uncertain or conflicting financing remains review-gated.
- Add per-company query, fetch, source-judgment, synthesis, and miss-reason
  audit records so operators can explain why a company did or did not enrich.
- Refresh only touched company vectors so long profile text, products,
  scenarios, target customers, team structure, and financing updates are
  available to RAG.
- Explicitly exclude recruiting/job-trend extraction from this change.

## Capabilities

### New Capabilities

- `company-synthesis-enrichment-pipeline`: Upload-scoped Company synthesis
  pipeline covering trusted XLSX publishing, source-tiered crawling, generic
  web-search gating, long narratives, team structuring, products, scenarios,
  target customers, financing updates, audit, and retrieval refresh.

### Modified Capabilities

- `company-enrichment-source-closure`: Clarifies that generic web search uses
  identity-only queries and LLM source judgment, while Yiou/PitchHub and
  official websites remain high-trust source adapters for synthesis material.

## Impact

- Affected code: company import quality promotion, company narrative synthesis,
  team parsing/structuring, official website crawling, Yiou/PitchHub and Serper
  connectors, company source-product extraction, company signal extraction,
  upload enrichment batch runner, admin-console company APIs/detail page,
  company vectorizer/Milvus backfill, and chat context.
- Affected storage: existing `company`, `company_snapshot`,
  `company_team_member`, `company_product`, `company_product_evidence`,
  `company_application_scenario`, `company_application_scenario_evidence`,
  `company_signal_event`, `company_news_item`, and enrichment batch/search
  audit tables. New audit or source-material tables MAY be added if existing
  tables cannot represent ReAct decisions and synthesis provenance cleanly.
- Affected dependencies: ReAct-style workflow may be implemented with a bounded
  lightweight tool-call loop using existing OpenAI/http clients, or with
  LangChain/LangGraph if the implementation proves that the dependency is
  justified and controllable in batch jobs.
- Affected validation: focused unit tests, contract/API tests, connector/query
  tests, script tests, OpenSpec validation, a bounded 100-company dry-run or
  limited write validation, and RAG smoke checks on touched company IDs.
