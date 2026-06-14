## ADDED Requirements

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
