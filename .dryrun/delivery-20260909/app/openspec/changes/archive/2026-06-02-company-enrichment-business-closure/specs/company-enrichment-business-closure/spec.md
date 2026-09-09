## ADDED Requirements

### Requirement: Source news rows produce company signal events

Accepted company source records from Yiou and PitchHub MUST be processable into `company_signal_event` rows when the source body contains clear financing, product, partnership, order, award, expansion, executive, or milestone evidence.

The extraction runner MUST support filtering by `source_adapter` so operators can process Yiou/PitchHub records without reprocessing unrelated news. The runner MUST report processed news count, extracted event count, inserted event count, error count, and per-source-adapter counts.

Each inserted event MUST keep `primary_news_id`, `event_type`, `event_date`, `event_summary`, `confidence`, `dedup_key`, and normalized subject metadata. Duplicate events for the same company/type/dedup key MUST remain idempotent.

#### Scenario: PitchHub financing history becomes a funding signal

- **GIVEN** a company-confirmed `company_news_item` row from `source_adapter='pitchhub_36kr'`
- **AND** the row body contains a dated financing history item
- **WHEN** signal extraction runs for `source_adapter='pitchhub_36kr'`
- **THEN** a `company_signal_event` funding row is inserted or deduped
- **AND** the row references the original `news_id`
- **AND** the extraction report includes PitchHub processed/extracted counts

### Requirement: Source body text produces product records with evidence

Accepted Yiou/PitchHub source body text MUST be extractable into `company_product` rows when the body contains concrete product or service names and descriptions.

Product extraction from source body text MUST write `company_product` through the canonical upsert path and MUST write `company_product_evidence` with source URL, evidence span, confidence, and extractor version.

Product rows extracted from third-party source profiles MUST default to `quality_status='needs_review'` unless a later official source confirms them.

#### Scenario: PitchHub project profile creates product evidence

- **GIVEN** a PitchHub source row for a company contains a project introduction and product/service description
- **WHEN** source-product extraction runs
- **THEN** at least one `company_product` row is written for that company
- **AND** `company_product_evidence.source_url` is the PitchHub detail URL
- **AND** the evidence span quotes the source body section used for extraction

### Requirement: Company detail and release APIs expose enrichment closure fields

Company release/detail payloads MUST expose recent source-backed signal events, product records, and source evidence links so operators can inspect financing/product recency without reading raw JSON only.

The generic domain release object for companies MUST include compact product and recent-event summaries in `core_facts` and MUST include source evidence rows when evidence is requested.

The data helper detail endpoint MUST expose `recent_events`, `products`, and `source_records` or equivalent typed arrays for company detail pages.

#### Scenario: Company detail page shows products and recent events

- **GIVEN** a company has one product, one funding event, and one PitchHub source row
- **WHEN** the company detail API is requested
- **THEN** the response includes the product name and description
- **AND** the response includes the funding event summary and date
- **AND** the response includes the PitchHub source URL and adapter name

### Requirement: Company Milvus refresh includes products and recent events

Company Milvus backfill MUST include product summaries and recent signal-event summaries in the text embedded for `company_profiles`.

The Milvus payload MUST retain compact product and recent-event metadata where the collection schema supports it, and retrieval snippets SHOULD prefer enriched profile/product/event text over empty descriptions.

#### Scenario: RAG can retrieve a product-enriched company

- **GIVEN** a company has a product row and recent funding/product signal events
- **WHEN** company Milvus backfill composes the company text
- **THEN** the composed text includes the product name, product description, event type, event date, and event summary
- **AND** retrieval for a product or recent-financing query can return that company after refresh

### Requirement: Bounded E2E reports closure coverage

The business-closure runbook or script MUST support bounded runs and MUST report counts for source rows, signal events, products, API checks, and Milvus/RAG refresh checks.

#### Scenario: Bounded closure run reports remaining gaps

- **GIVEN** operators run the closure E2E with a limited company sample
- **WHEN** any stage is skipped or unavailable
- **THEN** the report records the skipped stage, blocker, and confidence impact instead of claiming full closure

### Requirement: Company enrichment fields are structured

Company enrichment MUST expose financing, products, and application scenarios as stable structured fields, not only as narrative text.

Funding signals MUST keep normalized financing details in `company_signal_event.event_subject_normalized`, including round, amount, investors, FA information when available, and source provenance. Detail and release APIs MUST expose these normalized financing fields.

Product records MUST support product category, target customer segments, application scenarios, and technical tags. Product extractors MUST persist these fields when source text contains them and keep evidence for the source text used.

Application scenarios MUST be persisted as first-class company rows with source evidence, confidence, quality status, optional related product, scenario category, description, and target customer.

Admin company XLSX upload MUST be the scoped entry point for company enrichment. After upload parsing and canonical import, the pipeline MUST derive the uploaded batch company IDs, enrich only that scoped set by default, use XLSX-derived names/descriptions/team text plus LLM search hints to broaden Yiou/PitchHub web-search queries, and then run source evidence, signal, product, and scenario closure stages for that scoped set.

#### Scenario: Product profile yields structured product and scenario records

- **GIVEN** a Yiou or PitchHub source row describes a product, its customers, and concrete use cases
- **WHEN** source-product extraction runs
- **THEN** `company_product` includes product category, target customers, application scenarios, and technical tags where supported by source text
- **AND** at least one `company_application_scenario` row is inserted or deduped when concrete scenarios are present
- **AND** scenario evidence references the source URL and evidence span

#### Scenario: Company APIs expose structured business fields

