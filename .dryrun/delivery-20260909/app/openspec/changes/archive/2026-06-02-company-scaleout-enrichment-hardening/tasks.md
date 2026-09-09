## 1. Contract and Regression Tests

- [x] 1.1 Add official-site acquisition tests for static success, sitemap discovery, common-path discovery, SPA-shell detection, Playwright rendering success, and rendering failure in `apps/miroflow-agent/tests/data_agents/company/test_official_product_capture.py`.
- [x] 1.2 Add official-site failure-taxonomy tests for `no_website`, `invalid_url`, `dns_failed`, `timeout`, `http_403`, `http_429`, `captcha_or_bot_challenge`, `robots_disallowed`, `js_required`, `js_render_failed`, `text_too_short`, `no_relevant_pages`, `identity_mismatch`, `noise_page`, and `fetch_failed`.
- [x] 1.3 Add source-provenance tests that accepted source materials preserve acquisition method, source tier, URL, title, capture time, LLM judgment status, confidence, evidence span, and trust reason.
- [x] 1.4 Add model-routing tests proving low-risk query and trusted-XLSX structuring can use `deepseek-v4-lite`, while snippet triage, source judgment, generic product admission, financing extraction, conflict judgment, multi-source summaries, and quality audit use `deepseek-v4-pro`.
- [x] 1.5 Add regression coverage proving snippet triage, generic product admission, and financing extraction do not use a `lite_then_pro` cascade.
- [x] 1.6 Add batch concurrency/checkpoint tests for per-stage concurrency limits, timeout/retry settings, resumed stages, and duplicate-free replay.
- [x] 1.7 Add admin API and frontend tests for batch/company enrichment diagnostics, official-site failure reason, accepted/rejected source counts, product/scenario/funding counts, vector refresh status, and source links.
- [x] 1.8 Add report-shape tests for 200-company dry-run and live validation outputs, including selected company IDs, enabled/skipped stages, source counts, miss reasons, vector refresh, RAG smoke status, and residual risks.

## 2. Official-Site Acquisition Hardening

- [x] 2.1 Refactor `apps/miroflow-agent/src/data_agents/company/official_product_capture.py` to separate URL normalization, fetch attempt recording, page discovery, rendering fallback, material extraction, and failure classification.
- [x] 2.2 Implement sitemap discovery and same-host URL normalization for official-site material capture.
- [x] 2.3 Implement bounded common-path probing for about, product, service, solution, case, customer, and news pages when navigation links are missing.
- [x] 2.4 Add JavaScript-rendering fallback behind an explicit flag or dependency-safe helper, triggered only for low-text, empty, or SPA-shell static pages.
- [x] 2.5 Add compliance-safe blocking detection for CAPTCHA, login, paywall, robots disallow, HTTP 403, and HTTP 429 without bypass attempts.
- [x] 2.6 Persist or report acquisition method, HTTP status, content length, text length, page category, accepted/rejected status, and normalized failure reason for every official-site attempt.
- [x] 2.7 Update `apps/miroflow-agent/scripts/run_company_official_product_capture.py` to expose rendering, discovery, timeout, page-count, and failure-taxonomy options in dry-run and batch modes.

## 3. Source Material and LLM Quality Gates

- [x] 3.1 Extend the source-material contract if needed so official, Yiou, PitchHub, and generic web materials can store acquisition diagnostics and source-judgment evidence consistently.
- [x] 3.2 Update generic source judgment so accepted material requires target-company identity and fact attribution before any source feeds synthesis or vector text.
- [x] 3.3 Add product-ownership and scenario-attribution gates to prevent related articles, investors, customers, competitors, similar projects, and platform recommendations from becoming target-company facts.
- [x] 3.4 Ensure source-product extraction writes only the six business-facing product fields: product name, product description, product category, technical tags, target customers, and application scenarios.
- [x] 3.5 Ensure generic-web-only facts remain review-gated unless source judgment confirms strong identity and attribution evidence.
- [x] 3.6 Preserve rejected source and rejected candidate reasons in batch/company diagnostics.

## 4. LLM Model Routing and Concurrent Execution

- [x] 4.1 Add a task-to-model routing layer for Company enrichment LLM calls, with auditable task type, model profile, timeout, retry budget, and non-sensitive request metadata.
- [x] 4.2 Wire `deepseek-v4-lite` only for low-risk search hint, identity alias, and trusted-XLSX structuring tasks.
- [x] 4.3 Wire `deepseek-v4-pro` for snippet triage, source judgment, generic product admission, product ownership attribution, financing extraction, conflict/newer-round judgment, multi-source profile synthesis, technology-route synthesis, and quality audit.
- [x] 4.4 Add configurable per-stage LLM concurrency and provider-level rate limiting to the upload enrichment batch runner.
- [x] 4.5 Add retry/backoff and JSON repair retry for LLM structured extraction failures without hiding final failure reasons.
- [x] 4.6 Record model profile and LLM task outcomes in per-company audit without logging API keys, prompts containing secrets, or credential-bearing environment values.

## 5. Batch Checkpoint, Resume, and Idempotency

- [x] 5.1 Extend `apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` checkpoint state to cover official acquisition, Yiou/PitchHub capture, generic source judgment, product/scenario synthesis, financing extraction, profile synthesis, and vector refresh.
- [x] 5.2 Update `apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py` so reruns skip succeeded stages by default and can include failed stages when requested.
- [x] 5.3 Make official-source, product, scenario, financing-event, profile-summary, and vector-refresh writes idempotent under repeated batch execution.
- [x] 5.4 Add stale-running cleanup for companies and stages that time out during concurrent execution.
- [x] 5.5 Add batch-level summaries for query counts, fetch counts, accepted/rejected sources, LLM failures, official failure reasons, products, scenarios, target customers, funding events, summaries, and vectors.

