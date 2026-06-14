## Change Log

### 2026-05-28 Structured Business Fields

- Added explicit scope for structured financing, product, and application-scenario fields.
- Decision: keep financing in `company_signal_event` and normalize its `event_subject_normalized` JSON instead of creating a duplicate funding table.
- Decision: extend `company_product` with product category, target customers, application scenarios, and technical tags.
- Decision: add first-class `company_application_scenario` and `company_application_scenario_evidence` tables for scenario-level search, display, and source audit.
- Added task section 6 for migration/model tests, extractor updates, API/frontend display, Milvus/search integration, and bounded live validation.

### 2026-05-28 Upload-Scoped Enrichment

- Added explicit scope that admin company XLSX upload is the entry point for company enrichment.
- Decision: after canonical import, load company IDs from the upload import batch and run Yiou/PitchHub source discovery plus signal/product/scenario extraction only for those IDs.
- Decision: use uploaded XLSX project name, description, and team text plus optional LLM-extracted aliases/founders/keywords to broaden site-search queries while keeping deterministic source acceptance.

### 2026-05-28 Upload Batch Operations Closure

- Added task section 7 for resumable upload enrichment batches, per-company checkpoints, search miss audit, official-site product capture, LLM fallback extraction, Milvus batch refresh, stale-run cleanup, and product/scenario review actions.
- Decision: admin upload should enqueue external enrichment work and return queued batch metadata instead of synchronously executing the full external web-search chain inside the import task.
- Decision: query diagnostics and miss reasons are operational evidence and must be persisted, not only printed in script output.

### 2026-05-28 Ten Percent Validation Repair

- A 103-company live validation batch exposed systemic operational defects that must be repaired before broader rollout:
  - local-file Milvus URI propagation failed inside batch subprocesses;
  - chunk aggregate counters were copied into every company checkpoint;
  - running batch progress was only visible through company state rows, not the batch row;
  - search audit accepted/rejected counters were aggregate diagnostics repeated per query row;
  - official-site product extraction accepted domain-sale and JavaScript placeholder pages as products.
- Added task section 8 for the validation repair. The scope keeps source discovery, extraction, and review behavior intact, but tightens state, audit, and extraction boundary guards.

### 2026-05-28 Historical Noise Cleanup And 100 Company Revalidation

- While preparing cleanup for the previous 10 percent validation batch, additional official-site product false positives were identified:
  - testimonial or reviewer social handles extracted as product names;
  - call-to-action labels and footer/social-link labels extracted as product names;
  - generic section titles extracted as products.
- Added task section 9 to cover regression tests, additional extraction guards, an auditable cleanup of historical noisy product rows from the previous 10 percent validation batch, and a fresh 100-company validation batch.
- The fresh 100-company validation exposed a source-acceptance defect: product and keyword search hints could be reused as record-match terms, allowing unrelated Yiou/PitchHub company pages to be accepted when they only matched product words such as parking robots.
- Scope was extended inside task section 9 to separate search-query expansion from company-identity acceptance and to clean the contaminated rows from the 100-company validation batch.

### 2026-05-28 Source Product Semantic Quality Gate

- The operator clarified that XLSX import data is trusted as the company identity and existing-facts baseline, while external Yiou/PitchHub/official pages are untrusted enrichment candidates that may be stale, cross-linked, or about similar companies.
- Decision: source-backed products and scenarios are visible to company detail, release, chat fallback, and Milvus only when `quality_status='ready'`; `needs_review` and `rejected` rows remain stored as evidence and review state but do not enter display/RAG surfaces.
- Decision: add an LLM verification mode to the batch-scoped source product quality audit. The verifier compares the external source against the trusted XLSX baseline, checks company identity, product ownership, whether the candidate is an actual product/service, and requires source evidence. Ambiguous candidates remain `needs_review`.
- Decision: the audit can promote LLM-confirmed candidates to `ready`, reject high-confidence wrong-company/non-product candidates through the review-action path, and preserve ambiguous cases for operator review without requiring manual review of every source product row.

### 2026-05-28 Company Detail Business Display Refinement

- The company detail page should not expose raw product implementation fields such as `product_id`, `source_url`, `quality_status`, `confidence`, or review actions in the primary business product section.
- Decision: the company product section renders only product name, product description, product category, technical tags, target customers, and application scenarios.
- Decision: company `profile_summary` is labeled as `Company Introduction` in the UI instead of reusing the professor-oriented personal profile label.
- Decision: recent event rows should render business-facing date, type, and summary columns instead of exposing normalized JSON such as `amount_cny_wan: null`.
