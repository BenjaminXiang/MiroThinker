## ADDED Requirements

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
