## Acceptance Evidence

This file records implementation and validation evidence for
`company-scaleout-enrichment-hardening`.

### Required Evidence Matrix

| Area | Required evidence | Status |
|---|---|---|
| OpenSpec | `openspec validate company-scaleout-enrichment-hardening --strict` | Passed after current implementation changes on 2026-05-31 |
| Official-site acquisition | Unit/script tests for static fetch, sitemap/common-path discovery, JS rendering fallback, compliance-safe blocking, and failure taxonomy | Partial: RED/GREEN tests added for sitemap URL filtering, actual `/sitemap.xml` discovery, common-path fallback, SPA-shell detection, JS-render callable and CLI flag, HTTP/robots diagnostics, failure taxonomy, and dry-run failure reporting |
| Source quality gates | Tests proving generic and third-party sources require company identity and fact attribution before persistence | Passed for source judgment, generic product admission, product/scenario candidate attribution, six-field product report shape, generic-web review gating, and batch rejection diagnostics |
| Model routing | Tests proving low-risk tasks may use `deepseek-v4-lite` and judgment-sensitive tasks use `deepseek-v4-pro`; no `lite_then_pro` for snippet triage, product admission, or financing extraction | Passed for the Company routing layer, upload-batch audit metadata, and the `run_company_xlsx_team_synthesis.py` entrypoint |
| Concurrency/checkpoint | Tests proving configurable concurrency, retry, resume, stale cleanup, duplicate-free replay, provider rate limiting, child-script concurrency, per-child LLM timeout/retry controls, and per-company child checkpointing | Passed for the upload enrichment batch runner, 10-company smoke, 200-company post-optimization dry-run, 200-company live validation, and the 2026-05-31 child LLM timeout/retry hardening tests |
| Admin console | Backend/frontend tests and 5180 inspection for batch diagnostics, company details, product/scenario/recent-dynamics/source-link display, and search/detail navigation | Passed for the current gate: focused API/frontend/build tests passed earlier; 5180 search/detail inspection passed for representative companies on 2026-05-31 |
| 200-company dry-run | Report with selected companies, stages, expected writes, skipped checks, configured concurrency, and blockers | Passed on 2026-05-31 for batch `fb7eeffb-ca23-45bd-8116-0029f8aa32ce`; 200/200 selected companies succeeded under dry-run/no-persistence/no-Milvus mode |
| 200-company live bounded run | Report with persisted outputs only for selected companies and touched-company vector refresh only | Passed for the fixed 200-company validation sample on 2026-05-31; 200 selected companies succeeded, affected vectors were refreshed after cleanup, and unselected companies remained queued |
| 1024-company full rerun | Gated full dry-run, reviewed execution plan, live rerun, touched-company vector refresh, RAG smoke checks, 5180 inspection, and full-run effect report after all current-goal validation passes and after the pre-1024 internal-concurrency/rate-limit/checkpoint/model-routing optimization gate passes | Passed on 2026-05-31: full dry-run, execution plan, live rerun, touched-vector refresh, RAG smoke, 5180 inspection, and full-run effect report are recorded |
| Post-collection product/scenario extraction | Regression coverage and live OneGu replay proving XLSX-only product/scenario facts are extracted after collection, persisted, visible in 5180, and refreshed into company vectors | Passed on 2026-05-31: OneGu produced 1 product and 8 application scenarios through the `deepseek-v4-pro` product fallback route |
| Data quality | Report counts for official, Yiou, PitchHub, generic sources, products, scenarios, target customers, funding events, summaries, vectors, miss reasons, and residual risks | Passed for the 200-company validation gate with residual risks recorded in the final summary |
| RAG | Smoke checks for product, scenario, target-customer, financing, and profile-summary questions using refreshed touched-company vectors | Passed on 2026-05-31 with 5/5 post-cleanup company RAG smoke checks |

### Notes

- XLSX remains the trusted baseline for company identity and baseline facts.
- Full XLSX-scale live enrichment is a gated final phase of this change. It
  must not run until the source-quality, admin diagnostics, idempotency,
  200-company dry-run/live validation, touched-vector refresh, RAG smoke, and
  representative 5180 inspection gates have passed.
- The 1024-company full dry-run and live rerun are additionally gated by the
  200-company runtime evidence. If the 200-company dry-run exposes scaleout
  bottlenecks, the full run must wait for script-internal LLM/web concurrency,
  provider rate limiting, per-company child-script checkpoints, dry-run
  no-write regression coverage, and full Company LLM model-routing verification.
- Recruiting/job-trend extraction, CAPTCHA bypass, login bypass, paywall bypass,
  and unbounded crawling are outside this change.

### 2026-05-31 - Post-collection XLSX-only product/scenario escape repair

Requirement coverage:
- Fixed the escaped OneGu case where trusted XLSX text contained explicit
  product and scenario facts but the full post-collection run left
  `company_product` and `company_application_scenario` empty.
- Post-collection narrative synthesis now still runs the XLSX-baseline
  product/scenario extractor, so companies with no accepted external source
  rows can still publish trusted XLSX-derived product facts.
- XLSX product/scenario extraction uses the judgment-grade
  `generic_product_admission` Company LLM route, currently
  `deepseek-v4-pro`, and records fallback model/count/error diagnostics instead
  of silently returning empty results.
- The live OneGu replay persisted 1 product (`Youxin points mall`) and 8
  application scenarios. Both 18188 and 5180 APIs returned the same counts, and
  the 5180 detail page rendered the product and scenario sections.
- Refreshed the OneGu company vector after persistence.

Verification:
- `uv run --no-sync pytest -n0 --no-cov apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py -q` -> passed, 59 tests.
- `uv run --no-sync ruff check apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py` -> passed.
- `python -m py_compile apps/miroflow-agent/src/data_agents/company/source_product_extractor.py apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py` -> passed.
- OneGu replay output:
  `.agents/runs/company-scaleout-enrichment-hardening/onegu-post-collection-product-replay-20260531T153722Z.json`
  -> 1 product synthesized/written, 8 scenarios synthesized/written, 0
  product-synthesis failures, fallback model `deepseek-v4-pro`.
- API verification output:
  `.agents/runs/company-scaleout-enrichment-hardening/onegu-api-ui-verification-20260531T154026Z.json`
  -> 18188 and 5180 both returned 1 product and 8 application scenarios.
- 5180 browser evidence:
  `.agents/runs/company-scaleout-enrichment-hardening/screenshots/onegu-company-detail-products-20260531.png`.
- Vector refresh output:
  `.agents/runs/company-scaleout-enrichment-hardening/onegu-milvus-refresh-20260531T154006Z.json`
  -> 1 company processed, 0 skipped, 0 errors.

Remaining gaps:
- This slice replayed the reported OneGu company only. The same fixed
  post-collection extractor should be included in the next bounded/full company
  rerun to lift the remaining XLSX-only product/scenario long tail.

### 2026-05-31 - All-company post-collection product/scenario coverage

Requirement coverage:
- Executed post-collection XLSX/current-material product and scenario extraction
  for all 1024 resolved XLSX-backed companies.
