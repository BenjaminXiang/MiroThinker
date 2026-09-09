## Context

Yiou content required by the Company domain is public web content on `data.iyiou.com`. The platform does not have a native Yiou API contract and should not claim a direct Yiou crawler. The durable abstraction is a named source adapter that runs web search constrained to the Yiou site and records adapter provenance when writing rows.

Live probing showed:

- Serper `/news` with `site:data.iyiou.com` can return zero results for companies that have Yiou profile pages.
- Serper `/search` with `site:data.iyiou.com` returns organic company detail/profile results for the same queries.
- Organic Yiou company/profile pages can be filtered out by recency-only `tbs` parameters even when the page exists.
- The previous live E2E checked only the first XLSX company, so a no-hit first company made the live check look weaker than the adapter really was.

## Goals / Non-Goals

**Goals:**

- Use web-search organic results for Yiou site-filter discovery.
- Use web-search organic results for PitchHub site-filter discovery.
- Preserve the existing Serper news endpoint for generic recent-news discovery.
- Keep source provenance explicit through `source_adapter='iyiou'` or `source_adapter='pitchhub_36kr'` and diagnostics.
- Use available XLSX fields to build source-search context: registered company name, normalized name, project name, description-derived aliases, founder names, and domain keywords.
- Fetch accepted PitchHub detail pages after URL/name confirmation, so profile/product/funding/team sections can be used by downstream extraction.
- Make live E2E scan multiple companies with a bounded `--live-limit`.

**Non-Goals:**

- Do not reverse-engineer Yiou internals.
- Do not reverse-engineer Yiou or PitchHub internals.
- Do not scrape source pages directly beyond optional body fetch through the generic reader-backed fetch mechanism.
- Do not claim complete Yiou or PitchHub coverage; report hit counts and zero-result samples honestly.

## Decisions

1. Add `SerperSearchConnector` beside `SerperNewsConnector`.
   - Rationale: generic news search and site-filtered source discovery have different result keys and endpoint behavior.
   - `SerperNewsConnector` remains `/news` + `news`.
   - `SerperSearchConnector` uses `/search` + `organic`.
   - `SerperSearchConnector` does not apply news-style recency filters by default because Yiou profile/product/funding pages are source evidence, not necessarily recent news items.

2. Yiou adapter delegates to `SerperSearchConnector`.
   - Rationale: Yiou profile pages are organic web results.
   - The adapter still filters accepted URLs to `data.iyiou.com`.
   - The adapter rejects generic Yiou landing/list pages and keeps only detail-like paths such as company detail, intelligence detail, or news paths.
   - The adapter tries the registered/canonical company name and a normalized company name query because Yiou and search indexes may use short names.
   - The adapter requires the returned title, snippet, or fetched text to mention the company name or normalized alias before accepting the record.

3. Source search context is built from the XLSX import record and latest snapshot fields.
   - Rationale: many source pages are indexed by project or short brand names, not only the legal entity name.
   - Deterministic hints are extracted from descriptions and team rows first.
   - A model-backed hint extractor may provide aliases, founder names, and keywords, but deterministic guards keep generic product phrases such as "product", "service", or broad Chinese nouns from becoming standalone search aliases.
   - Query terms are capped per run to protect external search quota, but there is no source-record count cap once records are found and accepted.

4. PitchHub uses the same site-filter adapter pattern.
   - Rationale: PitchHub pages under `pitchhub.36kr.com/project/...` and `pitchhub.36kr.com/organization/...` contain product, financing, company, and team evidence.
   - PitchHub delegates discovery to `SerperSearchConnector` with `site:pitchhub.36kr.com`.
   - PitchHub accepts only project and organization detail paths, applies the same company-name confirmation rule, and records `source_adapter='pitchhub_36kr'`.
   - Accepted PitchHub detail URLs are fetched through the reader fallback after acceptance, avoiding unnecessary detail fetches for rejected search results.

5. Live E2E scans a sample and reports source-level counts.
   - Rationale: one company may legitimately have zero Yiou rows. Validation should report sample coverage, not binary success on the first company.
   - The report includes per-source record counts, companies with records, content character counts, and top accepted URLs.

## Risks / Trade-offs

- Organic search can return stale or non-company source pages. Mitigation: keep source URL and diagnostics; event/product extraction remains reviewable.
- Alias extraction can over-query if generic phrases are mistaken for company aliases. Mitigation: require explicit alias markers and reject generic or malformed alias candidates.
- Wider live samples consume Serper quota. Mitigation: default `--live-limit=20` and allow smaller limits.
- Search snippets may be insufficient for structured extraction. Mitigation: keep optional article/profile text fetching and treat low-confidence rows as enrichment evidence.

## Migration Plan

No database migration is required. Existing `company_news_item.source_adapter` and `extraction_diagnostics` fields are sufficient.

## Rollback

Revert the connector delegation so Yiou uses the prior Serper news connector. This is safe but reduces Yiou profile-page coverage.
