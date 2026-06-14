# Acceptance Evidence

## Summary Completeness

- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py audit --sample-limit 20`
  - Initial observed state before repair: 1024 resolved companies, 10 missing `profile_summary`, 10 missing `technology_route_summary`.
- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py repair-summaries`
  - Result: selected 10 candidates, 10 repairable, 0 blocked.
  - Report: `.agents/runs/company-prd-acceptance-closure/company_summary_repair_dry_run.json`
- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py repair-summaries --apply --confirm-real-db`
  - Result: selected 10, repaired 10, blocked 0, post-counts `missing_profile_summary=0`, `missing_technology_route_summary=0`.
  - Report: `.agents/runs/company-prd-acceptance-closure/company_summary_repair_apply.json`
- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py audit --sample-limit 20`
  - Result: 1024 resolved companies, `missing_profile_summary=0`, `missing_technology_route_summary=0`.
  - Report: `.agents/runs/company-prd-acceptance-closure/company_prd_audit.json`

## Retrieval Top-5 Evaluation

- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py export-top5`
  - Result: 50 queries, 250 result rows, all 50 queries returned results, fallback reranker was not used.
  - User-label artifact: `.agents/runs/company-prd-acceptance-closure/company_top5_eval_unlabeled.csv`
  - Export report: `.agents/runs/company-prd-acceptance-closure/company_top5_eval_export.json`
- Status: The 50-query PRD Top-5 label pass is deferred. The gate is not claimed as passed yet.

## Retrieval Ten-Query Candidate-Pool Pilot

- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py export-candidate-pool --query-limit 10 --retrieval-top-k 20 --lexical-limit 30 --pool-limit 25`
  - Result: 10 pilot queries, 244 candidate rows, all 10 queries returned at least one candidate, fallback reranker was not used.
  - User-label artifact: `.agents/runs/company-prd-acceptance-closure/company_candidate_pool_10_unlabeled.csv`
  - Export report: `.agents/runs/company-prd-acceptance-closure/company_candidate_pool_10_export.json`
- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py score-candidate-pool --label-csv ../../.agents/runs/company-prd-acceptance-closure/company_candidate_pool_10_unlabeled.csv`
  - Result before labels: 10 unlabeled queries, no Top-5 pass/fail claim.
  - Score report: `.agents/runs/company-prd-acceptance-closure/company_candidate_pool_10_score.json`
- Status: The ten-query pilot is ready for user review. It distinguishes `answerable`, `corpus_gap`, and `uncertain` queries so corpus gaps are not counted as retrieval failures.

## Evidence and Source Traceability

- Command: real admin serializer call for `COMP-54fd4dd036ff`
  - Result: Company detail payload returned 4 products, 19 scenarios, 4 events, 9 top-level evidence entries, and product field evidence with source tier and source URL or stable XLSX identifier.
- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py evidence-audit --sample-limit 20`
  - Result: sampled 60 source-backed facts, `failure_count=0`.
  - Report: `.agents/runs/company-prd-acceptance-closure/company_evidence_audit.json`

## Duplicate-Pair Evaluation

- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py export-dedup-pairs --limit 120`
  - Result: 120 duplicate candidate pairs exported.
  - User-label artifact: `.agents/runs/company-prd-acceptance-closure/company_dedup_pairs_unlabeled.csv`
  - Export report: `.agents/runs/company-prd-acceptance-closure/company_dedup_pair_export.json`
- Status: PRD dedup accuracy gate is pending human labels. The gate is not claimed as passed yet.

## Incremental Refresh and Review-State Policy

- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py refresh-dry-run --company-id COMP-54fd4dd036ff --company-id COMP-302ee093a2d1 --limit 20`
  - Result: dry-run selected exactly the 2 explicit companies, wrote 0 business facts and 0 vectors.
  - Report: `.agents/runs/company-prd-acceptance-closure/company_refresh_dry_run.json`
- Command: `uv run --no-sync python scripts/run_company_prd_acceptance.py review-policy-sample --sample-limit 100`
  - Result: sampled 100 facts, 18 default-visible by policy, 82 review-gated.
  - Report: `.agents/runs/company-prd-acceptance-closure/company_review_policy_sample.json`

## Company Upload Full-Run Readiness Round 1

- Command: `uv run --no-sync pytest tests/data_agents/company/test_canonical_import_readiness.py tests/data_agents/company/test_source_product_extractor.py tests/scripts/test_run_company_xlsx_team_synthesis.py -q -n0`
  - Result: 39 passed.
- Command: `uv run --no-sync pytest tests/test_upload_pipeline_trigger.py -q`
  - Result: 16 passed, 4 FastAPI deprecation warnings.