- Increased the LLM fallback output budget to 4096 tokens after the first full
  run exposed 42 `json_parse_failed` responses that were valid-looking but
  truncated.
- Broadened the LLM extraction prompt so source-grounded services, solutions,
  platforms, technical systems, and core technology offerings can be extracted
  as product candidates, not only named packaged products.
- Added scenario derivation from product `application_scenarios`, so product
  cards and the standalone application-scenario table stay aligned.
- First full pass processed 1024/1024 companies, with 42 product-synthesis
  parse failures. The focused retry processed 42/42 and left 0 failures.
- Residual replays processed 373 and then 264 companies with 0 failures.
- Final database coverage: 1003/1024 companies have non-rejected products and
  775/1024 have non-rejected standalone application scenarios. Residual gaps
  are recorded as no source-grounded product/scenario extraction, not pipeline
  failures.
- Refreshed all 1024 company vectors after the product/scenario expansion.

Verification:
- Final counts artifact:
  `.agents/runs/company-scaleout-enrichment-hardening/all-company-product-scenario-final-counts-20260531T164524Z.json`.
- Full replay artifact:
  `.agents/runs/company-scaleout-enrichment-hardening/all-company-post-collection-product-replay-20260531T160719Z.json`.
- Failed-parse retry artifact:
  `.agents/runs/company-scaleout-enrichment-hardening/all-company-post-collection-product-failure-retry-20260531T162332Z.json`.
- Residual broad-offering replay artifact:
  `.agents/runs/company-scaleout-enrichment-hardening/all-company-product-scenario-residual-replay-20260531T162908Z.json`.
- Scenario-derivation residual replay artifact:
  `.agents/runs/company-scaleout-enrichment-hardening/all-company-scenario-derivation-residual-replay-20260531T163901Z.json`.
- 5180 API smoke artifact:
  `.agents/runs/company-scaleout-enrichment-hardening/all-company-product-scenario-api-smoke-20260531T164738Z.json`
  confirmed OneGu and Wisson/万勋 product/scenario fields are visible through
  the frontend API path.
- Milvus refresh artifact:
  `.agents/runs/company-scaleout-enrichment-hardening/all-company-product-scenario-milvus-refresh-20260531T164601Z.json`
  -> 1024 companies processed, 0 skipped, 0 errors.
- Focused tests:
  `uv run --no-sync pytest -n0 --no-cov apps/miroflow-agent/tests/data_agents/company/test_source_product_extractor.py apps/miroflow-agent/tests/scripts/test_run_company_xlsx_team_synthesis.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  -> 62 passed.
- `uv run --no-sync ruff check ...` -> passed.
- `python -m py_compile ...` -> passed.

Remaining gaps:
- 21 companies still have no non-rejected product and 249 companies still have
  no standalone application-scenario row after all retries. Samples are stored
  in the final-counts artifact for later manual/source-enrichment review.

### 2026-05-31 - Child LLM concurrency, timeout, and retry hardening

Requirement coverage:
- Upload-runner child defaults were raised to `LLM=4` and `web=3`.
- The upload runner now exposes `--child-llm-timeout-seconds` and
  `--child-llm-retry-budget`, records those settings in run reports, and
  propagates them to all LLM-using child scripts.
- LLM child scripts now expose matching `--llm-timeout-seconds` and
  `--llm-retry-budget` options.
- OpenAI-compatible clients now receive explicit `max_retries` from Company
  task routing.
- Signal extraction now runs LLM extraction with per-news-row worker
  concurrency, while DB writes remain serialized after extraction.

Verification:
- RED subset failed before implementation on missing timeout/retry flags,
  runner propagation, OpenAI `max_retries`, and signal worker concurrency.
- The same subset passed after implementation: 9 tests.
- Signal worker-concurrency RED/GREEN passed: 1 test.
- Focused Company script suite passed: 117 tests.
- `python -m py_compile` passed for all touched scripts.
- `openspec validate company-scaleout-enrichment-hardening --strict` passed.

Remaining gaps:
- The 1024-company dry-run remains pending under task 9.5.
- The 1024-company live rerun remains gated on full dry-run review.

### 2026-05-31 - Full imported-company dry-run and live-run plan

Requirement coverage:
- Created a fresh full imported-company dry-run batch
  `84fd0f38-1430-4532-9787-098f2663a3ce` for the current 1024-company
  XLSX-backed canonical set.
- The dry-run used real official-site, Yiou, PitchHub, generic web, Serper, and
  DeepSeek calls while preserving `--dry-run --skip-persistence --skip-milvus`.
- The final fixed resume completed 1024/1024 selected companies with database
  batch status `succeeded`, 0 failed companies, and every stage checkpointed
  1024/1024.
- Business fact tables had zero row-count delta:
  `company_product`, `company_product_evidence`,
  `company_application_scenario`, `company_signal_event`, and
  `company_news_item`.
- `company_enrichment_search_audit` increased from 5892 to 11450 rows, which is
  retained as permitted dry-run search-audit evidence.
- Recorded the full live-run execution plan, including enabled/skipped stages,
  checkpoint/resume policy, provider concurrency/rate-limit settings, estimated
  runtime, cleanup plan, and rollback plan.
- During 9.5, the provider rate limiter was fixed because the interval lock was
  serializing DeepSeek calls. A regression test now proves two slow calls can
  overlap when `max_concurrency=2`.

Evidence:
- Dry-run output:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-resume-llm40-fixed-20260531T112931Z.json`.
- Dry-run stderr:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-resume-llm40-fixed-20260531T112931Z.stderr.txt`
  (0 bytes).
- Before counts:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-before-counts-20260531T081827Z.json`.
- After counts:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-after-counts-20260531T115737Z.json`.
- Human report:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-report-20260531T115737Z.md`.
- Machine summary:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-summary-20260531T115737Z.json`.
- Execution plan:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-run-execution-plan-20260531T115737Z.md`.

Key metrics:
- Final fixed resume runtime: 28m 6s.
- Total batch wall clock including aborted tuning resumes: 3h 38m.
- Generic web search audit: 3166 rows, 15697 results, 4058 accepted.
- Yiou search audit: 1196 rows, 2184 results, 363 accepted.
- PitchHub/36Kr search audit: 1196 rows, 7002 results, 408 accepted.
- Runner summary: 4045 stage reports succeeded, 0 failed; 3012 queries; 331
  fetches; 3855 accepted sources; 4796 rejected sources; 1004 dry-run
  narratives; 56 LLM failures recorded in diagnostics.

Verification:
- `uv run --no-sync pytest apps/miroflow-agent/tests/data_agents/company/test_provider_rate_limit.py`
  -> passed, 4 tests.
- `uv run --no-sync python -m py_compile apps/miroflow-agent/src/data_agents/company/provider_rate_limit.py`
  -> passed.
- Full dry-run command exited 0 and the database batch status is `succeeded`.

Remaining gaps:
- Closed by the later full live-rerun evidence section below.

### 2026-05-31 - Full 1024-company live rerun, vector refresh, and effect report

Requirement coverage:
- Executed the full live rerun for batch
  `a1a72d01-e054-48e9-8124-f62e920ab3f7` after the full dry-run and execution
  plan passed review.
