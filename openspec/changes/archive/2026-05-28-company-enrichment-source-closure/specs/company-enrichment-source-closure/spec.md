## ADDED Requirements

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
