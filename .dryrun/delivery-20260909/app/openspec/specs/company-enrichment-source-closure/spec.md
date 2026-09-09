# company-enrichment-source-closure Specification

## Purpose
Define the Company-domain enrichment closure contract for optional publish fields, structured key-person background, named Yiou enrichment, official website product capture, and XLSX-backed E2E acceptance.
## Requirements
### Requirement: Company release exposes PRD-listed optional publish fields

The Company release contract MUST expose `credit_code`, `legal_representative`, `registered_capital`, and `patent_count` when those values are present in the imported or canonical company data. These fields MUST remain optional and MUST NOT become required for release eligibility.

The release object MUST include the same optional fields in `core_facts` so downstream retrieval, admin APIs, and exports can consume them consistently.

#### Scenario: XLSX optional fields are published

- **GIVEN** a company import record has a credit code, legal representative, registered capital, and patent count
- **WHEN** company release generation runs
- **THEN** the resulting `CompanyRecord` contains those optional fields
- **AND** the corresponding `ReleasedObject.core_facts` contains the same values
- **AND** the record remains valid when any of those optional values are absent

### Requirement: Company key persons preserve structured background

The Company key-person structure MUST support `name`, `role`, `description`, `education_structured`, and `work_experience`. Extraction from XLSX team raw text MUST preserve the person introduction as `description` when available.

The extractor MUST use conservative deterministic hints for education and work experience. It MUST NOT invent degree, institution, employer, or role values that are not present in the source text.

#### Scenario: Team intro becomes key-person background

- **GIVEN** XLSX team raw text contains a person name, role, and introduction
- **WHEN** company release generation extracts key personnel
- **THEN** the key person contains `name` and `role`
- **AND** the introduction is preserved in `description`
- **AND** any education or work hints come only from source text spans

### Requirement: Yiou enrichment is a named source adapter

The Company enrichment pipeline MUST provide a named Yiou adapter for `data.iyiou.com` content. The adapter MAY reuse generic search and article-fetch infrastructure, but accepted records MUST identify Yiou as the source adapter and retain source URL, fetched timestamp, extraction status, and diagnostics.

Yiou records MUST be stored or emitted as additive enrichment evidence. They MUST NOT overwrite XLSX/canonical identity fields without explicit high-confidence evidence and a separate canonical update rule.

#### Scenario: Yiou adapter emits source-specific evidence

- **GIVEN** a company name and a Yiou article result from `data.iyiou.com`
- **WHEN** the Yiou enrichment adapter fetches and normalizes the item
- **THEN** the emitted record identifies the adapter as `iyiou`
- **AND** it retains the article URL and extracted text or snippet
- **AND** failures are represented as diagnostics rather than silent success

### Requirement: Official website product capture stores product evidence

The Company pipeline MUST provide a bounded official-site product capture path for companies with a website. The crawler MUST stay within the official host unless explicitly configured otherwise and MUST use page, depth, and URL-pattern limits.

Extracted product records MUST include a product name or category-like label, a short description when present, source URL, evidence span, confidence, and quality status. Low-confidence or page-only product records MUST remain reviewable and MUST NOT be promoted as verified product facts.

#### Scenario: Official product page creates a product record

- **GIVEN** an official company website page contains a product name and description
- **WHEN** official product capture runs for the company
- **THEN** the pipeline writes or emits a product record linked to the company
- **AND** the product record includes source URL, evidence span, confidence, and quality status
- **AND** the crawler does not fetch unbounded external domains

### Requirement: Company XLSX E2E proves enrichment closure

The change MUST include an E2E validation path using `docs/专辑项目导出1768807339.xlsx`. The E2E MUST cover import, release, key-person structure, optional publish fields, enrichment/product capture where prerequisites are available, and a retrieval or release smoke check.

The E2E report MUST distinguish passed deterministic checks from skipped live external checks. It MUST NOT claim complete company enrichment if Yiou, official-site, product, or retrieval checks are skipped or fail.

#### Scenario: Real XLSX E2E reports pass and gaps

- **GIVEN** the real XLSX file exists at `docs/专辑项目导出1768807339.xlsx`
- **WHEN** the company E2E validation runs
- **THEN** the report includes parsed company count, release count, optional-field coverage, key-person structured coverage, Yiou enrichment results or blocker, product capture results or blocker, and retrieval/release smoke result
- **AND** any skipped external check includes the command, blocker, confidence impact, and next best command

### Requirement: Source-backed Company facts SHALL remain traceable through API and release

Accepted Company source facts SHALL remain traceable when exposed through Company detail APIs and release payloads. For source-backed products, application scenarios, recent dynamics, financing events, profile summaries, and technology-route summaries, the exposed payload SHALL include available source URL or stable XLSX source identifier, source type or source tier, capture or update timestamp, and field-level evidence/support metadata.

