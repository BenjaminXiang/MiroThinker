# company-synthesis-enrichment-pipeline Specification

## Purpose
TBD - created by archiving change company-synthesis-enrichment-pipeline. Update Purpose after archive.
## Requirements
### Requirement: XLSX baseline publishes company base records

The Company pipeline MUST treat imported XLSX rows as the trusted baseline for
company identity and base profile fields. A company with `identity_status='resolved'`
and sufficient XLSX baseline fields MUST be eligible for `company.quality_status='ready'`
without requiring manual review of products, scenarios, or external-source
enrichment.

The promotion rule MUST evaluate XLSX baseline completeness separately from
external enrichment completeness. Missing products, scenarios, generic web
results, or source-product review actions MUST NOT keep the company base record
in `needs_review`.

Sufficient baseline fields MUST include a company name, a latest company
snapshot, and at least one meaningful business/profile field such as industry,
business, description, region, website, financing baseline, team raw text, or
reported patent count. Malformed imports, unresolved identity, or no meaningful
baseline fields MUST remain reviewable.

#### Scenario: XLSX-backed company is auto-published
- **GIVEN** a company has `identity_status='resolved'`
- **AND** the latest XLSX snapshot contains company name plus industry and description
- **WHEN** company quality promotion runs
- **THEN** `company.quality_status` becomes `ready`
- **AND** products and scenarios for the same company can still remain `needs_review`

#### Scenario: Unresolved company remains reviewable
- **GIVEN** a company has `identity_status!='resolved'`
- **WHEN** company quality promotion runs
- **THEN** `company.quality_status` remains `needs_review`
- **AND** the report records the baseline readiness blocker

### Requirement: Company detail exposes synthesized summaries first

Company detail and release payloads MUST expose `company.profile_summary` and
`company.technology_route_summary` before falling back to latest snapshot
`description` and `business`. The fallback fields MUST remain visible when
synthesized fields are absent.

The company detail page MUST render sections in this order:
`Basic Information`, `Products`, `Application Scenarios`, `Recent Events`.
Products MUST NOT be rendered before basic information. Company pages MUST use
company-domain labels such as `Company Profile` and MUST NOT label company
summary text as `Personal Profile`.

Product display payloads and pages MUST expose only business-facing product
fields: product name, product description, product category, technical tags,
target customers, and application scenarios. Internal source quality fields,
raw extraction diagnostics, and audit keys MUST remain available through audit
or review surfaces rather than the primary company detail page.

#### Scenario: Synthesized summary is visible
- **GIVEN** a company has `company.profile_summary='long synthesized profile'`
- **AND** the latest XLSX snapshot has `description='short XLSX description'`
- **WHEN** the company detail API is requested
- **THEN** `summary_fields.profile_summary` is `long synthesized profile`
- **AND** the XLSX description is not used as the primary profile summary

#### Scenario: Detail sections follow review order
- **GIVEN** a company has products, application scenarios, and recent events
- **WHEN** the admin detail page renders the company
- **THEN** the page shows basic information before products
- **AND** products appear before application scenarios
- **AND** application scenarios appear before recent events

#### Scenario: Company page uses company-domain labels
- **GIVEN** the admin detail page renders a company record
- **WHEN** the summary section is shown
- **THEN** the section label is `Company Profile` or the localized equivalent
- **AND** the page does not label company summary text as `Personal Profile`

#### Scenario: Product display hides audit fields
- **GIVEN** a product has source evidence, quality status, and extraction diagnostics
- **WHEN** the primary company detail page renders the product
- **THEN** it shows product name, product description, product category, technical tags, target customers, and application scenarios
- **AND** it does not show raw audit keys such as `quality_status` or `amount_cny_wan`

### Requirement: Long company profiles feed display and retrieval

The Company synthesis pipeline MUST generate source-grounded long company
profiles suitable for detail display and retrieval. When sufficient material is
available, the generated Chinese `profile_summary` SHOULD target 500-900
characters and MUST preserve factual grounding in XLSX and accepted source
material. Shorter profiles are allowed only when the available source material
is sparse, and the synthesis audit MUST record that blocker.

The company vector text, chat context, and retrieval payload MUST include the
long profile, technology or production-line summary, products, target customers,
application scenarios, structured team highlights, and newer financing signals
when present.

#### Scenario: Long profile is embedded for retrieval
- **GIVEN** synthesis writes a long `company.profile_summary`
- **AND** products, target customers, scenarios, and team highlights are present
- **WHEN** company Milvus backfill composes text for that company
- **THEN** the composed text includes the long profile
- **AND** it includes product, scenario, target-customer, team, and financing snippets