- The live rerun processed 1024/1024 selected XLSX-backed canonical companies
  with 1024 succeeded, 0 failed, database batch status `succeeded`, and empty
  command stderr.
- All 8193 reported stage executions succeeded across baseline readiness,
  XLSX/team synthesis, official product capture, Yiou, PitchHub, generic source
  judgment, signal extraction, source-product extraction, and multi-source
  narrative synthesis.
- Persisted live business-fact deltas for the 1024-company scope:
  `company_product` +1726, `company_product_evidence` +4949,
  `company_application_scenario` +766, `company_signal_event` +152,
  `company_news_item` +3729, and `company_enrichment_search_audit` +5558.
- Refreshed only the touched 1024 company vectors in the admin-console Milvus
  Lite store used by the 5180 backend.
- Ran post-refresh RAG smoke checks for product, target customer, application
  scenario, recent financing, and profile-summary queries; all 5 checks hit
  the expected company at rank 1.
- Inspected the 5180 company detail page for `COMP-54fd4dd036ff` and recorded
  text, DOM, and screenshot evidence for company summary, products, application
  scenarios, recent dynamics, target customers, financing text, source links,
  and absence of the old `个人简介` label.
- Produced the full-run effect report with baseline/post-run counts, coverage,
  source acceptance/rejection, quality status, manual-review exposure, vector
  refresh, RAG smoke, 5180 notes, failures, and residual risks.

Evidence:
- Live batch output:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-20260531T120639Z.json`.
- Live stderr:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-20260531T120639Z.stderr.txt`
  (0 bytes).
- Before counts:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-before-counts-20260531T120621Z.json`.
- After counts:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-after-counts-20260531T132516Z.json`.
- Machine summary:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-summary-20260531T132516Z.json`.
- Effect metrics:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-effect-metrics-20260531T134500Z.json`.
- Effect report:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-effect-report-20260531.md`.
- Vector refresh:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-admin-milvus-refresh-20260531T133200Z.json`.
- RAG smoke:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-rag-smoke-20260531T133320Z.json`.
- 5180 text snapshot:
  `.agents/runs/company-scaleout-enrichment-hardening/5180-company-metalenx-full-live-text-20260531.txt`.
- 5180 DOM snapshot:
  `.agents/runs/company-scaleout-enrichment-hardening/5180-company-metalenx-full-live-snapshot-20260531.txt`.
- 5180 screenshot:
  `.agents/runs/company-scaleout-enrichment-hardening/screenshots/5180-company-metalenx-full-live-20260531.png`.

Key metrics:
- Companies with products: 666/1024; product rows: 2346.
- Companies with product target customers: 83/1024; product rows with target
  customers: 102.
- Companies with application scenarios: 341/1024; scenario rows: 1136.
- Companies with signal events: 579/1024; funding or financing signal events:
  843.
- Companies with news/source items: 928/1024; news/source rows: 4702.
- Companies with `profile_summary`: 1014/1024.
- Companies with `technology_route_summary`: 1014/1024.
- Search audit by source: generic web 3166 queries / 15500 results / 3995
  accepted; Yiou 1196 queries / 2176 results / 361 accepted; PitchHub/36Kr
  1196 queries / 6988 results / 407 accepted.
- Vector refresh processed 1024/1024 companies with 0 errors in 48.8 seconds.

Verification:
- Full live rerun command exited 0; database batch status is `succeeded`.
- Touched-vector refresh command exited 0 and reported 1024 processed, 0
  skipped, and 0 errors.
- RAG smoke command exited 0 and reported 5 passed, 0 failed.
- 5180 browser inspection confirmed the representative page renders the
  enriched company information and no longer uses `个人简介`.

Remaining gaps:
- Product target-customer coverage remains a quality-improvement item.
- Review-gated product/scenario facts remain visible with review state and need
  operator review before being treated as verified facts.
- Official-site capture remains bounded by availability, anti-bot behavior,
  JavaScript rendering quality, robots, CAPTCHA, login, and paywall limits.

### 2026-05-30 - OpenSpec and official-site diagnostic test slice

Requirement coverage:
- Created the `company-scaleout-enrichment-hardening` OpenSpec change with proposal, design, spec deltas, tasks, and acceptance matrix.
- Added official-site acquisition regression tests for sitemap URL filtering, common material URL generation, SPA-shell detection, JavaScript-render fallback success through an injectable renderer, and normalized failure taxonomy.
- Added source-material provenance fields and script-level dry-run serialization for acquisition method, source judgment status, confidence, evidence span, and official capture failures.

Verification:
- `openspec validate company-scaleout-enrichment-hardening --strict` -> passed.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_official_product_capture.py -q` -> RED before implementation, then passed, 19 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py -q` -> RED before implementation, then passed, 8 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py tests/data_agents/company/test_official_product_capture.py -q` -> passed, 27 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_official_product_capture.py tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_narrative_enrichment.py -q` -> passed, 54 tests.

Remaining gaps:
- Official sitemap fetching is now wired for the default `/sitemap.xml`; alternate sitemap indexes and `robots.txt` sitemap discovery are still pending.
- JavaScript rendering is available through a dependency-optional Playwright helper and `--enable-js-render`; production validation still needs an environment check that browser dependencies are installed.
- HTTP status, content type, errors, and robots flags are now represented by structured fetch results; full `robots.txt` parsing is still pending.
- The 200-company dry-run has now passed; live bounded validation remains pending.

### 2026-05-30 - Official-site sitemap, structured fetch, and diagnostics slice

Requirement coverage:
- Official capture now supports structured fetch results with HTML, HTTP status, content type, error, and robots-disallowed flags.
- Official capture now tries same-host `/sitemap.xml` when homepage navigation yields no material URLs, then falls back to common official business paths.
- The official capture script accepts `--enable-js-render` and uses a dependency-optional Playwright renderer only when static content requires JavaScript.
- Official capture attempts now report acquisition method, HTTP status, content type, error, robots flag, content length, text length, page category, accepted/rejected status, JS-required flag, and normalized failure reason.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py -q` -> RED before implementation, then passed, 10 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py tests/data_agents/company/test_official_product_capture.py -q` -> passed, 29 tests.

Remaining gaps:
- `robots.txt` parsing and sitemap discovery from robots declarations are not implemented yet.
- Playwright availability has not been verified in the runtime environment.
- The official capture script still fetches materials and products separately; a later cleanup should reuse captured pages to reduce duplicate official-site requests.

### 2026-05-30 - Company LLM model routing slice

Requirement coverage:
- Added `deepseek-v4-lite` to the shared OpenAI-compatible LLM profile resolver.
- Added a Company LLM routing module with explicit task types, direct model selection, timeout defaults, retry-budget defaults, DeepSeek non-thinking extra body, and credential-free audit metadata.
- Routed low-risk search-hint generation to `deepseek-v4-lite`.
- Routed generic source judgment, generic product admission, financing extraction, and multi-source profile synthesis to `deepseek-v4-pro`.
- Added regression coverage proving snippet triage, generic product admission, financing extraction, and other judgment-sensitive tasks do not use a `lite_then_pro` cascade.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_llm_routing.py tests/data_agents/professor/test_llm_profiles.py -q` -> RED before implementation, then passed, 30 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_llm_routing.py tests/data_agents/professor/test_llm_profiles.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_narrative_backfill.py -q` -> passed, 93 tests.
- `python -m compileall -q apps/miroflow-agent/src/data_agents/company/llm_routing.py apps/miroflow-agent/src/data_agents/professor/llm_profiles.py apps/miroflow-agent/scripts/run_company_generic_source_judgment.py apps/miroflow-agent/scripts/run_company_signal_extract.py apps/miroflow-agent/scripts/run_company_source_product_extract.py apps/miroflow-agent/scripts/run_company_narrative_backfill.py apps/miroflow-agent/scripts/run_company_news_ingest.py` -> passed.

Remaining gaps:
- Other Company LLM usage points outside the covered upload-batch path may still need routing cleanup when they are included in future slices.

### 2026-05-30 - Upload batch execution hardening slice

Requirement coverage:
- Added a per-stage execution policy to `run_company_upload_enrichment_batch.py` covering stage family, effective concurrency, provider/rate-limit key, timeout, retry budget, retry backoff, JSON repair retry flag, and credential-safe LLM audit metadata.
- Added separate CLI controls for global, LLM, and web stage concurrency plus stage timeout, retry budget, and retry backoff.
- Added provider-level max concurrency defaults and environment overrides for DeepSeek, Serper, official-site, and Milvus stages.
- Routed upload-batch stage audit metadata to `deepseek-v4-lite` for search-hint/trusted-XLSX tasks and `deepseek-v4-pro` for source judgment, financing extraction, product admission, and multi-source profile synthesis tasks.
- Added transient failure retry at the stage-shard layer, with attempt reports, final failure reason, and non-retryable structured-output failure classification.
- Extended per-company `stage_status` payloads with execution policy, LLM task outcome metadata, miss reason, and last error while avoiding API keys and credential-bearing values.
- Extended stale cleanup to cover stale running company-state rows, not only stale running batch rows.
- Added upload-batch summary counters for checkpoint skips, stage success/failure, queries, fetches, accepted/rejected sources, LLM failures, official failure reasons, products, scenarios, target-customer product count, funding events, narratives, and vector refreshes.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py -q` -> RED before implementation, then passed, 26 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_llm_routing.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py -q` -> passed, 113 tests.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` -> passed.
- `openspec validate company-scaleout-enrichment-hardening --strict` -> passed.

