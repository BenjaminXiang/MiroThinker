# Change Log

## 2026-06-01

- Added a ten-query Company retrieval candidate-pool pilot before the full 50-query PRD Top-5 labeling pass.
- Rationale: the reviewer noted that some queries may not be answerable from the current 1024-company corpus and that ground truth is difficult to establish directly. The pilot separates corpus coverage gaps from retrieval failures.
- Scope: added candidate-pool export, corpus-gap-aware scoring, focused tests, acceptance evidence, and labeling instructions. The existing 50-query Top-5 harness remains available but is deferred as the immediate user review artifact.
- Added Round 1 readiness scope for full Company XLSX upload: canonical preflight, `docs/企业总表.xlsx` header mapping, trusted XLSX product/scenario preservation, shared-domain identity guarding, and safer upload enrichment defaults.
- Added Round 2 operator flow for Company upload enrichment: explicit start API, dedicated batch-progress page, PipelineRuns links, duplicate-upload preflight, and existing-company overlap diff samples.
- Added active duplicate upload rejection by content hash for admin-console uploads, including frontend SHA-256 preflight, backend HTTP 409 handling, and a hash-scoped Postgres advisory transaction lock for concurrent upload races.
- Changed Company XLSX upload post-processing to auto-start the upload-scoped Company enrichment batch and removed global retrieval-validation actions from Company upload runs to avoid unrelated RAG failures being presented as upload failures.
- Added a trusted-XLSX fallback narrative for sparse but valid upload rows so the enrichment batch does not finish with empty mandatory Company `profile_summary` / `technology_route_summary` fields when the LLM refuses sparse material.
- Extended Company list search to include latest XLSX `project_name` and `company_name_xlsx`, after a completed upload batch was not discoverable by the workbook project name.
- Added a customer/operator-facing Company upload processing overview on PipelineRuns detail so upload progress is understandable from one page rather than split across raw import summary and enrichment batch diagnostics.
- Raised Company upload enrichment concurrency defaults to 8 for stage shards, child LLM/Web workers, and DeepSeek/Serper provider limiters after checking host CPU, memory, and file descriptor headroom.
- Added Round 3 production-hardening scope for Company uploads: lightweight runner metadata and stale restart, durable uploaded-file storage, shared batch rollups, upload quality reports, clearer large-upload progress, miss-reason buckets, official-site fallback, bounded source-cache reuse, representative quality sampling, and a final publication-policy reconfirmation. Model-tier cost optimization remains deferred.
- Implemented Round 3 production hardening: V039 runner/report fields, durable uploaded-file archive with sidecar summary, runner pid/log/heartbeat recording, stale restart API, consistent batch rollups, quality report and miss-bucket API/UI fields, lightweight official-site JS-render fallback in upload batches, and Serper query-payload source cache for repeated enrichment runs.