- **GIVEN** a company has one funding event, one structured product, and one application scenario
- **WHEN** company detail and release APIs are requested
- **THEN** the response includes financing round/date/amount/investors as structured fields
- **AND** the response includes product category, target customers, application scenarios, and technical tags
- **AND** the response includes application scenario records with evidence URLs

#### Scenario: Uploaded XLSX batch drives scoped enrichment

- **GIVEN** an operator uploads a company XLSX in the admin company page
- **WHEN** the upload pipeline completes canonical import
- **THEN** the pipeline loads company IDs from the new import batch
- **AND** Yiou/PitchHub web-search enrichment commands are scoped to those company IDs
- **AND** search contexts include XLSX project name, description, team text, and LLM-extracted aliases, founders, and keywords when the LLM is available
- **AND** downstream signal and product/scenario extraction only process those scoped company IDs

### Requirement: Uploaded company enrichment is resumable and auditable

Admin company XLSX upload MUST enqueue a company enrichment batch after canonical import instead of running the whole external enrichment chain inline inside the import task. The import task MUST return the enrichment batch id, selected company count, and queued status.

Each enrichment batch MUST persist per-company checkpoint state, current stage, attempts, counters, timestamps, and last error. A batch runner MUST process queued companies in bounded chunks and MUST support resume by batch id without repeating completed stages for a company unless explicitly requested.

Yiou/PitchHub web-search enrichment MUST persist per-company search audit rows that include source adapter, query text, query kind, result count, accepted count, rejection counts, LLM search hints when used, diagnostics, and a miss reason when no source row is accepted.

#### Scenario: Upload import enqueues rather than blocks on external enrichment

- **GIVEN** an operator uploads a company XLSX
- **WHEN** canonical import succeeds
- **THEN** an enrichment batch row is created for that import batch
- **AND** one per-company state row is created for each imported company selected for enrichment
- **AND** the upload import summary reports the enrichment batch as queued
- **AND** the import task does not synchronously run Yiou, PitchHub, signal extraction, source-product extraction, official product capture, or Milvus refresh commands

#### Scenario: Resumable runner records search misses

- **GIVEN** an enrichment batch contains a company with no accepted Yiou/PitchHub result
- **WHEN** the batch runner processes source discovery
- **THEN** search audit rows record every executed query and result count
- **AND** the company checkpoint records a miss reason such as `no_results`, `all_results_rejected`, or `source_fetch_error`
- **AND** rerunning the same batch skips completed companies unless resume options request reprocessing

### Requirement: Upload enrichment includes official websites and retrieval refresh

Upload-scoped company enrichment MUST use uploaded company website data when available. Official-site product capture MUST support canonical company IDs and MUST run in the upload enrichment batch after Yiou/PitchHub source capture.

After product, scenario, and signal extraction completes for a company batch, the runner MUST refresh company Milvus only for the touched company IDs unless the operator passes an explicit skip flag.

#### Scenario: Uploaded official website yields product evidence

- **GIVEN** an uploaded company snapshot includes a website URL
- **WHEN** the upload enrichment batch reaches the official-product stage
- **THEN** official product capture fetches bounded candidate pages for that company id
- **AND** any extracted products are written with official source URLs and evidence
- **AND** the company checkpoint records official-product extracted/inserted counts

#### Scenario: Batch refreshes only touched company vectors

- **GIVEN** a batch processes three company IDs
- **WHEN** Milvus refresh runs
- **THEN** the refresh command is invoked with those three company IDs
- **AND** no unrelated companies are refreshed by that batch

### Requirement: Product and scenario extraction has LLM fallback

Source product/scenario extraction MUST keep deterministic parsing as the first pass. When deterministic parsing returns no candidate for a supported Yiou/PitchHub source body and the configured LLM is available, extraction SHOULD ask the LLM for structured product and scenario candidates using only source text.

LLM fallback MUST return structured product category, target customers, application scenarios, technical tags, scenario descriptions, confidence, and evidence span when supported by source text. Fallback rows MUST default to `quality_status='needs_review'` and MUST not invent unsupported fields.

#### Scenario: LLM fallback extracts a product missed by rules

- **GIVEN** a supported Yiou/PitchHub source body describes a product in a format not matched by deterministic rules
- **WHEN** source-product extraction runs with LLM fallback enabled
- **THEN** a product candidate is inserted with evidence span and `needs_review`
- **AND** any concrete application scenario candidates are inserted with evidence
- **AND** the report marks the extraction source as `llm_fallback`

### Requirement: Enrichment operations support cleanup and review

Operators MUST be able to close stale running enrichment pipeline rows without changing live runs. Cleanup MUST filter by age and optional trigger/run kind, record a terminal status, and preserve error summary explaining the stale cleanup.

Operators MUST be able to accept, reject, or return company product and application scenario rows to review. Review actions MUST update row `quality_status`, write an audit row with actor, action, note, target type, target id, previous status, new status, and timestamp, and preserve extracted evidence rows.

#### Scenario: Stale enrichment run is closed

- **GIVEN** a `pipeline_run` has status `running` and is older than the configured threshold
- **WHEN** stale cleanup runs for the matching trigger/run kind
- **THEN** the run is marked `failed` or `partial` with a stale cleanup error summary
- **AND** newer running rows outside the threshold remain unchanged

#### Scenario: Operator accepts an extracted product

- **GIVEN** a company product has `quality_status='needs_review'`
- **WHEN** an operator accepts the product
- **THEN** the product status becomes `ready`
- **AND** a review action row records the actor, action, previous status, new status, note, and target product id