If a fact is visible to users but source metadata is unavailable, the API or release audit SHALL report the missing metadata as an acceptance failure.

#### Scenario: Source-backed product retains evidence at boundary
- **WHEN** a Company product is visible in a Company detail API response or release payload
- **THEN** the visible product includes source metadata when source evidence exists in storage
- **AND** missing source metadata is reported by the evidence/source audit

#### Scenario: XLSX-derived fact uses stable source identifier
- **WHEN** a Company profile or product fact is derived from trusted XLSX baseline material
- **THEN** the exposed evidence identifies the XLSX source or import batch
- **AND** the fact does not require an external URL to satisfy source traceability

### Requirement: Review-gated Company facts SHALL follow source-confidence policy

Company source facts SHALL be published according to source confidence, company identity confirmation, and fact attribution. Facts from trusted XLSX baseline, official-site material, or accepted high-quality sources MAY appear in default detail and retrieval surfaces when identity and attribution evidence pass. Facts from weak generic web material, unresolved attribution, conflicts, or rejected candidates MUST remain review-gated and excluded from default retrieval text.

The policy SHALL preserve the original review state and evidence so operators can audit or override individual facts later.

#### Scenario: Trusted fact is publishable with audit state
- **WHEN** a product, scenario, or signal is derived from trusted XLSX, official-site, Yiou, PitchHub, or source-judged material with target-company attribution
- **THEN** the fact can appear in default user-facing Company surfaces
- **AND** the audit payload still exposes its source and review status

#### Scenario: Weak generic fact is excluded
- **WHEN** a source fact has weak identity evidence or unresolved ownership attribution
- **THEN** it is excluded from default Company detail and retrieval payloads
- **AND** it remains visible only through review or diagnostic surfaces

### Requirement: Official source closure MUST include acquisition diagnostics
The Company source-closure pipeline MUST treat official website capture as high-trust source-material acquisition, not only as direct product extraction.

Official source material MUST retain URL, title, captured text or text summary, capture time, acquisition method, source tier, trust reason, accepted/rejected status, and failure reason when capture fails. Source closure MUST distinguish unavailable official sources from sources that were available but produced no product, scenario, financing, or profile facts.

#### Scenario: official source material captures non-product business pages
- **WHEN** official website discovery accepts an about, solution, customer, case, news, service, or product page
- **THEN** the source material is available to profile summary, technology-route summary, product synthesis, scenario synthesis, financing extraction, and vector text builders
- **AND** the material records acquisition diagnostics and source tier `official_site`

#### Scenario: official source failure remains auditable
- **WHEN** official website capture cannot produce accepted material
- **THEN** the source closure output records a normalized failure reason and the last meaningful acquisition diagnostic
- **AND** the pipeline can continue with XLSX baseline, Yiou, PitchHub, and accepted generic web sources

### Requirement: Site-search source closure MUST preserve search and judgment provenance
The Yiou, 36Kr/PitchHub, and generic web source paths MUST preserve query text, query type, locale settings where applicable, result count, accepted count, rejected count, rejection reasons, source URL, adapter name, and LLM source-judgment evidence.

Generic web search MUST remain identity-query based and MUST use `gl="cn"` and `hl="zh-cn"` in Serper requests. Yiou and 36Kr/PitchHub site-filter searches MAY use broader recall terms such as trusted aliases, project names, founders, and distinctive XLSX keywords, but those terms alone MUST NOT satisfy source acceptance.

#### Scenario: generic web query remains identity-only
- **WHEN** generic Serper discovery runs for a company
- **THEN** generated queries contain only canonical name, registered name, XLSX company/project name, stored aliases, or trusted LLM identity aliases
- **AND** the Serper request payload includes `gl="cn"` and `hl="zh-cn"`
- **AND** product, financing, founder, industry, recruiting, and site-filter tails are not appended to generic queries

#### Scenario: high-quality site search uses broader recall but separate acceptance
- **WHEN** Yiou or 36Kr/PitchHub search uses alias, founder, project name, or distinctive XLSX keyword recall terms
- **THEN** the accepted source still requires site/domain checks plus target-company identity and fact-attribution checks
- **AND** the source closure audit records the recall query separately from the acceptance evidence

### Requirement: Source closure MUST protect published facts from source pollution
The Company source-closure pipeline MUST prevent unrelated companies, related articles, investors, customers, competitors, similar projects, page recommendations, and platform news lists from creating products, scenarios, financing events, profile facts, or vector text for the target company.