Remaining gaps:
- This slice proves duplicate-free replay at the orchestration/checkpoint level; full table-by-table idempotency for all child writers remains tracked under task 5.3.
- Admin-console diagnostics, 200-company dry-run/live validation, touched-vector RAG smoke tests, and 5180 manual inspection remain pending.

### 2026-05-30 - Source quality gates and rejection diagnostics slice

Requirement coverage:
- Generic source judgment already requires target-company identity and fact attribution before accepting generic web material; this slice verified that invariant in the focused source-quality suite.
- Source-product extraction now preserves LLM source-gate and candidate-gate rejection reasons in `rejected_candidate_reasons` and `rejected_candidates`.
- Product/scenario candidate attribution gates now keep rejection reasons for Yiou, PitchHub, and generic web source materials.
- Source-product report items now expose only the six business-facing product fields: product name, product description, product category, technical tags, target customers, and application scenarios.
- Generic-web products now require explicit accepted source judgment before they can become `ready`; high confidence or strong-sounding trust text alone is insufficient.
- Upload-batch summaries and source-product stage details now aggregate rejected candidate counts, reasons, and bounded sanitized samples.

Verification:
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py -q` -> RED before implementation on missing rejected-candidate diagnostics and six-field product report shape, then passed, 15 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_stage_details_capture_synthesis_and_persistence_audit tests/scripts/test_run_company_upload_enrichment_batch.py::test_stage_details_capture_source_product_rejection_reasons tests/scripts/test_run_company_upload_enrichment_batch.py::test_batch_summary_accumulates_source_product_rejection_reasons -q` -> RED before implementation on missing batch rejection diagnostics, then passed, 3 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_source_product_extractor.py::test_generic_web_products_require_accepted_source_judgment_before_ready tests/data_agents/company/test_source_product_extractor.py::test_generic_web_products_can_be_ready_with_accepted_strong_judgment -q` -> RED before implementation on generic-web ready gating, then passed, 2 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_generic_source_judgment.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_upload_enrichment_batch.py -q` -> passed, 60 tests.
- `cd apps/miroflow-agent && uv run pytest -n0 --no-cov tests/data_agents/company/test_llm_routing.py tests/data_agents/company/test_generic_source_judgment.py tests/data_agents/company/test_source_product_extractor.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_official_product_capture.py tests/data_agents/company/test_official_product_capture.py -q` -> passed, 126 tests.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_source_product_extract.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/source_product_extractor.py` -> passed.
- `cd apps/miroflow-agent && uv run ruff check scripts/run_company_source_product_extract.py scripts/run_company_upload_enrichment_batch.py src/data_agents/company/source_product_extractor.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_source_product_extractor.py` -> passed.
- `openspec validate company-scaleout-enrichment-hardening --strict` -> passed.

Remaining gaps:
- Admin-console diagnostics and 5180 display are still pending under section 6.
- Full child-writer table-level idempotency remains tracked under task 5.3.
- 200-company dry-run/live validation, RAG smoke tests, 5180 inspection, and the gated 1024-company full rerun remain pending.

### 2026-05-30 - Admin pipeline diagnostics and company detail evidence slice

Requirement coverage:
- Pipeline run detail API now returns upload-scoped company enrichment batch diagnostics, including source query/result/accepted/rejected counts, product/scenario/event counts, official product count, vector refresh count, LLM failure count, status/stage/miss-reason rollups, official-site failure reasons, rejected candidate reasons, source-adapter rollups, and a bounded company-level diagnostic sample.
- Pipeline run detail UI now shows batch progress, source acceptance/rejection, product/scenario/dynamic counts, vector refresh status, official failure categories, candidate rejection reasons, source distribution, and company-level failure samples.
- Company detail tests verify the company-specific summary label, business review order, business-facing product fields, and source links in the evidence section without leaking internal product fields.

Verification:
- `cd apps/admin-console && uv run --no-sync pytest tests/test_pipeline_runs_api.py tests/test_domains_postgres.py -q` -> passed, 49 tests.
- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/RecordDetail.test.tsx` -> passed, 6 tests.
- `cd apps/admin-console && uv run --no-sync ruff check backend/api/pipeline.py tests/test_pipeline_runs_api.py` -> passed.
- `python -m compileall -q apps/admin-console/backend/api/pipeline.py` -> passed.
- `cd apps/admin-console/frontend && npm run build` -> passed; Vite reported the existing large-chunk warning.
- `openspec validate company-scaleout-enrichment-hardening --strict` -> passed.

Remaining gaps:
- Company detail UI still keeps review actions/status out of the product business card to respect the six-field product display requirement; a separate review workflow surface remains pending.
- 5180 live search/detail navigation has not been rechecked in this slice.
- 200-company dry-run/live validation, touched-vector RAG smoke tests, and the gated 1024-company full rerun remain pending.

