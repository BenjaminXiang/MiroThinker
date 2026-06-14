## 1. Verification Contract And Baseline Evidence

- [x] 1.1 Create `.agents/runs/professor-core-profile-paper-quality/verification-contract.md` with RED/GREEN evidence for schema, pipeline, quality gate, API/frontend, chat citation, and badcase acceptance.
- [x] 1.2 Add a read-only baseline audit command for current Professor/Paper quality gaps, including summary length, missing research overview, missing `paper_summary`, duplicate verified paper title/year groups, and linked paper enrichment status.
- [x] 1.3 Add regression fixtures or scenario records for Ahmed Elazab, Ding Wenbo, and the pFedGPA paper from `docs/测试集答案.xlsx`.
- [x] 1.4 Record baseline audit output in `.agents/runs/professor-core-profile-paper-quality/verification.md` before production-code edits.

## 2. Schema And Storage Contracts

- [x] 2.1 Add an additive migration for durable Professor profile sections, including a Chinese research overview section with source page, source language, generation method, source hash/span, run id, and timestamps.
- [x] 2.2 Add an additive migration or equivalent storage for durable paper merge traceability from superseded paper id to canonical paper id.
- [x] 2.3 Update Professor storage models and writer helpers to persist and query profile sections without weakening existing `professor` table behavior.
- [x] 2.4 Update Paper storage helpers to read merge targets and resolve canonical paper ids for API, summary, and index consumers.
- [x] 2.5 Add migration tests and rollback/downgrade checks for the new storage.

## 3. Chinese Profile Section Extraction And Translation

- [x] 3.1 Implement official-profile research overview extraction into durable profile-section storage.
- [x] 3.2 Implement an idempotent LLM translation path for English official research overviews, keyed by source text hash and run id.
- [x] 3.3 Add quality validation for Chinese research overview output, including non-empty Chinese text and source traceability.
- [x] 3.4 Backfill or dry-run Ahmed Elazab's official English research overview into a Chinese research overview section.
- [x] 3.5 Add unit and integration tests for Chinese source overview, English-to-Chinese translation, missing source text, and source-hash idempotency.

## 4. Paper Canonical Deduplication And Enrichment

- [x] 4.1 Move or wrap DOI, arXiv, and title/year/author deduplication into the canonical Professor-homepage paper write path.
- [x] 4.2 Preserve official Professor-page evidence when migrating a page-only paper link to an enriched canonical paper row.
- [x] 4.3 Persist old-to-new paper merge traceability when page-only rows are merged or rejected.
- [x] 4.4 Ensure Professor paper summary inputs and Admin detail paper lists resolve merge aliases and exclude duplicate active title/year groups.
- [x] 4.5 Add regression coverage for Ahmed Elazab's duplicated Alzheimer paper and at least one generic duplicate title/year group.
- [x] 4.6 Add pFedGPA title enrichment coverage for arXiv id/PDF resolution when provider data is available.

## 5. Seed-Scoped Quality Closure Pipeline

- [x] 5.1 Implement an idempotent seed-scoped closure runner that chains homepage paper ingest, title enrichment/merge, paper enrichment, paper quality promotion, Professor output summaries, Professor quality re-evaluation, and index refresh selection.
- [x] 5.2 Update the admin seed full-run follow-up to schedule the closure only for successful full runs without a row limit.
- [x] 5.3 Ensure sample or limited seed runs cannot promote final Professor `ready` through this closure.
- [x] 5.4 File pipeline issues or run evidence for each failed closure stage with seed id, professor id, stage, and reason.
- [x] 5.5 Add tests for successful closure sequencing, idempotent rerun behavior, stage failure visibility, and sample-run non-promotion.

## 6. Professor Quality Gate And Output Summaries

- [x] 6.1 Extend persisted Professor quality evaluation to enforce 200-300 Chinese `profile_summary`, non-repetitive summary content, durable Chinese research overview when source material exists, and critical issue blocking.
- [x] 6.2 Require deduplicated eligible verified papers before `paper_summary` generation and Professor ready promotion.
- [x] 6.3 Generate or refresh Professor `paper_summary` from deduplicated eligible paper links only.
- [x] 6.4 Add Ding Wenbo regression coverage for complete core profile fields, non-repetitive Chinese summary, and missing company role not blocking Professor core readiness.
- [x] 6.5 Add before/after quality-status distribution reporting for dry-run and write-mode re-evaluation.

## 7. API, Frontend, And Chat Link Surfaces

- [x] 7.1 Update the Admin Professor detail API to return persisted Chinese research overview sections before raw-text fallback.
- [x] 7.2 Update the Admin Professor detail API to return deduplicated paper rows with `paper_id`, title, year, quality status, canonical source, and available external/PDF links.
- [x] 7.3 Update the React Professor workbench so paper titles link to `/paper/<paper_id>`.
- [x] 7.4 Update chat citation generation so local paper citations use the configured base URL plus `/paper/<paper_id>`.
- [x] 7.5 Add API tests, frontend tests, and chat regression tests for Professor paper link routing and obsolete browse-hash avoidance.

## 8. Backfill, Acceptance, And Release Evidence

- [x] 8.1 Run a plan-only duplicate paper audit and record affected rows, affected professors, and merge candidates.
- [x] 8.2 Run a bounded dry-run for Chinese research overview backfill and Professor output summary generation.
- [x] 8.3 Execute write-mode backfills only after dry-run evidence is recorded and reviewed.
- [x] 8.4 Verify Ahmed Elazab, Ding Wenbo, and pFedGPA acceptance scenarios against the real database and API.
- [x] 8.5 Run targeted unit/integration/frontend checks listed in the verification contract.
- [x] 8.6 Update `acceptance.md`, `change-log.md`, and `.agents/runs/professor-core-profile-paper-quality/verification.md` with commands, results, skipped checks, risks, and remaining blockers.