- Command: `uv run --no-sync python - <<'PY' ... build_company_import_preflight(Path('../../docs/企业总表.xlsx')) ... PY`
  - Result: no-write preflight parsed 6,527 rows, generated 6,492 canonical IDs, found 34 duplicate generated-ID groups, 49 identity-conflict rows, 16 shared-domain risk rows, and 0 unresolved identity rows.
  - Field coverage: company name 6,527; project name 6,527; industry 6,515; region 6,527; business 6,520; established date 6,527; legal representative 6,521; contact email 6,310; product intro 5,381; product features 5,279; application scenarios 5,681.
- Implemented behavior:
  - Web Company dry-run now includes `canonical_preflight` with generated ID, new/matched count when existing lookup is available, identity conflicts, shared-domain risk samples, unresolved identity samples, and field coverage.
  - `docs/企业总表.xlsx` headers are mapped into canonical import values and retained in `raw_row_jsonb`.
  - XLSX product intro, product features, and application scenarios are included in the trusted XLSX product/scenario synthesis path.
  - Shared or platform hosts are not used as the sole canonical identity anchor.
  - Upload-created enrichment batches are now prepared for the upload scope; later Round 2 acceptance supersedes the original manual-start default with automatic post-import enrichment startup.
- Remaining readiness gaps after this round:
  - The Web UI still needs an explicit operator confirmation flow for running enrichment batches by limit, chunk size, stage, and status.
  - Duplicate same-file upload behavior still needs a visible idempotency or re-import confirmation message.
  - Existing-company overlap updates still need a user-facing difference report before a large real import.

## Company Upload Enrichment Operator Flow Round 2

- Command: `uv run --no-sync pytest tests/test_pipeline_runs_api.py tests/test_upload_pipeline_trigger.py -q`
  - Result: 31 passed, 4 FastAPI deprecation warnings.
- Command: `npm test -- --run src/pages/CompanyEnrichmentBatch.test.tsx src/pages/PipelineRuns.test.tsx`
  - Result: 2 files passed, 4 tests passed. jsdom emitted the known `getComputedStyle(... pseudo-elements)` not-implemented warning from Ant Design rendering.
- Command: `npm run build`
  - Result: build succeeded. Vite emitted the existing large-chunk warning for the single bundled app.
- Command: `uv run --no-sync pytest tests/data_agents/company/test_canonical_import_readiness.py tests/data_agents/company/test_source_product_extractor.py tests/scripts/test_run_company_xlsx_team_synthesis.py -q -n0`
  - Result: 40 passed.
- Implemented behavior:
  - Added `GET /api/pipeline/company-enrichment-batches/{batch_id}` for a dedicated batch-detail page.
  - Added `POST /api/pipeline/company-enrichment-batches/{batch_id}/start` so operators explicitly start a queued or partial Company enrichment batch after upload.
  - Start options include `limit`, `chunk_size`, `stage_preset`, `include_failed`, and `skip_milvus`.
  - Stage presets map to existing runner flags: `trusted_xlsx` skips live web, `high_trust_sources` skips generic Serper, and `full` runs all configured stages.
  - Added `/company-enrichment-batches/:batchId` frontend page with progress, stage/source counters, failure reasons, company diagnostics, and a start form.
  - PipelineRuns Company enrichment rows now link to the dedicated batch page.
  - Company upload dry-run now reports duplicate-upload preflight state and canonical overlap diffs for existing companies when DB lookup is available.
  - Company upload now rejects an active duplicate file hash before creating a new import run. The frontend computes the SHA-256 hash before upload and opens the existing active run when one is found; the backend takes a hash-scoped Postgres advisory transaction lock, repeats the same check, and returns HTTP 409 to protect against concurrent uploads.
- Remaining caveat:
  - The API starts the existing background batch runner and records a child `backfill_real` pipeline run; it does not inline-run the work inside the request thread.

## Active Duplicate Company Upload Rejection

- Command: `uv run --no-sync pytest tests/test_upload_pipeline_trigger.py -q`
  - Result: 17 passed, 4 FastAPI deprecation warnings.
- Command: `uv run --no-sync ruff check backend/api/upload.py tests/test_upload_pipeline_trigger.py`
  - Result: passed.
- Command: `npm test -- --run src/pages/DomainList.test.tsx`
  - Result: 1 file passed, 1 test passed.
- Command: `npm run build`
  - Result: build succeeded. Vite emitted the existing large-chunk warning for the single bundled app.