### 2026-05-30 - Batch idempotency and scale-validation report-shape slice

Requirement coverage:
- Upload-batch reports now include selected company IDs, enabled and skipped stages, source-adapter counts, miss-reason counts, vector refresh count, RAG smoke status, and residual risks for dry-run/live validation evidence.
- Product and application-scenario writers preserve source-tier evidence with duplicate-safe `WHERE NOT EXISTS` insertion paths.
- Financing signal insertion uses the `(company_id, event_type, dedup_key)` conflict guard and reports duplicate conflicts as zero inserted rows.
- Source rows from Yiou, PitchHub, generic Serper, and accepted generic source judgment remain duplicate-safe through source-URL conflict guards.
- Profile-summary backfill keeps the default only-missing selector, and Company vector refresh uses idempotent collection creation plus Milvus upsert semantics.

Verification:
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_source_product_extract.py tests/data_agents/company/test_source_product_extractor.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_narrative_backfill.py tests/scripts/test_run_milvus_backfill_company.py tests/data_agents/company/test_vectorizer.py -q` -> passed, 120 tests.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_official_product_capture.py tests/data_agents/company/test_generic_source_judgment.py tests/data_agents/company/test_yiou_adapter.py tests/data_agents/company/test_serper_news_connector.py -q` -> passed, 84 tests.
- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_upload_enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_official_product_capture.py tests/scripts/test_run_company_signal_extract.py` -> passed.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/admin-console/backend/api/pipeline.py` -> passed.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_pipeline_runs_api.py tests/test_domains_postgres.py -q` -> passed, 49 tests.
- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/RecordDetail.test.tsx` -> passed, 6 tests.

Remaining gaps:
- This slice verifies report shape and idempotent child-writer contracts; it does not replace the actual 200-company dry-run/live validation gates.
- 5180 live search/detail inspection, RAG smoke checks, and the gated 1024-company full rerun remain pending.

### 2026-05-30 - Representative sample selector and plan-only dry-run slice

Requirement coverage:
- Added a deterministic representative company selector for upload-scoped batches.
- The selector stratifies candidates by industry, website availability, and existing external-source coverage, then round-robins deterministically by bucket with `company_id` as the stable row order.
- Added `--representative-sample-size` to the upload enrichment batch runner so the 200-company validation gate does not depend on biased first-N `company_id` ordering.
- Added `--plan-only` so operators can generate a no-write validation plan with selected company IDs, selection metadata, enabled and skipped stages, configured stage policies, expected writes, blocked prerequisites, RAG smoke status, and residual risks.

Verification:
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/company/test_enrichment_batch.py::test_select_representative_company_sample_is_deterministic_and_stratified tests/scripts/test_run_company_upload_enrichment_batch.py::test_parse_args_accepts_dry_run_skip_flags tests/scripts/test_run_company_upload_enrichment_batch.py::test_process_batch_plan_only_uses_representative_sample_without_writes -q` -> RED before implementation, then passed, 3 tests.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py -q` -> passed, 31 tests.
- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_upload_enrichment_batch.py src/data_agents/company/enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py` -> passed.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` -> passed.

Remaining gaps:
- The no-write plan-only mode is implemented, and the post-optimization 200-company dry-run execution report is now stored under task 8.5 evidence.
- The live bounded 200-company validation, touched-vector RAG smoke checks, 5180 inspection, and gated 1024-company full rerun remain pending.

### 2026-05-30 - 200-company bottleneck evidence and pre-1024 scaleout gate

Requirement coverage:
- A 200-company dry-run was attempted for batch `4fe6c43d-2054-4732-b47f-2364dd48e9b2` with `--dry-run --skip-persistence --skip-milvus`, stage concurrency 2, LLM/web stage concurrency 2, and stage subchunks of 5 companies.
- The run timed out after 10,800 seconds with 175 selected companies completed and 25 selected companies stale-running in `generic_source_judgment`.
- Stale-running rows for that batch were closed precisely as failed with `last_error='wrapper_timeout_after_10800_seconds'`; no child processes remained.
- Business fact tables stayed unchanged during the retry after the dry-run no-write fix: `company_product`, `company_product_evidence`, `company_application_scenario`, `company_signal_event`, and `company_news_item` all had zero row-count delta. `company_enrichment_search_audit` increased as permitted dry-run audit evidence.
- The timeout is the measured go/no-go evidence for delaying 1024-company execution until child-script internal concurrency, provider rate limiting, per-company checkpointing, and model-routing verification are in place.

Verification:
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_upload_enrichment_batch.py -q` -> passed, 37 tests after dry-run no-write and timeout-report fixes.
- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_official_product_capture.py scripts/run_company_upload_enrichment_batch.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_upload_enrichment_batch.py` -> passed.
- `openspec validate company-scaleout-enrichment-hardening --strict` -> passed before this scaleout-gate update.

Remaining gaps:
- Task 8.5 is now complete after the post-optimization 200-company dry-run succeeded.
- A 200-company live bounded run is required before any 1024-company full dry-run/live execution.

### 2026-05-30 - Child concurrency, provider rate limiting, and checkpoint smoke

Requirement coverage:
- Added a provider rate-limit wrapper for OpenAI-compatible DeepSeek calls and requests-session Serper calls, with provider-specific environment controls for max concurrency and minimum request interval.
- Added child-script `--concurrency` controls for Company XLSX/team synthesis, generic source judgment, source-product extraction, news ingest, and signal extraction entrypoints.
- The upload-batch runner now passes `--child-llm-concurrency` and `--child-web-concurrency` into eligible child scripts and records the child concurrency settings in the run report.
- `run_company_xlsx_team_synthesis.py` now uses Company LLM routing directly: trusted XLSX structuring uses `deepseek-v4-lite`, while multi-source narrative synthesis uses `deepseek-v4-pro`.
- Per-company child checkpoints are written for XLSX/team synthesis, Yiou/PitchHub news ingestion, generic source judgment, and multi-source narrative synthesis, and the parent runner avoids overwriting already checkpointed companies when a shard fails.
- A 10-company post-optimization dry-run smoke batch `4c87b052-b9a3-4e93-8bd7-5f9186bd5f10` completed successfully with `--child-llm-concurrency 2 --child-web-concurrency 2`.
- The smoke run proved dry-run no business fact writes: deltas were zero for `company_product`, `company_product_evidence`, `company_application_scenario`, `company_signal_event`, and `company_news_item`; `company_enrichment_search_audit` increased by 52 audit rows.
- The smoke run proved per-company checkpoints: `generic_source_judgment`, `multi_source_narrative`, `news_iyiou`, and `news_pitchhub` each had 10 checkpointed company states.