### Requirement: XLSX text can synthesize products and scenarios

When external products or scenarios are missing, the pipeline MUST use trusted
XLSX `description`, `business`, project name, and team context as source
material for LLM product/scenario synthesis. The LLM output MUST be evidence
bound and MUST NOT invent product names, customers, or scenarios absent from
the supplied material.

Synthesis MUST support the product fields `product_name`, `short_description`,
`product_category`, `technical_tags`, `target_customers`, and
`application_scenarios`. Target customers MUST be extracted from product
material plus official website context when available, not guessed solely from
the industry label.

#### Scenario: XLSX description creates a fallback product
- **GIVEN** a trusted XLSX description states that a company provides an AI ECG platform for hospitals
- **AND** no ready product exists for that company
- **WHEN** XLSX product synthesis runs
- **THEN** a company product candidate is produced with product name, description, category, technical tags, target customers, and application scenarios
- **AND** the product evidence references XLSX source material

#### Scenario: Industry-only target customer is rejected
- **GIVEN** the only available field is `industry='医疗AI'`
- **WHEN** product synthesis runs
- **THEN** it MUST NOT set target customer to `医院` unless product or official website material supports that customer

### Requirement: XLSX team raw text is LLM-structured

The pipeline MUST structure XLSX `team_raw` with an LLM into key-person facts
including name, role, background, experience highlights, and company or product
relevance. The raw `team_raw` text MUST remain preserved.

LLM team structuring MUST only use the provided XLSX team text and accepted
source material. Education, employer, title, and founder claims MUST NOT be
invented. Ambiguous persons MUST remain reviewable with the raw evidence span.

#### Scenario: Team raw becomes key-person structure
- **GIVEN** XLSX `team_raw` contains a founder name, role, and introduction
- **WHEN** team structuring runs
- **THEN** the key person includes name, role, background, experience highlights, and source evidence
- **AND** the original `team_raw` remains available

### Requirement: Official websites provide high-trust synthesis material

For every uploaded company with a website, the pipeline MUST run bounded
official-site collection. The crawler MUST stay within the official host and
MUST collect candidate homepage, about, product, service, solution, case,
customer, and news pages when reachable within configured page, URL, depth,
timeout, and character limits.

Official website material MUST be tagged as high-trust source material for
product, scenario, target-customer, long-profile, technology-route, and newer
financing synthesis. Noisy pages, JavaScript placeholders, domain-sale pages,
and unrelated external pages MUST be rejected or marked as unusable.

#### Scenario: Official website contributes target customers
- **GIVEN** an official website solution page describes a product for hospitals and remote diagnosis
- **WHEN** synthesis runs
- **THEN** target customers and application scenarios can be extracted from that official material
- **AND** evidence links point to the official page URL

### Requirement: Generic web search uses ReAct-style gated retrieval

Generic Serper web search MUST use identity-only queries generated from company
full name, registered name, XLSX project or short name, and trusted
LLM-extracted aliases. Generic queries MUST NOT append product, financing,
founder, recruiting, job, or keyword tails by default.

Serper payloads for generic search MUST include `gl='cn'` and `hl='zh-cn'`.

The generic search workflow MUST be ReAct-style: search snippets first, ask the
LLM whether the snippet is sufficient, fetch full page text only when the LLM
marks the snippet as potentially relevant but insufficient, then run LLM source
judgment on company identity and fact attribution before any source material is
accepted for synthesis.

#### Scenario: Full name and short name are searched
- **GIVEN** a company has canonical name `深圳旭宏医疗科技有限公司`
- **AND** trusted alias `旭宏医疗`
- **WHEN** generic web search runs
- **THEN** Serper receives one query for the full name
- **AND** Serper receives one query for the alias
- **AND** both payloads include `gl='cn'` and `hl='zh-cn'`

#### Scenario: Snippet triggers full-page fetch
- **GIVEN** a Serper result snippet mentions the target company but omits product detail
- **WHEN** the ReAct source workflow evaluates the result
- **THEN** it calls the fetch-page tool for that URL
- **AND** it records that snippet information was insufficient

#### Scenario: Generic search result is rejected
- **GIVEN** a generic search result describes a competitor or same-industry company
- **WHEN** LLM source judgment runs
- **THEN** the result is rejected
- **AND** the rejection reason records company identity mismatch or fact attribution failure

### Requirement: LLM synthesis MUST use the configured DeepSeek profile

LLM-backed company synthesis MUST use the shared OpenAI-compatible LLM settings
for this rollout, including source judgment, structured product extraction,
team structuring, and financing extraction. The active model MUST be
`deepseek-v4-pro` with base URL `https://api.deepseek.com`, and credentials
MUST be read from environment variables such as `DEEPSEEK_API_KEY`,
`LOCAL_LLM_API_KEY`, or `ONLINE_LLM_API_KEY`.