- Implemented behavior:
  - Added `GET /api/upload/{domain}/active-duplicate?file_content_hash=...` for frontend preflight.
  - Added backend duplicate enforcement in the upload handler before persisting a new source page or opening a new import run.
  - Active means an existing admin-console import run with the same file hash is still `running`, or its upload-scoped Company enrichment batch is `queued` or `running`.
  - Added frontend SHA-256 preflight for Company and Patent uploads; when an active duplicate is found, the upload is rejected in the UI and the operator is navigated to the existing pipeline run.

## Company Upload Auto-Enrichment And Validation Scope

- Command: `uv run --no-sync pytest tests/test_upload_pipeline_trigger.py tests/test_pipeline_runs_api.py tests/test_dashboard.py -q`
  - Result: 37 passed, 4 FastAPI deprecation warnings.
- Command: `uv run --no-sync ruff check backend/api/upload.py backend/api/pipeline.py backend/api/dashboard.py tests/test_upload_pipeline_trigger.py tests/test_pipeline_runs_api.py tests/test_dashboard.py`
  - Result: passed.
- Command: `npm test -- --run src/pages/PipelineRuns.test.tsx src/pages/DomainList.test.tsx src/pages/CompanyEnrichmentBatch.test.tsx`
  - Result: 3 files passed, 5 tests passed. jsdom emitted the known `getComputedStyle(... pseudo-elements)` not-implemented warning from Ant Design rendering.
- Command: `npm run build`
  - Result: build succeeded. Vite emitted the existing large-chunk warning for the single bundled app.
- Implemented behavior:
  - Successful Company XLSX imports now schedule the existing upload-scoped Company enrichment batch runner by default.
  - The legacy `COMPANY_UPLOAD_ENRICHMENT_AUTORUN=0` setting no longer leaves Company upload batches stuck in `queued`; an explicit emergency disable is available through `COMPANY_UPLOAD_ENRICHMENT_DISABLE_AUTORUN=1`.
  - Dashboard and PipelineRuns no longer offer global retrieval validation for Company XLSX uploads.
  - The backend rejects global retrieval validation requests for Company upload runs so unrelated patent/paper RAG failures cannot be recorded as Company upload failures.

## Trusted XLSX Narrative Fallback For Sparse Upload Rows

- Command: `uv run --no-sync pytest tests/scripts/test_run_company_xlsx_team_synthesis.py tests/data_agents/company/test_narrative_enrichment.py -q -n0`
  - Result: 22 passed.
- Command: `uv run --no-sync pytest tests/scripts/test_run_company_xlsx_team_synthesis.py -q -n0`
  - Result: 10 passed.
- Command: `uv run --no-sync ruff check scripts/run_company_xlsx_team_synthesis.py tests/scripts/test_run_company_xlsx_team_synthesis.py`
  - Result: passed.
- Command: `DATABASE_URL=<live admin DB> uv run --no-sync python scripts/run_company_xlsx_team_synthesis.py --company-id COMP-b3d846edf003 --include-source-materials --skip-team --dry-run --llm-timeout-seconds 180 --llm-retry-budget 1`
  - Result: succeeded; processed 1 company; `narratives_written=1`; `narrative_fallbacks=1`; `narratives_rejected=0`; `companies_with_errors=0`.
- Runtime verification against the four-company upload batch `a140b825-5a3d-412a-b5f2-e386d8e61f1e`:
  - Batch status: `succeeded`; progress 100%; selected 4; processed 4; succeeded 4; failed 0; `llm_failure_count=0`; status counts `{"succeeded": 4}`.
  - Mandatory summary check: all 4 companies have non-empty `profile_summary` and non-empty `technology_route_summary`.
  - Sparse-row example `COMP-b3d846edf003` / `竣浩科技`: fallback wrote a factual profile from XLSX trusted baseline and structured product facts after the LLM narrative result was `sparse_material`.
- Implemented behavior:
  - `run_company_xlsx_team_synthesis.py` now builds a conservative trusted-XLSX fallback narrative when the LLM refuses or under-produces a sparse but valid Company upload row.
  - The fallback only restates imported XLSX fields and already-structured product/scenario candidates; it explicitly avoids inventing financing, team, customer, or operating facts that are absent from the materials.
  - Fallback usage is recorded in per-company reports and enrichment stage diagnostics through `narrative_fallback_used` / `narrative_fallbacks` and the original LLM rejection reason.

## Company Upload Discoverability From XLSX Identifiers

- Command: `uv run --no-sync pytest tests/test_domains_postgres.py -q`
  - Result: 38 passed, 4 FastAPI deprecation warnings.
- Command: `uv run --no-sync ruff check backend/api/domains.py tests/test_domains_postgres.py`
  - Result: passed.
