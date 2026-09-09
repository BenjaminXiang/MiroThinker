## 1. Source Event Closure

- [x] 1.1 Add RED tests for source-adapter filtering and per-source report counts in `run_company_signal_extract.py`.
- [x] 1.2 Update signal extraction prompt/runner to process Yiou/PitchHub source profile rows and report source-level inserted counts.
- [x] 1.3 Run focused signal extractor tests.

## 2. Source Product Closure

- [x] 2.1 Add RED tests for extracting products from Yiou/PitchHub source body text into `CompanyProductCandidate` records.
- [x] 2.2 Add a source-text product extraction script that reads accepted source rows and writes `company_product` plus `company_product_evidence`.
- [x] 2.3 Fix official product capture DB writes to use canonical `company_id` from the DB when writing products.
- [x] 2.4 Run focused product extractor and script tests.

## 3. Company Display Surfaces

- [x] 3.1 Add RED backend tests proving company release/detail payloads include products, recent events, and source evidence.
- [x] 3.2 Extend company API/release DTOs and frontend detail rendering for products/recent events/source links.
- [x] 3.3 Run admin-console backend/frontend focused checks.

## 4. Milvus And RAG Refresh

- [x] 4.1 Add RED tests proving company Milvus text includes product and recent-event summaries.
- [x] 4.2 Extend company Milvus SQL/text/payload composition to include products and recent events.
- [x] 4.3 Run company Milvus focused tests and a bounded refresh or dry-run.

## 5. Bounded E2E And Evidence

- [x] 5.1 Add or update a bounded business-closure E2E report covering ingest, signal extraction, product extraction, API detail checks, and Milvus/RAG checks.
- [x] 5.2 Run the closure E2E on a small known sample including `深圳旭宏医疗科技有限公司`.
- [x] 5.3 Update acceptance evidence, verification notes, and validate OpenSpec strict.

## 6. Structured Financing, Products, And Scenarios

- [x] 6.1 Add RED migration/model tests for structured product columns and application scenario tables.
- [x] 6.2 Add V034 migration and canonical/API models for structured product and scenario fields.
- [x] 6.3 Add RED extractor tests for target customers, technical tags, and application scenarios from Yiou/PitchHub source text.
- [x] 6.4 Persist structured product fields and application scenario/evidence rows through the source-product extraction script.
- [x] 6.5 Expose structured financing, products, and application scenarios in company detail/release APIs and frontend detail rendering.
- [x] 6.6 Include structured product/scenario text in company Milvus refresh and company topic fallback search.
- [x] 6.7 Wire admin XLSX upload batches to scoped Yiou/PitchHub enrichment commands using uploaded company IDs and LLM search hints.
- [x] 6.8 Run bounded live validation on `深圳旭宏医疗科技有限公司`, update acceptance evidence, and validate OpenSpec strict.

## 7. Upload Batch Closure, Auditability, And Operations

- [x] 7.1 Add RED migration/model tests for upload-scoped enrichment batch state, per-company checkpoint state, search audit rows, and review action audit rows.
- [x] 7.2 Add V035 migration and storage helpers for resumable company enrichment batches.
- [x] 7.3 Change admin company XLSX upload to enqueue an enrichment batch after canonical import instead of running the full Yiou/PitchHub subprocess chain inline in the import task.
- [x] 7.4 Add a resumable `run_company_upload_enrichment_batch.py` runner that processes queued companies in chunks, records stage-level counts, and can resume after interruption.
- [x] 7.5 Persist Yiou/PitchHub search query diagnostics per company, including query text, source adapter, result counts, accepted counts, rejection counts, LLM hints, and miss reasons.
- [x] 7.6 Improve source signal extraction so dated Yiou news rows can produce events from their published date while source profile/project pages still require in-body date evidence.
- [x] 7.7 Support official-site product capture by canonical company ID and run it as part of upload batch enrichment when uploaded snapshots contain a website.
- [x] 7.8 Add LLM structured extraction fallback for source products and scenarios when deterministic source-text parsing returns no candidates.
- [x] 7.9 Auto-refresh company Milvus for only the companies touched by the enrichment batch, with an explicit skip flag for operators.
- [x] 7.10 Add stale `pipeline_run` cleanup tooling and close stale enrichment child runs without masking live runs.
- [x] 7.11 Add company product/scenario review endpoints for accepting, rejecting, or returning extracted rows to review, with audit records.
- [x] 7.12 Run focused tests, OpenSpec strict validation, and a bounded upload-batch E2E that proves queue, resume, audit, official product, LLM fallback, Milvus refresh, and review actions.

## 8. Ten Percent Validation Repair

- [x] 8.1 Add regression tests for local-file Milvus URI propagation from the upload batch runner.
- [x] 8.2 Add regression tests proving chunked batch counters are written per company, not copied from chunk aggregate reports.
- [x] 8.3 Add regression tests proving running batch progress is visible while chunks finish.
- [x] 8.4 Add regression tests proving search audit per-query accepted/rejected counters are not aggregate values repeated across query rows.
- [x] 8.5 Add regression tests proving official website extraction rejects domain-sale and JavaScript placeholder pages.
- [x] 8.6 Implement the batch runner, audit, and official-site extraction fixes discovered by the 10 percent validation.
- [x] 8.7 Run focused tests, OpenSpec strict validation, and a small batch smoke that proves the repaired invariants.

## 9. Historical Noise Cleanup And 100 Company Revalidation

- [x] 9.1 Add regression tests for official-site product false positives found while cleaning the previous 10 percent validation batch.
- [x] 9.2 Implement the additional official-site extraction guards for testimonial/social-handle, CTA, footer/social-link, generic-section, protocol/social-app, marketing, channel, article-title, copyright, and external-tool noise.
- [x] 9.3 Export and delete historical noisy `company_product` rows produced by the previous 10 percent validation batch, preserving a cleanup audit artifact.
- [x] 9.4 Create and run a fresh 100-company validation batch, then record search, signal, product, scenario, official-product, Milvus, and noise-regression evidence.
- [x] 9.5 Add source-acceptance regression coverage and repair Yiou/PitchHub matching so product, keyword, and LLM hint query terms can broaden search but cannot prove company identity.
- [x] 9.6 Clean the 100-company validation batch rows rejected by the repaired source-acceptance and official-product guards, preserving cleanup and restore audit artifacts.

## 10. Source Product Quality Audit Closure

- [x] 10.1 Add regression tests for batch-scoped source product quality audit classification, including company identity failure, non-product/generic-name failure, evidence-quality failure, and ready candidates.
- [x] 10.2 Implement a batch-scoped `run_company_source_product_quality_audit.py` script that audits source-backed products against company identity, source evidence, product-name quality, and evidence-span quality without requiring manual review of every row.
- [x] 10.3 Run the audit on the 100-company validation batch, export a report, and mark clear failures as `rejected` while leaving ambiguous rows as `needs_review`.
- [x] 10.4 Record post-audit metrics, remaining risk, and validation commands in acceptance and run verification artifacts.