Runtime calls SHOULD use non-thinking mode for this rollout unless a later
change explicitly opts into reasoning output.

Implementation code and OpenSpec artifacts MUST NOT hardcode API keys. Runtime
scripts may load ignored local `.env` files when they already use the
repository's dotenv pattern.

#### Scenario: Company synthesis resolves DeepSeek settings
- **GIVEN** `DEEPSEEK_API_KEY` is set in the process environment or loaded local `.env`
- **WHEN** the company synthesis runner opens an LLM client
- **THEN** it uses model `deepseek-v4-pro`
- **AND** it sends requests to `https://api.deepseek.com`
- **AND** the smoke check confirms no reasoning output is returned in
  non-thinking mode
- **AND** no API key is stored in committed source files

### Requirement: Financing updates are evidence-gated

XLSX financing fields MUST remain the baseline financing facts. External
sources MAY create funding signals only when source material is attributable to
the target company and contains explicit financing evidence such as date, round,
amount, investor, or financing summary.

When external evidence is newer than the XLSX latest funding baseline, the
pipeline MUST write a funding signal and expose it as a latest funding candidate
with source evidence. Historical financing MUST be preserved as signal history
without silently overwriting the XLSX baseline. Conflicting or uncertain
financing evidence MUST remain reviewable.

#### Scenario: Newer external financing becomes a signal
- **GIVEN** XLSX says the latest funding was a 2024 angel round
- **AND** an accepted PitchHub or Yiou source states a 2026 A round for the same company
- **WHEN** financing synthesis runs
- **THEN** a `company_signal_event` funding row is created with normalized round, date, amount or investors when available
- **AND** the event source URL is preserved
- **AND** the event is visible in recent dynamics and retrieval text

### Requirement: Synthesis is upload-scoped and resumable

The company synthesis pipeline MUST run from the uploaded XLSX company set by
default. It MUST process companies in bounded chunks, persist per-company stage
state, and support resume by enrichment batch ID without repeating completed
stages unless explicitly requested.

Stages MUST include baseline readiness, XLSX/team synthesis, official-site
source material capture, Yiou/PitchHub source capture, generic web search
source judgment, multi-source synthesis, persistence, and touched-company
vector refresh. Operators MUST be able to skip live web or Milvus stages by
explicit flags for dry-run validation.

#### Scenario: Upload batch resumes without repeating completed companies
- **GIVEN** an enrichment batch has completed XLSX synthesis for one company
- **WHEN** the runner resumes the batch
- **THEN** the completed stage is skipped for that company
- **AND** unfinished stages continue for pending companies

#### Scenario: Operator sees company enrichment progress after upload
- **GIVEN** an admin uploads a company XLSX and the import run has an upload-scoped enrichment batch
- **WHEN** the operator opens the pipeline run detail page
- **THEN** the detail API returns the enrichment batch status, current stage, selected company count, processed count, success count, failure count, timestamps, and last error
- **AND** the frontend renders a company enrichment processing status section
- **AND** the frontend refreshes the detail view while the import run or enrichment batch is still active

### Requirement: Source and synthesis audit is explainable

For each company, the pipeline MUST persist enough audit evidence to explain
query generation, search result counts, snippet sufficiency decisions, page
fetch attempts, source judgment, accepted source material, rejected source
material, synthesis inputs, facts produced, facts rejected, and miss reasons.

Miss reasons MUST distinguish at least `no_results`, `all_results_rejected`,
`fetch_failed`, `llm_rejected`, `synthesis_no_facts`, and `persist_failed`.

#### Scenario: Operator can explain an empty product section
- **GIVEN** a company has no ready products after enrichment
- **WHEN** an operator inspects the batch audit
- **THEN** the audit shows which queries ran
- **AND** it shows whether results were absent, rejected, failed to fetch, rejected by LLM, or produced no product facts

### Requirement: Recruiting and job-trend extraction is excluded

The Company synthesis pipeline MUST NOT extract recruiting, job postings,
role-demand trends, or hiring signals as product, scenario, financing, or core
company facts in this change. Search queries and fetch filters MUST avoid
recruiting/job-intent tails unless a future change explicitly enables that
domain.

#### Scenario: Recruiting page is not accepted
- **GIVEN** a generic web result is a recruiting or job posting page
- **WHEN** source judgment runs
- **THEN** the result is rejected for this change
- **AND** no product, scenario, team, or financing fact is produced from that page

