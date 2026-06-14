## 1. Baseline Audit and Summary Completeness

- [x] 1.1 Add a Company PRD acceptance audit script that reports mandatory summary completeness, product/scenario/event coverage, review-state counts, and evidence/source boundary samples.
- [x] 1.2 Add focused tests for the audit report shape and missing-summary detection.
- [x] 1.3 Add or extend a Company summary repair path that backfills missing `profile_summary` and `technology_route_summary` from trusted XLSX baseline and accepted source material without fabricating sparse records.
- [x] 1.4 Run the summary audit and repair against the current database, then record pre-run and post-run missing counts under `.agents/runs/company-prd-acceptance-closure/`.

## 2. Top-5 Retrieval Relevance Evaluation

- [x] 2.1 Add a deterministic 50-query Company retrieval evaluation query set covering enterprise product, technology, industry, financing, and application-scenario questions.
- [x] 2.2 Add a script that runs the active Company retrieval path and exports an annotation-ready Top-5 CSV with company context, scores, product/scenario snippets, and evidence hints.
- [x] 2.3 Add a scoring mode that reads human labels and computes Top-5 hit rate, Top-1 hit rate, Precision@5, partial rate, and failure reasons.
- [x] 2.4 Run the unlabeled CSV export on the current database and record the artifact path for user labeling.

## 3. Evidence/Source API and Release Contract

- [x] 3.1 Add focused tests proving Company detail API and release payloads expose source/evidence metadata for products, scenarios, signal events, profile summaries, and technology summaries when storage contains evidence.
- [x] 3.2 Repair serializers or helper functions so API/release payloads retain source URL or stable XLSX source identifiers, source type/tier, timestamps, and field-level evidence when available.
- [x] 3.3 Add an evidence/source audit mode that samples Company detail and release payloads and reports missing field paths by company ID.
- [x] 3.4 Run a representative evidence/source audit and record pass/fail counts and failing examples.

## 4. Duplicate-Pair Deduplication Evaluation

- [x] 4.1 Add a script that exports at least 100 Company candidate duplicate pairs with comparison fields and system prediction.
- [x] 4.2 Add a scoring mode that reads human labels `duplicate`, `not_duplicate`, or `uncertain`, excludes `uncertain`, and computes accuracy, true positives, false positives, true negatives, and false negatives.
- [x] 4.3 Add focused tests for candidate export shape and scoring math.
- [x] 4.4 Run the candidate-pair export on the current database and record the artifact path for user labeling.

## 5. Incremental Refresh and Review-State Policy

- [x] 5.1 Add or verify a monthly/on-demand refresh dry-run mode that selects companies by uploaded IDs, explicit IDs, stale source timestamps, missing mandatory fields, or operator request and reports selected scope without writing facts.
- [x] 5.2 Add focused tests for refresh selection and checkpoint/resume report fields.
- [x] 5.3 Implement a Company review-state publication policy helper that separates visible high-confidence XLSX/official/source-judged facts from low-confidence generic or weakly attributed facts.
- [x] 5.4 Add focused tests proving high-confidence facts are visible without per-row human review and low-confidence generic facts are excluded from default detail/retrieval payloads.
- [x] 5.5 Run a refresh dry-run and review-policy sample report against the current database.

## 6. Verification and Acceptance Evidence

- [x] 6.1 Run focused Company and admin-console tests touched by this change.
- [x] 6.2 Run `openspec validate company-prd-acceptance-closure --strict`.
- [x] 6.3 Update `openspec/changes/company-prd-acceptance-closure/acceptance.md` with commands, report paths, pass/fail status, and user-labeling items.
- [x] 6.4 Leave clearly named user-action artifacts for Top-5 relevance labels and duplicate-pair labels, without claiming those gates passed before labels exist.

## 7. Ten-Query Candidate-Pool Pilot

- [x] 7.1 Add a ten-query Company retrieval pilot before the full 50-query PRD review, covering product, technology, industry, and application-scenario intents.
- [x] 7.2 Export a candidate-pool CSV that merges active semantic retrieval candidates with lexical/product/scenario candidates from the current 1024-company corpus.
- [x] 7.3 Add scoring that separates `answerable`, `corpus_gap`, `uncertain`, and unlabeled queries, then computes Top-5 metrics only for answerable queries.
- [x] 7.4 Add focused tests for the ten-query pilot set, lexical candidate expansion, and corpus-gap-aware scoring.
- [x] 7.5 Run the ten-query candidate-pool export on the current database and record the artifact path for user labeling.
- [x] 7.6 Update acceptance evidence and labeling instructions so the 50-query direct Top-5 review remains deferred until the pilot is reviewed.

## 8. Company Upload Full-Run Readiness Round 1