Verification:
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/company/test_provider_rate_limit.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_signal_extract.py -q` -> passed, 99 tests.
- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_xlsx_team_synthesis.py scripts/run_company_source_product_extract.py scripts/run_company_generic_source_judgment.py scripts/run_company_news_ingest.py scripts/run_company_signal_extract.py scripts/run_company_upload_enrichment_batch.py src/data_agents/company/provider_rate_limit.py tests/data_agents/company/test_provider_rate_limit.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_upload_enrichment_batch.py` -> passed.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py apps/miroflow-agent/scripts/run_company_source_product_extract.py apps/miroflow-agent/scripts/run_company_generic_source_judgment.py apps/miroflow-agent/scripts/run_company_news_ingest.py apps/miroflow-agent/scripts/run_company_signal_extract.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/provider_rate_limit.py` -> passed.
- `DATABASE_URL=... uv run --no-sync python scripts/run_company_upload_enrichment_batch.py --batch-id 4c87b052-b9a3-4e93-8bd7-5f9186bd5f10 --representative-sample-size 10 --dry-run --skip-persistence --skip-milvus --chunk-size 10 --stage-concurrency 1 --llm-stage-concurrency 1 --web-stage-concurrency 1 --stage-subchunk-size 10 --stage-timeout-seconds 900 --stage-retry-budget 0 --retry-backoff-seconds 0 --sleep-seconds 0.05 --official-product-max-pages 2 --source-product-limit 1000 --child-llm-concurrency 2 --child-web-concurrency 2` -> succeeded; batch status `succeeded`, 10 processed, 0 failed.

Remaining gaps:
- The 10-company smoke is not a substitute for the 200-company dry-run gate.
- `source_product_extract` still performs internal LLM concurrency but does not yet provide a fully safe per-company completion checkpoint because it is news-row driven; parent-level idempotency and dry-run no-write coverage still protect persistence.
- The next validation step is a post-optimization 200-company dry-run before any live bounded run or 1024-company run.

### 2026-05-31 - 200-company post-optimization dry-run

Requirement coverage:
- Executed the post-optimization 200-company representative dry-run for batch `fb7eeffb-ca23-45bd-8116-0029f8aa32ce`.
- The run completed with status `succeeded`, 200 selected companies processed, 200 succeeded, and 0 failed.
- The run used `--dry-run --skip-persistence --skip-milvus`, child LLM concurrency 2, and child web concurrency 2.
- The run recorded model-routing evidence for lite/pro split: trusted XLSX/search hints use `deepseek-v4-lite`; source judgment, financing extraction, source-product admission, and multi-source synthesis use `deepseek-v4-pro`.
- Business fact tables had zero row-count delta. `company_enrichment_search_audit` increased by 1053 rows, matching the report query count.
- The run recorded 1053 queries, 513 fetches, 832 accepted sources, 1095 rejected sources, 122 source products extracted, 64 source scenarios extracted, 2 funding events extracted, and 192 multi-source narratives generated.

Verification:
- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py --batch-id fb7eeffb-ca23-45bd-8116-0029f8aa32ce --representative-sample-size 200 --dry-run --skip-persistence --skip-milvus --chunk-size 25 --stage-concurrency 2 --llm-stage-concurrency 2 --web-stage-concurrency 2 --stage-subchunk-size 10 --stage-timeout-seconds 1800 --stage-retry-budget 1 --retry-backoff-seconds 1 --sleep-seconds 0.05 --official-product-max-pages 3 --source-product-limit 4000 --child-llm-concurrency 2 --child-web-concurrency 2` -> passed.
- `.agents/runs/company-scaleout-enrichment-hardening/company-200-dry-run-post-optimization-20260530T1948Z.json` -> stored.
- `.agents/runs/company-scaleout-enrichment-hardening/company-200-dry-run-post-optimization-summary-20260531.md` -> stored.
- `.agents/runs/company-scaleout-enrichment-hardening/company-200-dry-run-post-optimization-20260530T1948Z.stderr.txt` -> empty.

Remaining gaps:
- The 200-company live bounded run, touched-vector refresh, RAG smoke checks, and representative 5180 inspection remain pending.
- Runtime is still too long for directly starting the 1024-company full dry-run/live rerun.
- `source_product_extract` per-company progress visibility, `news_ingest` true company-level concurrency, and target-customer metric reporting were fixed after this dry-run and require another bounded run to observe the improved report.
- Funding coverage remains low in this dry-run and should be improved before full live execution.

### 2026-05-31 - 200-company live bounded final validation and post-cleanup verification

Requirement coverage:
- Completed the fixed-sample 200-company live bounded validation gate for
  batch `66e8bcda-2030-42eb-84fb-5edefff97a43`: 200 selected companies
  processed, 200 succeeded, 0 failed, and 824 unselected imported companies
  remained queued.
- Replayed the strengthened generic-web identity guard against the accepted
  generic-web rows in the 200-company sample, then removed 90 near-name or
  wrong-legal-entity source rows and their derived evidence.
- Refreshed `profile_summary` and `technology_route_summary` for all 56
  affected companies after cleanup.
- Refreshed vectors for all 200 touched companies before RAG smoke, then
  re-refreshed the 56 cleanup-affected companies.
- Verified representative 5180 company detail behavior and label quality.

Evidence:
- Final validation summary:
  `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-final-validation-summary-20260531.md`.
- Live bounded report:
  `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-resume-provider8-subchunk1-20260531T0532Z.json`.
- Live bounded summary:
  `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-summary-20260531.md`.
- Cleanup report:
  `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-cleanup-20260531T071848Z.json`.
- Post-cleanup audit:
  `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-guard-post-cleanup-audit-20260531T071910Z.json`.
- Post-cleanup RAG smoke:
  `.agents/runs/company-scaleout-enrichment-hardening/company-post-cleanup-rag-smoke-pass5-20260531T074843Z.json`.
- 5180 OneGu inspection:
  `.agents/runs/company-scaleout-enrichment-hardening/5180-company-onegu-post-cleanup-inspection-20260531.json`.
- 5180 screenshots:
  `.agents/runs/company-scaleout-enrichment-hardening/screenshots/5180-company-metalenx-detail-20260531.png` and
  `.agents/runs/company-scaleout-enrichment-hardening/screenshots/5180-company-onegu-post-cleanup-20260531.png`.

Verification:
- `uv run --no-sync pytest apps/miroflow-agent/tests/data_agents/company/test_generic_source_judgment.py apps/miroflow-agent/tests/scripts/test_run_company_generic_source_judgment.py apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py -q` -> passed, 54 tests.
- `python -m py_compile apps/miroflow-agent/src/data_agents/company/generic_source_judgment.py apps/miroflow-agent/scripts/run_company_generic_source_judgment.py apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` -> passed.
- `openspec validate company-scaleout-enrichment-hardening --strict` -> passed.

Residual risks:
- The 1024-company full dry-run and live rerun remain pending under tasks
  9.5 through 9.9.
- The post-cleanup narrative refresh exposed long-tail LLM runtime; future
  full-scale execution should add per-call timeout and retry reporting inside
  LLM-heavy scripts.
- Product target-customer coverage remains a quality-improvement item, not a
  blocker for the current 200-company validation gate.

### 2026-05-31 - Post-dry-run concurrency and metric hardening

Requirement coverage:
- Fixed `run_company_news_ingest.py --concurrency` so company web/news fetches execute concurrently at company level instead of only accepting the CLI parameter.
- Fixed `run_company_source_product_extract.py` so it checkpoints every requested company, including companies that have no selected source rows.
- Added source-product checkpoint counters for source rows processed, product count, scenario count, products with target customers, and rejected candidate count.
- Added `products_with_target_customers` reporting to XLSX/team synthesis and source-product extraction, so upload-batch summaries no longer report a false zero when child reports contain target-customer products.