- Runtime verification:
  - Upload task `9d0b623b-4af0-4276-b102-21e7950231ea` finished as `succeeded`, imported 4 rows, and created enrichment batch `7d81d306-2bb6-4b47-bc86-bc917434ba47`.
  - Batch `7d81d306-2bb6-4b47-bc86-bc917434ba47` finished as `succeeded`; selected 4; processed 4; succeeded 4; failed 0; vector refreshed 4; `llm_failure_count=0`.
  - `GET /api/company?q=日行光学&page=1&page_size=5` returned `COMP-b3d846edf003` / `竣浩科技` with `project_name=日行光学`.
- Implemented behavior:
  - Company list search now includes `latest_snapshot.project_name` and `latest_snapshot.company_name_xlsx`, in addition to canonical name, registered name, and aliases.
  - This keeps ordinary Company search name-focused while making uploaded rows discoverable by the identifiers customers see in the XLSX workbook.

## Company Upload Processing Overview

- Command: `npm test -- --run src/pages/PipelineRuns.test.tsx`
  - Result: 1 file passed, 3 tests passed.
- Command: `npm run build`
  - Result: build succeeded. Vite emitted the existing large-chunk warning for the single bundled app.
- Implemented behavior:
  - Company upload PipelineRuns detail now shows an operator-facing `企业上传处理总览` before lower-level import summary and batch tables.
  - The overview uses the live `company_enrichment_batch` state instead of the stale upload-time `result_summary.enrichment.status`.
  - The overview includes a plain-language conclusion, current stage, total progress, import result, processed/succeeded/failed companies, product/scenario/event counts, vector refresh count, source accepted/rejected count, and direct links to the Company list and enrichment batch page.
  - The copy explicitly distinguishes immediately available baseline Company detail from still-running external enrichment.
  - Manual Milvus backfill is hidden for Company uploads while enrichment is still active, and after the upload-scoped batch has already refreshed vectors for all selected companies.

## Company Upload Enrichment Concurrency Scaleout

- Host capacity check:
  - `nproc`: 96.
  - `lscpu`: Intel Xeon Gold 5318Y, 2 sockets, 24 cores per socket, 2 threads per core.
  - `free -h`: 503 GiB total memory, 332 GiB available at check time.
  - `ulimit -n`: 1048576.
- Command: `uv run --no-sync pytest tests/scripts/test_run_company_upload_enrichment_batch.py tests/data_agents/company/test_provider_rate_limit.py -q`
  - Result: 37 passed.
- Runtime parse check:
  - Importing `scripts/run_company_upload_enrichment_batch.py` and parsing only `--batch-id` now yields `stage_concurrency=8`, `child_llm_concurrency=8`, `child_web_concurrency=8`.
  - `_provider_rate_limit_summary()` now reports `deepseek_max_concurrency=8` and `serper_max_concurrency=8`.
- Implemented behavior:
  - Company upload enrichment defaults now allow up to 8 stage shards for non-serialized stages.
  - Child LLM and Web worker defaults are both 8.
  - Cross-process DeepSeek and Serper provider limiters default to 8, while Milvus refresh and baseline readiness remain serialized.
  - Operators can still override the defaults through `COMPANY_UPLOAD_ENRICHMENT_*`, `COMPANY_DEEPSEEK_MAX_CONCURRENCY`, and `COMPANY_SERPER_MAX_CONCURRENCY` environment variables or explicit CLI flags.

## Company Upload Production Hardening Round 3

- Schema/runtime changes:
  - Added Alembic revision `V039` for `company_enrichment_batch` runner metadata, heartbeat/last-seen timestamps, last completed company, miss-reason buckets, and compact quality report JSON.
  - Applied `V039` to the current Postgres database used by the admin backend.
  - Restarted the admin backend on port `18188`; `/api/dashboard` returned HTTP 200 after restart, and the Vite frontend on port `5180` returned HTTP 200.
- Runner reliability:
  - Upload-scoped Company enrichment auto-run now records child process PID, log path, and heartbeat metadata.
  - Batch processing updates heartbeat and quality report at start, stage/chunk progress, and finish.
  - Stale detection now uses runner heartbeat/last-seen before falling back to updated-at.
  - Added `/api/pipeline/company-enrichment-batches/{batch_id}/restart-stale` for stale running batches.
- Durable upload files:
  - Admin uploads now persist under `data/admin_uploads/<domain>/<content-hash-prefix>/<task-id>/<original-filename>`.
  - A sidecar `.summary.json` is written next to the XLSX with source, domain, filename, content hash, task ID, path, and byte size.