- [x] 8.1 Add canonical upload preflight reporting for generated identity IDs, new/matched/conflict counts, duplicate generated IDs, shared-domain risks, and field coverage.
- [x] 8.2 Extend Company XLSX header mapping for `docs/企业总表.xlsx`, including industry, region, established date, legal representative, email, product intro, product features, and application scenarios.
- [x] 8.3 Preserve trusted XLSX product/scenario fields in the XLSX product/scenario synthesis path so they can populate structured product and scenario tables during upload enrichment.
- [x] 8.4 Add an identity guard so shared or platform domains are not used as the sole Company identity anchor.
- [x] 8.5 Make Web upload safe by default: skeleton import may enqueue an enrichment batch, but full external enrichment must not auto-run unless explicitly enabled.
- [x] 8.6 Run focused upload/import/product synthesis tests and update acceptance evidence with remaining readiness gaps.

## 9. Company Upload Enrichment Operator Flow Round 2

- [x] 9.1 Add an explicit API for starting a queued Company enrichment batch after operator confirmation, with limit, chunk size, stage preset, include-failed, and Milvus options.
- [x] 9.2 Add backend status/detail payloads suitable for a dedicated Company enrichment batch page, including progress percentage, running stage, failed stage, failed reason, and per-company diagnostics.
- [x] 9.3 Add a dedicated frontend page for Company enrichment batches with a start form, progress display, stage/source counters, and failure reason summaries.
- [x] 9.4 Link upload/PipelineRuns Company enrichment batches to the dedicated page.
- [x] 9.5 Add duplicate upload idempotency/preflight messaging and existing-company overlap diff reporting at the safest available scope.
- [x] 9.6 Preserve product/scenario ownership judgment and evidence in the operator-facing batch diagnostics where source material is available.
- [x] 9.7 Run focused backend/frontend tests and update acceptance evidence.
- [x] 9.8 Reject active duplicate Company Excel uploads by content hash before creating a new import run, with frontend preflight and backend race protection.
- [x] 9.9 Start Company enrichment automatically after successful XLSX import and prevent global retrieval-validation failures from being presented as Company upload failures.
- [x] 9.10 Add trusted-XLSX narrative fallback so sparse but valid uploaded rows do not complete enrichment with empty mandatory Company summary fields.
- [x] 9.11 Include trusted XLSX project names and original XLSX company names in Company list search so uploaded rows are discoverable from the identifiers customers see in the workbook.
- [x] 9.12 Add an operator-facing Company upload processing overview to the PipelineRuns detail page so customers can see upload, import, enrichment, extraction, narrative, and search-refresh completion in one place.
- [x] 9.13 Raise Company upload enrichment concurrency defaults to 8 for stage shards, child LLM/Web workers, and DeepSeek/Serper provider limiters after confirming the host has enough CPU and memory headroom.

## 10. Company Upload Production Hardening Round 3

- [x] 10.1 Add lightweight runner reliability metadata for upload-scoped Company enrichment batches: process ID, log path, heartbeat/last-seen timestamp, stale detection, and a safe restart action for stale or failed batches.
- [x] 10.2 Persist uploaded Company XLSX files under a stable data directory keyed by domain, content hash, and task ID, while preserving the original source filename for audit and reruns.
- [x] 10.3 Deduplicate Company enrichment batch rollup logic so PipelineRuns and the dedicated batch detail endpoint expose the same source counters, rejected reasons, official-source failures, and LLM failure counts.
- [x] 10.4 Generate and expose a compact per-upload quality report covering import counts, enrichment counts, product/scenario/dynamic counts, failed companies, major miss reasons, and sample Company links.
- [x] 10.5 Improve large-upload progress clarity with last heartbeat, runner PID/log path, last completed or updated Company diagnostics, and plain-language stage notes.
- [x] 10.6 Normalize external-source miss reasons into operator-facing buckets such as no search results, identity mismatch, fetch failure, LLM rejection, registration-only source, and unknown.
- [x] 10.7 Add a lightweight official-site fallback path that can use Playwright rendering only when static fetch is missing, too short, or otherwise low-value; do not add a general crawling platform.
- [x] 10.8 Add bounded source-search cache reuse for repeated Company upload/enrichment runs so recent Serper/source results can be reused by company, adapter, query, and URL hash.
- [x] 10.9 Add a small product/scenario quality sample report for representative Company rows, focused on ownership, target customers, application scenarios, and evidence presence.
- [x] 10.10 Reconfirm structured-field publishing policy for trusted XLSX/official/source-judged facts versus weak generic Web facts after the new reporting surfaces are in place.
- [x] 10.11 Run focused backend/frontend/agent tests and update acceptance evidence.
