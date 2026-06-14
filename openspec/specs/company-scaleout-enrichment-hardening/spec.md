# company-scaleout-enrichment-hardening Specification

## Purpose
TBD - created by archiving change company-scaleout-enrichment-hardening. Update Purpose after archive.
## Requirements
### Requirement: Company enrichment SHALL use a 200-company scaleout gate
The system SHALL provide an upload-scoped Company enrichment validation path that processes a deterministic 200-company sample before any full XLSX-scale live enrichment is attempted.

The sample SHALL be selected from imported XLSX-backed company rows and SHALL preserve traceability to the upload task, import batch, selected company IDs, source XLSX path, selection criteria, and run scope.

The validation SHALL include dry-run and live bounded modes. Live mode SHALL persist enrichment outputs only for selected companies and SHALL refresh vectors only for touched company IDs.

#### Scenario: 200-company dry-run reports selected scope
- **WHEN** an operator runs the scaleout validation in dry-run mode for 200 companies
- **THEN** the report contains the selected company count, selected company IDs or a durable selection artifact, XLSX source path, selection criteria, enabled stages, skipped stages, and expected write counts
- **AND** no products, scenarios, signal events, source rows, or vectors are written

#### Scenario: 200-company live run stays bounded
- **WHEN** an operator runs the scaleout validation in live mode for the selected 200-company sample
- **THEN** the pipeline writes enrichment outputs only for companies in that sample
- **AND** vector refresh is restricted to the touched company IDs
- **AND** the report states that no full XLSX-scale enrichment was attempted

### Requirement: Official-site capture SHALL use layered acquisition and failure taxonomy
The system SHALL capture official-site source material with a layered strategy: normalized official URL, static fetch, sitemap discovery, navigation discovery, common-path probing, and JavaScript-rendering fallback for empty, short, or SPA-shell static pages.

Official-site capture SHALL stay within the company-owned host unless an explicitly trusted redirect is recorded. It SHALL NOT bypass CAPTCHA, login walls, paywalls, robots restrictions, or bot challenges.

Each official-site attempt SHALL persist or report acquisition method, URL, HTTP status when available, content length, text length, page category, accepted/rejected status, and one normalized failure reason when no material is accepted.

Failure reasons SHALL include at least `no_website`, `invalid_url`, `dns_failed`, `timeout`, `http_403`, `http_429`, `captcha_or_bot_challenge`, `robots_disallowed`, `js_required`, `js_render_failed`, `text_too_short`, `no_relevant_pages`, `identity_mismatch`, `noise_page`, and `fetch_failed`.

#### Scenario: JavaScript site uses rendering fallback
- **WHEN** static official-site fetch returns a valid page that contains only a SPA shell or insufficient text
- **THEN** the pipeline attempts a bounded JavaScript-rendering fallback
- **AND** accepted rendered content records `acquisition_method` as a rendered method
- **AND** failure records `js_required` or `js_render_failed` instead of silently reporting no products

#### Scenario: blocked site records compliance-safe failure
- **WHEN** an official site returns a bot challenge, CAPTCHA page, login requirement, paywall, robots disallow, HTTP 403, or HTTP 429
- **THEN** the pipeline records the corresponding failure reason
- **AND** the pipeline does not attempt to bypass the restriction
- **AND** downstream synthesis may continue with XLSX, Yiou, PitchHub, and accepted generic web materials

### Requirement: Source facts SHALL pass LLM quality gates before persistence
The system SHALL require LLM source judgment before generic web material can feed products, application scenarios, financing signals, recent dynamics, profile summaries, technology-route summaries, or vector text.

Source judgment SHALL confirm target-company identity and fact attribution. Product and scenario persistence SHALL confirm that the product, service, or application scenario belongs to the target company, not to an investor, customer, competitor, similar project, related article, or platform recommendation.

Accepted facts SHALL retain source tier, source URL, evidence span, LLM judgment status, confidence or quality status, and trust reason. Rejected facts SHALL retain rejection reason and source evidence when available.

#### Scenario: unrelated same-industry result is rejected
- **WHEN** web search returns a page about a different company in the same industry
- **THEN** LLM source judgment rejects the source with an identity or attribution reason
- **AND** no product, scenario, funding event, profile sentence, or vector text from that source is persisted for the target company

#### Scenario: source-backed product is persisted with evidence
- **WHEN** accepted source material explicitly describes a product offered by the target company
- **THEN** the persisted product includes product name, product description, product category, technical tags, target customers, and application scenarios when present
- **AND** product evidence links back to the source URL, source tier, evidence span, and judgment result