Verification:
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_news_ingest.py::test_cli_dry_run_processes_companies_concurrently_when_configured -q` -> RED before implementation, then passed.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py::test_cli_dry_run_extracts_products_without_insert tests/scripts/test_run_company_source_product_extract.py::test_cli_checkpoints_each_requested_company_even_without_source_rows -q` -> RED before implementation, then passed.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_xlsx_team_synthesis.py::test_process_company_synthesizes_publishable_products_from_xlsx -q` -> RED before implementation, then passed.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_upload_enrichment_batch.py -q` -> passed, 82 tests.
- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_news_ingest.py scripts/run_company_source_product_extract.py scripts/run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py` -> passed.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_news_ingest.py apps/miroflow-agent/scripts/run_company_source_product_extract.py apps/miroflow-agent/scripts/run_company_xlsx_team_synthesis.py` -> passed.

Remaining gaps:
- The post-dry-run fixes still need a bounded E2E rerun to measure runtime and corrected target-customer coverage.
- The 200-company live bounded run, touched-vector refresh, RAG smoke checks, representative 5180 inspection, and 1024-company execution remain pending.

### 2026-05-31 - 10-company post-fix dry-run smoke

Requirement coverage:
- Executed a 10-company dry-run smoke for batch `88cd2a26-bc87-401a-b4ed-2baa2a9a55ff` after the company-level news concurrency, source-product checkpoint, and target-customer reporting fixes.
- The run completed with status `succeeded`, 10 selected companies processed, 10 succeeded, and 0 failed.
- The run used `--dry-run --skip-persistence --skip-milvus`, stage concurrency 1, child LLM concurrency 2, and child web concurrency 2.
- Business fact tables had zero row-count delta. `company_enrichment_search_audit` increased by 52 rows, matching the dry-run `query_count=52`.
- The report recorded 52 queries, 22 fetches, 29 accepted sources, 53 rejected sources, 3 products extracted or synthesized, 1 product with target customers, 0 scenarios, 0 funding events, 10 multi-source narratives, and 20 rejected product/scenario candidates.
- The run confirmed the child-concurrency report shape and model routing evidence: trusted XLSX/search-hint tasks use `deepseek-v4-lite`; source judgment, financing extraction, source-product admission, and multi-source synthesis use `deepseek-v4-pro`.

Verification:
- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py --batch-id 88cd2a26-bc87-401a-b4ed-2baa2a9a55ff --dry-run --skip-persistence --skip-milvus --chunk-size 10 --stage-concurrency 1 --llm-stage-concurrency 1 --web-stage-concurrency 1 --stage-subchunk-size 10 --stage-timeout-seconds 900 --stage-retry-budget 0 --retry-backoff-seconds 0 --sleep-seconds 0.05 --official-product-max-pages 2 --source-product-limit 1000 --child-llm-concurrency 2 --child-web-concurrency 2` -> passed.
- `.agents/runs/company-scaleout-enrichment-hardening/company-10-dry-run-post-fix-20260531T0030Z.json` -> stored.
- `.agents/runs/company-scaleout-enrichment-hardening/company-10-dry-run-post-fix-summary-20260531.md` -> stored.
- `.agents/runs/company-scaleout-enrichment-hardening/company-10-dry-run-post-fix-20260531T0030Z.stderr.txt` -> empty.

Remaining gaps:
- This smoke validates wiring and no-write behavior for the post-dry-run fixes, but it is not a replacement for the 200-company live bounded validation.
- Target-customer coverage remains low in this sample; the only target-customer count came from XLSX/team synthesis, not source-product extraction.
- The `multi_source_narrative` stage remains slow enough that full 1024-company execution still requires bounded live validation and careful concurrency/rate-limit settings.

### 2026-05-30 - Live bounded sample mode and validation cleanup slice

Requirement coverage:
- The upload enrichment runner can now execute a representative sample in live mode while scoping every child command and Milvus refresh to selected company IDs only.
- Live bounded report metadata states the representative-sample scope, selected company IDs, expected writes, and `full_population_attempted=false`.
- Added `run_company_validation_cleanup.py` as a safe validation cleanup tool.
- Cleanup defaults to dry-run and, when applied, only deletes `company_enrichment_search_audit` rows for the batch and resets `company_enrichment_company_state` / `company_enrichment_batch` status counters for that batch.
- Cleanup explicitly does not touch production Company fact tables such as `company_news_item`, `company_signal_event`, `company_product`, `company_application_scenario`, or Milvus profiles.

Verification:
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py::test_process_batch_live_representative_sample_stays_bounded -q` -> passed, 1 test.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_validation_cleanup.py -q` -> RED before implementation, then passed, 2 tests.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_validation_cleanup.py -q` -> passed, 34 tests.
- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_upload_enrichment_batch.py scripts/run_company_validation_cleanup.py src/data_agents/company/enrichment_batch.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_enrichment_batch.py tests/scripts/test_run_company_validation_cleanup.py` -> passed.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/scripts/run_company_validation_cleanup.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` -> passed.

Remaining gaps:
- The actual 200-company dry-run has passed; the live run has not been executed yet.
- Validation report persistence, RAG smoke checks, 5180 inspection, and the gated 1024-company full rerun remain pending.

### 2026-05-30 - Official capture script option and page-reuse slice

Requirement coverage:
- Official capture now keeps page discovery, fetch-attempt diagnostics, JavaScript rendering fallback, material extraction, product extraction, and failure classification in separate helper paths.
- The official capture script exposes rendering, timeout, page-count, sitemap-discovery, and common-path-discovery controls.
- Failure taxonomy remains represented in dry-run reports through `official_capture_attempts` and `official_capture_failures`.
- Products are now extracted from the same diagnostic pages used for official source materials, so sitemap-discovered or JavaScript-rendered official pages are not lost by a separate legacy product-fetch path.

Verification:
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py::test_parse_args_accepts_dry_run_and_limit tests/scripts/test_run_company_official_product_capture.py::test_cli_dry_run_extracts_products_from_diagnostic_sitemap_pages -q` -> RED before implementation, then passed, 2 tests.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/scripts/test_run_company_official_product_capture.py tests/data_agents/company/test_official_product_capture.py -q` -> passed, 30 tests.
- `cd apps/miroflow-agent && uv run --no-sync ruff check scripts/run_company_official_product_capture.py tests/scripts/test_run_company_official_product_capture.py` -> passed.
- `python -m compileall -q apps/miroflow-agent/scripts/run_company_official_product_capture.py` -> passed.

Remaining gaps:
- Runtime validation on real websites is still part of the 200-company dry-run/live validation gate.

### 2026-05-30 - Company detail review-state UI slice

Requirement coverage:
- Company detail keeps the business order as basic information, products, application scenarios, recent dynamics, summaries, related records, and evidence.
- Product cards still show only the six business-facing fields: product name, product description, product category, technical tags, target customers, and application scenarios.
- Review state and review actions are now visible in a separate product/scenario control row instead of being exposed as raw `quality_status` or product IDs.
- Source links remain visible in the evidence section rather than being mixed into the product business fields.