## 6. Admin Console and Detail Surfaces

- [x] 6.1 Extend pipeline detail API payloads with company-level enrichment diagnostics, official-site failure reason, source counts by tier, accepted/rejected counts, current stage, last error, and vector refresh status.
- [x] 6.2 Extend company detail API payloads with enriched profile summary, technology-route summary, products, application scenarios, recent financing/dynamics, source URLs, quality status, and updated timestamps.
- [x] 6.3 Update company detail UI so basic information remains first, followed by products, application scenarios, and recent dynamics, with source links and review state visible when available.
- [x] 6.4 Update pipeline detail UI so operators can inspect batch progress, per-company failures, official-source failure categories, source-judgment outcomes, and stage-level retries.
- [x] 6.5 Verify search and detail navigation still work on the 5180 path for a company enriched in the validation sample.

## 7. Scaleout Validation Runner and Evidence

- [x] 7.1 Add or extend a deterministic sample selector that can select 200 representative XLSX-backed companies across industry, website availability, and source-coverage buckets.
- [x] 7.2 Add a 200-company dry-run mode that reports selected scope, expected writes, enabled/skipped stages, configured concurrency, and blocked prerequisites without modifying data.
- [x] 7.3 Add a 200-company live bounded validation mode that runs the upload-scoped enrichment stages, persists only selected-company outputs, and refreshes only touched vectors.
- [x] 7.4 Add cleanup tooling for historical validation noise that targets batch/source markers and statuses only, not unrelated production data.
- [x] 7.5 Produce a validation report covering base readiness, official-site attempts and failures, Yiou/PitchHub/generic source results, products, scenarios, target customers, funding events, team structure, long profiles, technology summaries, vector refresh, RAG smoke checks, and residual risks.
- [x] 7.6 Store validation evidence under `.agents/runs/company-scaleout-enrichment-hardening/` and summarize requirement coverage in `openspec/changes/company-scaleout-enrichment-hardening/acceptance.md`.

## 8. RAG and Final Verification

- [x] 8.1 Update company vector payload construction if needed so refreshed vectors include long profile, technology summary, products, technical tags, target customers, scenarios, structured team highlights, and source-backed funding signals.
- [x] 8.2 Run focused Company tests for official capture, source judgment, source-product extraction, signal extraction, narrative enrichment, batch orchestration, vectorizer, and upload scripts.
- [x] 8.3 Run focused admin-console API and frontend tests for upload/pipeline/detail/search behavior.
- [x] 8.4 Run `openspec validate company-scaleout-enrichment-hardening --strict` after implementation changes.
- [x] 8.5 Run the 200-company dry-run validation and record the report.
- [x] 8.6 Run the 200-company live bounded validation only after dry-run prerequisites pass and record the report.
- [x] 8.7 Run touched-company vector refresh and RAG smoke checks for product, scenario, target-customer, recent-financing, and profile-summary questions.
- [x] 8.8 Manually inspect representative companies in the 5180 environment and record screenshots or notes for product fields, application scenarios, recent dynamics, source links, processing status, and summary quality.

## 9. Full 1024-Company Rerun After Current-Goal Verification

- [x] 9.1 Confirm all current-goal verification gates have passed: source-quality tests, admin diagnostics tests, idempotency checks, 200-company dry-run, 200-company live bounded run, touched-vector refresh, RAG smoke checks, and representative 5180 inspection.
- [x] 9.2 Record the measured 200-company dry-run bottleneck report and use it as the go/no-go gate for full-run scaleout.
- [x] 9.3 Before any 1024-company full dry-run or live rerun, implement script-internal LLM/web concurrency for LLM-heavy child scripts, provider rate limiting for DeepSeek and Serper, per-company stage checkpointing inside child scripts, and dry-run no-write regression coverage.
- [x] 9.4 Verify Company LLM model routing across all upload-enrichment LLM entry points, especially `run_company_xlsx_team_synthesis.py`, so low-risk search-hint/trusted-XLSX tasks use `deepseek-v4-lite` and judgment/synthesis tasks use `deepseek-v4-pro`.
- [x] 9.5 Run a full imported-company dry-run for the current XLSX-backed company set, expected to be 1024 canonical companies unless the database count changes before execution.
- [x] 9.6 Record the full-run execution plan, including enabled stages, skipped stages, checkpoint/resume policy, provider concurrency/rate-limit settings, estimated runtime, cleanup plan, and rollback plan.
- [x] 9.7 Execute the full 1024-company live rerun only after the full dry-run is reviewed and passes prerequisites.
- [x] 9.8 Refresh vectors only for touched companies and run RAG smoke checks for product, scenario, target-customer, recent-financing, and profile-summary questions after the full rerun.
- [x] 9.9 Produce a full-run effect report covering baseline counts, post-run counts, coverage uplift, source acceptance/rejection reasons, product/scenario/target-customer/funding/summarization coverage, vector refresh results, RAG smoke results, 5180 inspection notes, failures, and remaining manual-review companies.

## 10. Post-Collection Product/Scenario Extraction Escape Repair

- [x] 10.1 Add regression coverage for XLSX-only product/scenario facts discovered after the full rerun, using the OneGu-style "Youxin / points mall / CRM / supply chain" case.
- [x] 10.2 Ensure post-collection synthesis still runs XLSX-baseline product/scenario extraction during the final multi-source narrative stage, even when external source rows are absent.
- [x] 10.3 Ensure XLSX product/scenario LLM fallback uses the judgment-grade `deepseek-v4-pro` route and records fallback parse/provider diagnostics instead of silently returning empty results.
- [x] 10.4 Re-run the OneGu company slice, verify product/scenario rows are persisted, refresh its vector, and record evidence.