### Requirement: LLM model routing SHALL distinguish low-risk and judgment-sensitive tasks
The system SHALL route LLM tasks by risk and SHALL expose the selected model in auditable runtime configuration.

`deepseek-v4-lite` MAY be used for low-risk search hint generation, identity alias extraction, and short trusted-XLSX structuring. `deepseek-v4-pro` SHALL be used for snippet triage, source judgment, generic product admission, product ownership attribution, financing extraction, financing conflict or newer-round judgment, multi-source profile synthesis, technology-route synthesis, and quality audit.

The system SHALL NOT use a `lite_then_pro` cascade for snippet triage, generic product admission, or financing extraction.

#### Scenario: judgment-sensitive task uses pro model
- **WHEN** the pipeline runs source judgment, product admission, or financing extraction
- **THEN** the LLM profile resolver selects `deepseek-v4-pro`
- **AND** the audit record identifies the task type and model profile without logging credentials

#### Scenario: rejected cascade baseline remains disabled
- **WHEN** the pipeline runs snippet triage, generic product admission, or financing extraction
- **THEN** the task does not first call a lite model as a gate before pro execution

### Requirement: LLM and web stages SHALL be concurrent, rate-limited, and resumable
The system SHALL provide configurable concurrency for LLM and web-heavy stages. Each stage SHALL have timeout, retry, rate-limit, and maximum-work settings suitable for bounded batch execution.

The pipeline SHALL persist per-company and per-stage checkpoint state. Rerunning a batch SHALL skip succeeded stages by default, SHALL resume failed or pending work when requested, and SHALL NOT create duplicate source materials, products, scenarios, signal events, batch states, or vector refresh rows.

#### Scenario: interrupted batch resumes without duplicates
- **WHEN** a 200-company enrichment batch is interrupted after some companies complete official-site capture and product synthesis
- **THEN** a resume run skips completed stages by default
- **AND** pending or failed stages continue from checkpoint state
- **AND** persisted products, scenarios, signal events, source rows, and vectors remain idempotent

#### Scenario: concurrency settings are bounded
- **WHEN** an operator starts the enrichment batch with configured stage concurrency
- **THEN** the runner applies per-stage concurrency, timeout, retry, and rate-limit settings
- **AND** the final report includes the configured values and observed failure counts

### Requirement: Company enrichment diagnostics SHALL be visible to operators
The admin console SHALL expose upload-scoped Company enrichment status at batch level and company level.

The pipeline or company detail surfaces SHALL show current stage, processed/succeeded/failed counts, last error, source counts by tier, official-site failure reason, accepted/rejected source counts, product count, scenario count, funding event count, summary generation status, vector refresh status, source URLs, and update time when available.

Review status SHALL be separated from company base publish status. XLSX-backed company base readiness SHALL NOT be blocked merely because external products, scenarios, or generic web facts need review.

#### Scenario: operator can inspect missing products
- **WHEN** a company has no accepted product after enrichment
- **THEN** the operator can see whether the cause was no website, official-site fetch failure, no relevant pages, all external sources rejected, LLM rejection, synthesis produced no product facts, or persistence failure

#### Scenario: company detail uses enriched summaries first
- **WHEN** a company has synthesized `profile_summary` or `technology_route_summary`
- **THEN** the company detail page displays those synthesized fields before falling back to XLSX snapshot description or business text
- **AND** products, application scenarios, and recent dynamics display below basic information with source links when available

### Requirement: Scaleout validation SHALL produce evidence for data quality and RAG readiness
The 200-company validation report SHALL include coverage and quality metrics for imported companies, selected companies, baseline-ready records, official-site attempts, official accepted materials, Yiou accepted materials, PitchHub accepted materials, generic web accepted and rejected materials, products, application scenarios, target customers, funding events, structured team rows, long profiles, technology summaries, touched-vector refresh, RAG smoke checks, and miss reasons.

RAG validation SHALL use refreshed touched-company vectors and SHALL include representative questions about products, application scenarios, target customers, recent financing, and company profile summaries.

#### Scenario: validation report distinguishes gaps from success
- **WHEN** the 200-company validation finishes
- **THEN** the report includes passed counts, skipped checks, failed checks, blocker reasons, and residual risks
- **AND** missing official-site material is categorized by failure reason instead of being reported as generic absence

#### Scenario: touched companies answer RAG smoke questions
- **WHEN** vectors are refreshed for touched companies after live validation
- **THEN** RAG smoke checks can retrieve source-backed company context for sampled product, scenario, target-customer, and financing questions
- **AND** the report includes the query, retrieved company IDs, source-backed answer status, and any retrieval failure reason