Facts from XLSX and official owned sources MAY become ready when explicit evidence supports them. Facts from generic web sources MUST remain review-gated unless source judgment confirms target-company identity, fact attribution, and strong evidence. Review state MUST remain independent from XLSX-backed company base publish readiness.

#### Scenario: related-page pollution does not enter product facts
- **WHEN** a source page contains target-company text plus related articles or recommendations about other companies
- **THEN** the extractor does not persist products or scenarios from unrelated page sections
- **AND** rejected candidates retain a pollution or attribution failure reason

#### Scenario: generic source product remains review-gated without strong evidence
- **WHEN** a generic web source mentions a product category but does not clearly attribute the product to the target company
- **THEN** the product candidate is rejected or persisted as review-gated according to the judgment result
- **AND** company base publish status remains based on XLSX readiness, not the product review state

### Requirement: Generic Serper source discovery uses identity-only queries

Generic Serper source discovery MUST generate queries only from company identity
terms: canonical company name, registered name, trusted XLSX project or short
name, and trusted LLM-extracted aliases. It MUST NOT append product, financing,
founder, recruiting, job, or industry keyword tails by default.

Yiou and 36Kr/PitchHub site-specific discovery MAY continue using project names,
aliases, founders, and distinctive keywords to broaden recall, but those terms
MUST NOT prove company identity by themselves. Accepted source rows MUST still
pass domain/path constraints and company identity checks.

All Serper payloads in this source-discovery path MUST include `gl='cn'` and
`hl='zh-cn'`.

#### Scenario: Generic query does not add news tail
- **GIVEN** a company named `深圳示例科技有限公司`
- **WHEN** generic Serper source discovery builds a query
- **THEN** the query is `深圳示例科技有限公司`
- **AND** it does not include `融资`, `发布`, `产品`, `招聘`, founder names, or industry keywords
- **AND** the Serper payload includes `gl='cn'` and `hl='zh-cn'`

#### Scenario: Site-specific query can broaden recall without proving identity
- **GIVEN** a PitchHub search uses alias plus founder to find a project page
- **WHEN** a result is returned
- **THEN** the result is accepted only if source domain, path, and company identity checks pass
- **AND** product keywords or founder names alone do not prove the result belongs to the company

### Requirement: Generic web source material requires LLM source judgment

Generic web search results MUST NOT be written as accepted source material or
used in synthesis until an LLM source-judgment step confirms both target-company
identity and fact attribution. The judgment MUST record accepted, rejected, or
needs-review status with a reason and evidence span.

The source workflow MUST inspect snippets before fetching full pages. It MUST
fetch full page text only when the snippet is potentially relevant but
insufficient for product, financing, application scenario, target customer,
team, or profile facts.

#### Scenario: Snippet-only rejection
- **GIVEN** a generic Serper result snippet clearly describes a different company
- **WHEN** source judgment evaluates the snippet
- **THEN** the result is rejected without fetching the page body
- **AND** the audit records `company_identity_failed`

#### Scenario: Full page accepted after snippet is insufficient
- **GIVEN** a generic Serper result snippet mentions the target company but lacks product details
- **WHEN** source judgment marks the snippet insufficient
- **THEN** the workflow fetches the page body
- **AND** the full page is accepted only if LLM judgment confirms company identity and fact attribution

### Requirement: Yiou site-filter discovery uses web-search organic results

The Company Yiou enrichment adapter MUST treat Yiou as a web-search site-filter source over `data.iyiou.com`. The adapter MUST NOT claim a native Yiou API or direct Yiou crawler.

Yiou discovery MUST use a web-search endpoint that returns organic web results for `site:data.iyiou.com`. Generic company news discovery MAY continue to use a news-search endpoint.

Yiou discovery MUST NOT apply news-style recency-only search filters by default because Yiou company/profile/product/funding pages may be older source pages that still provide current enrichment evidence.

Yiou discovery MUST search both the canonical or registered company name and a normalized company-name alias when those terms differ.

Accepted Yiou records MUST retain `source_adapter='iyiou'`, source URL, and extraction diagnostics. The adapter MUST still reject results whose URL is outside `data.iyiou.com`. The adapter MUST reject generic Yiou landing/list pages, such as the site root or company index, and accept only detail-like Yiou evidence paths.

Accepted Yiou records MUST be company-confirmed by matching the returned title, snippet, or fetched text against the company name or a normalized alias.

The Company enrichment live-search flow MUST derive query context from available XLSX and snapshot fields, including the registered company name, normalized company name, project name, description-derived aliases, founder names, and domain keywords when available.

Description-derived aliases MUST require explicit alias markers such as short name, brand name, or project name. Generic product, service, technology, platform, or malformed phrase fragments MUST NOT be emitted as standalone aliases.