- Progress/reporting:
  - PipelineRuns and dedicated Company enrichment batch detail now expose the same rollup classes for source counters, official-source failures, rejected candidate reasons, and LLM failure counts.
  - Dedicated batch and PipelineRuns detail pages show heartbeat time, runner PID/log path, last completed company, quality report headline, and operator-facing miss-reason buckets.
  - Runtime smoke check on the current API found the latest Company upload detail returned one enrichment batch with `quality_report` present and `miss_reason_buckets` populated.
- Source/fetch quality:
  - Upload batch official-site capture now passes the existing lightweight `--enable-js-render` fallback, which only renders pages identified as JavaScript-required or too short by the official-site capture logic.
  - Upload batch child processes set a persistent Company source cache directory, and Serper-backed search connectors reuse recent query-payload responses when `MIROTHINKER_COMPANY_SOURCE_CACHE_DIR` is set.
  - Miss reasons are normalized into operator buckets: `no_search_results`, `identity_mismatch`, `webpage_unavailable`, `llm_rejected`, `registration_only`, and `other`.
- Publication policy:
  - Existing publication policy remains in force: trusted XLSX, official-site, and strongly identity-judged facts can be visible without per-row manual review; weak generic Web facts remain conservative and review-gated.
  - The new reporting surfaces expose low-confidence buckets and quality samples instead of making all data require manual review.

## Round 3 Verification

- Command: `uv run --no-sync pytest tests/storage/test_v039_migration.py tests/data_agents/company/test_enrichment_batch.py tests/data_agents/company/test_serper_news_connector.py tests/scripts/test_run_company_upload_enrichment_batch.py -q`
  - Result: 70 passed.
- Command: `uv run --no-sync pytest tests/test_upload_pipeline_trigger.py tests/test_pipeline_runs_api.py -q`
  - Result: 35 passed, 4 FastAPI deprecation warnings.
- Command: `uv run --no-sync ruff check scripts/run_company_upload_enrichment_batch.py src/data_agents/company/enrichment_batch.py src/data_agents/company/news_connectors/serper.py tests/data_agents/company/test_enrichment_batch.py tests/data_agents/company/test_serper_news_connector.py tests/scripts/test_run_company_upload_enrichment_batch.py tests/storage/test_v039_migration.py`
  - Result: passed.
- Command: `uv run --no-sync ruff check backend/api/upload.py backend/api/pipeline.py tests/test_upload_pipeline_trigger.py tests/test_pipeline_runs_api.py`
  - Result: passed.
- Command: `npm run build`
  - Result: build succeeded. Vite emitted the existing large-chunk warning for the single bundled app.
- Command: `openspec validate company-prd-acceptance-closure --strict`
  - Result: passed.

## Tests and Checks

- Command: `uv run --no-sync pytest tests/scripts/test_run_company_prd_acceptance.py -q -n0`
  - Result: 11 passed.
- Command: `uv run --no-sync pytest tests/scripts/test_run_milvus_backfill_company.py -q -n0`
  - Result: 9 passed.
- Command: `uv run --no-sync pytest tests/test_domains_postgres.py -q`
  - Result: 37 passed, 4 deprecation warnings.
- Command: `uv run --no-sync python - <<'PY' ... execute run_milvus_backfill._COMPANY_SQL ... PY`
  - Result: Company vector backfill SQL compiled against the real database and returned one row.
- Note: `uv run pytest tests/test_domains_postgres.py -q -n0` without `--no-sync` failed before tests due a temporary PyPI mirror TLS handshake error for `anthropic`; the same test suite passed with `--no-sync`.

## User-Action Artifacts

- `.agents/runs/company-prd-acceptance-closure/company_candidate_pool_10_unlabeled.csv`
  - Fill `human_relevance_label` for each row with `hit`, `partial`, or `miss`.
  - Fill `query_answerability` for each query with `answerable`, `corpus_gap`, or `uncertain`.
  - Score with `score-candidate-pool`.
  - This is the current review artifact before the deferred 50-query pass.
- `.agents/runs/company-prd-acceptance-closure/company_top5_eval_unlabeled.csv`
  - Fill `human_label` with `hit`, `partial`, or `miss`.
  - Score with `score-top5`.
  - The 50-query direct Top-5 pass is deferred until after the ten-query pilot.
- `.agents/runs/company-prd-acceptance-closure/company_dedup_pairs_unlabeled.csv`
  - Fill `human_label` with `duplicate`, `not_duplicate`, or `uncertain`.
  - Score with `score-dedup-pairs`.
- `.agents/runs/company-prd-acceptance-closure/README.md`
  - Contains compact labeling instructions.