Verification:
- `cd apps/admin-console/frontend && npm test -- --run src/pages/RecordDetail.test.tsx` -> RED before implementation, then passed, 5 tests.
- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/RecordDetail.test.tsx` -> passed, 7 tests.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_domains_postgres.py tests/test_pipeline_runs_api.py -q` -> passed, 49 tests.

Remaining gaps:
- 5180 live search/detail inspection remains pending.

### 2026-05-30 - Focused verification gate and LLM routing isolation fix

Requirement coverage:
- Company task-specific LLM routing now ignores broad `LOCAL_LLM_*` endpoint overrides when a task selects an explicit DeepSeek profile, preventing `.env`-loaded default Pro settings from overriding low-risk Lite tasks.
- The default shared professor/profile resolver still supports endpoint environment overrides for callers that rely on `LOCAL_LLM_MODEL`, `LOCAL_LLM_BASE_URL`, and matching API-key overrides.
- Added the Hydra `deepseek-v4-lite` LLM config so the Lite profile exists in both the shared resolver and the configuration surface.
- Company vector payload construction already includes long profile summaries, technology-route summaries, products, product categories, technical tags, target customers, application scenarios, structured team highlights, and source-backed recent funding details; focused vectorizer tests cover these fields.

Verification:
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/test_structured_output_mode.py tests/data_agents/company/test_llm_routing.py -q` -> RED before the routing isolation fix, then passed, 17 tests.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/professor/test_llm_profiles.py tests/data_agents/company/test_llm_routing.py -q` -> passed, 30 tests.
- `cd apps/miroflow-agent && uv run --no-sync pytest -n0 --no-cov tests/data_agents/company/test_llm_routing.py tests/data_agents/company/test_generic_source_judgment.py tests/data_agents/company/test_source_product_extractor.py tests/data_agents/company/test_official_product_capture.py tests/data_agents/company/test_enrichment_batch.py tests/data_agents/company/test_vectorizer.py tests/data_agents/company/test_yiou_adapter.py tests/data_agents/company/test_serper_news_connector.py tests/scripts/test_run_company_news_ingest.py tests/scripts/test_run_company_generic_source_judgment.py tests/scripts/test_run_company_signal_extract.py tests/scripts/test_run_company_source_product_extract.py tests/scripts/test_run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_narrative_backfill.py tests/scripts/test_run_company_official_product_capture.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/scripts/test_run_company_validation_cleanup.py tests/scripts/test_run_milvus_backfill_company.py -q` -> passed, 223 tests.
- `cd apps/miroflow-agent && uv run --no-sync ruff check src/data_agents/professor/llm_profiles.py src/data_agents/company/llm_routing.py` -> passed.
- `cd apps/miroflow-agent && uv run --no-sync python -m py_compile src/data_agents/professor/llm_profiles.py src/data_agents/company/llm_routing.py` -> passed.
- `cd apps/admin-console && uv run --no-sync pytest tests/test_domains_postgres.py tests/test_pipeline_runs_api.py tests/test_upload_pipeline_trigger.py tests/test_data_api_quality_status.py tests/test_data_api.py tests/test_chat_classifier_b_g_tune.py -q` -> passed, 92 tests and 7 skipped.
- `cd apps/admin-console/frontend && npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/RecordDetail.test.tsx src/pages/DomainList.test.tsx` -> passed, 8 tests.
- `cd apps/admin-console/frontend && npm run build` -> passed with the existing Vite large-chunk warning.
- `openspec validate company-scaleout-enrichment-hardening --strict` -> passed.

Remaining gaps:
- The actual 200-company dry-run validation has passed.
- The actual 200-company live bounded validation has not run.
- Touched-company vector refresh, RAG smoke checks, 5180 live inspection, and the gated 1024-company full rerun remain pending.

### 2026-05-31 - Provider-limiter concurrency and 200-company live bounded validation

Requirement coverage:
- Added upload-runner provider limiter overrides so batch reports and child processes can raise the real cross-process DeepSeek and Serper API concurrency caps without changing secrets or global configuration.
- Added explicit company-ID file support so the live validation sample remains fixed across resume attempts and does not drift when source coverage changes.
- The final live resume used company-level `--stage-subchunk-size 1`, preserving progress visibility and resume granularity for slow LLM/web stages.
- Executed the 200-company live bounded validation for batch `66e8bcda-2030-42eb-84fb-5edefff97a43`.
- The final run completed with status `succeeded`, 200 selected companies processed, 200 succeeded, 0 failed, and empty stderr.
- The DB batch row finished with `status=succeeded`, `companies_processed=200`, `companies_succeeded=200`, `companies_failed=0`, and `last_error=NULL`.
- Unselected imported companies remained queued; the run did not attempt the full population.

Verification:
- `cd apps/miroflow-agent && uv run --no-sync pytest apps/miroflow-agent/tests/scripts/test_run_company_upload_enrichment_batch.py -q` -> passed, 30 tests.
- `uv run --no-sync pytest apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py::test_mark_batch_finished_clears_stale_last_error_on_success apps/miroflow-agent/tests/data_agents/company/test_enrichment_batch.py::test_mark_company_stage_complete_updates_checkpoint_counters -q` -> passed, 2 tests.
- `python -m py_compile apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py apps/miroflow-agent/src/data_agents/company/enrichment_batch.py` -> passed.
- `DATABASE_URL=... uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py --batch-id 66e8bcda-2030-42eb-84fb-5edefff97a43 --company-id-file .agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-selected-company-ids.txt --chunk-size 25 --stage-concurrency 4 --llm-stage-concurrency 4 --web-stage-concurrency 4 --stage-subchunk-size 1 --stage-timeout-seconds 1800 --stage-retry-budget 1 --retry-backoff-seconds 1 --sleep-seconds 0.05 --official-product-max-pages 3 --source-product-limit 4000 --child-llm-concurrency 4 --child-web-concurrency 4 --provider-llm-max-concurrency 8 --provider-serper-max-concurrency 4 --skip-milvus` -> passed.
- `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-resume-provider8-subchunk1-20260531T0532Z.json` -> stored.
- `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-summary-20260531.md` -> stored.
- `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-resume-provider8-subchunk1-20260531T0532Z.stderr.txt` -> empty.

Observed live count deltas:
- `company_product`: 336 -> 668, delta +332.
- `company_product_evidence`: 1113 -> 2167, delta +1054.
- `company_application_scenario`: 227 -> 402, delta +175.
- `company_signal_event`: 617 -> 694, delta +77.
- `company_news_item`: 461 -> 1063, delta +602.
- `company_enrichment_search_audit`: 4845 -> 5892, delta +1047.

Remaining gaps:
- `milvus_refresh` was intentionally skipped in the live bounded run, so touched-vector refresh and RAG smoke checks remain pending.
- 5180 search/detail inspection remains pending.
- The final validation report remains pending until vector/RAG and 5180 evidence are added.
- Generic source judgment and multi-source narrative remain long-tail runtime hotspots; keep company-level subchunks before full-population execution.