#### Scenario: Yiou profile page is found through organic search

- **GIVEN** Serper web search returns an organic result at `https://data.iyiou.com/company/details/...`
- **WHEN** the Yiou adapter processes the result
- **THEN** the emitted record has `source_adapter='iyiou'`
- **AND** the emitted record keeps the Yiou source URL and snippet or fetched text
- **AND** the query does not append generic news-keyword tails that suppress company profile results
- **AND** the query does not apply a news-style recency-only search filter by default
- **AND** normalized-name fallback queries are attempted when the registered name returns no records or incomplete records

#### Scenario: Yiou record is found by normalized-name fallback

- **GIVEN** the registered company name returns no Yiou organic result
- **AND** the normalized company name returns a Yiou company detail result
- **WHEN** the Yiou adapter processes the company
- **THEN** the normalized-name result is accepted
- **AND** diagnostics report query terms and record counts by query

#### Scenario: Generic Yiou pages are not accepted as company evidence

- **GIVEN** Serper web search returns `https://data.iyiou.com/` or `https://data.iyiou.com/company`
- **WHEN** the Yiou adapter processes the results
- **THEN** those generic pages are rejected
- **AND** diagnostics report the generic-path rejection count

#### Scenario: Name-mismatched Yiou detail page is rejected

- **GIVEN** Serper web search returns a Yiou detail path whose title, snippet, and fetched text do not mention the target company or normalized alias
- **WHEN** the Yiou adapter processes the result
- **THEN** the result is rejected
- **AND** diagnostics report the name-mismatch rejection count

#### Scenario: Live validation samples multiple companies

- **GIVEN** a live Yiou validation run has `--live-limit 20`
- **WHEN** the validation runs against the XLSX company list
- **THEN** it reports `companies_checked`, `companies_with_yiou_records`, `iyiou_records`, and per-company samples
- **AND** zero results for one company do not imply the adapter failed globally

#### Scenario: Description and founder context produce source-search query terms

- **GIVEN** an XLSX company record has a registered name, normalized name, description, project name, and founder team rows
- **WHEN** the live source-search context is built
- **THEN** the adapter attempts identity terms such as the registered name and normalized name
- **AND** it may attempt explicit aliases from project or description fields
- **AND** it may attempt alias-plus-founder query terms
- **AND** generic product phrases from the description are not used as company aliases

### Requirement: PitchHub site-filter discovery uses web-search organic results

The Company PitchHub enrichment adapter MUST treat PitchHub as a web-search site-filter source over `pitchhub.36kr.com`. The adapter MUST NOT claim a native PitchHub API.

PitchHub discovery MUST use a web-search endpoint that returns organic web results for `site:pitchhub.36kr.com`. Generic company news discovery MAY continue to use a news-search endpoint.

PitchHub discovery MUST search source context terms derived from the company record, including the canonical or registered company name, normalized company-name alias, project-name alias, description-derived aliases, founder names, and domain keywords when available.

Accepted PitchHub records MUST retain `source_adapter='pitchhub_36kr'`, source URL, and extraction diagnostics. The adapter MUST reject results whose URL is outside `pitchhub.36kr.com` and MUST accept only detail-like PitchHub evidence paths, including `/project/` and `/organization/`.

Accepted PitchHub records MUST be company-confirmed by matching the returned title, snippet, or fetched detail text against the company name or accepted aliases.

Accepted PitchHub detail URLs SHOULD be fetched through the configured reader fallback after URL and company-name acceptance, so detail pages can contribute product, financing, industrial/commercial, and team evidence.

#### Scenario: PitchHub project page is found and enriched through detail fetch

- **GIVEN** Serper web search returns an organic result at `https://pitchhub.36kr.com/project/...`
- **WHEN** the PitchHub adapter processes the result
- **THEN** the emitted record has `source_adapter='pitchhub_36kr'`
- **AND** the emitted record keeps the PitchHub source URL
- **AND** the adapter records detail-fetch attempt and success diagnostics when reader fetch returns body text

#### Scenario: PitchHub discovery uses the same context query strategy as Yiou

- **GIVEN** a company record contains a project or short alias and founder names
- **WHEN** PitchHub discovery runs
- **THEN** the adapter attempts full-name, normalized-name, alias, and alias-plus-founder query terms within the bounded query budget
- **AND** diagnostics report query terms and record counts by query

#### Scenario: PitchHub live validation reports source-level coverage

- **GIVEN** a live validation run has `--live-limit 20`
- **WHEN** the validation runs against the XLSX company list
- **THEN** it reports PitchHub records, companies with PitchHub records, PitchHub content characters, and accepted top URLs separately from Yiou counts

