## 1. Verification Contract And Baseline

- [x] 1.1 Create `.agents/runs/paper-source-gap-remediation-lanes/verification-contract.md` with RED/GREEN evidence for source-gap lane reporting, fast-path no-source-acquisition behavior, full-text slow-lane failure buckets, no direct LLM fabrication, the professor-seeded boundary, and partial-run closure.
- [x] 1.2 Add a read-only current `miroflow_real` baseline artifact for active Paper gaps, source buckets, and primary remediation lane counts.
- [x] 1.3 Add RED tests for source-gap lane classification, precedence, representative samples, and deterministic selection hashes.

## 2. Source-Gap Audit

- [x] 2.1 Implement or extend a Paper source-gap audit module and CLI that classifies active Papers into one primary next-action lane plus secondary evidence.
- [x] 2.2 Add report fields for source buckets, lane counts, selected Paper ids, skipped reasons, samples, checkpoint metadata, and selection hashes.
- [x] 2.3 Add tests for existing abstract, identifier metadata, full-text slow lane, `prof_page_only` parser/title cleanup, review-only, and unsafe rows.
- [x] 2.4 Run a read-only source-gap audit on `miroflow_real` and record the artifact path in verification evidence.

## 3. Existing-Source Summary Fast Path

- [x] 3.1 Add an explicit CLI/report mode for existing-source-text summary generation that refuses DOI provider calls, title resolver calls, and PDF/full-text fetches.
- [x] 3.2 Preserve LLM Chinese summary generation, source-text provenance, boilerplate rejection, provider failure accounting, and pipeline-run closure for this lane.
- [x] 3.3 Add tests that prove the fast path selects only rows with usable existing source text and records processed, written, rejected, skipped, provider failures, and script-level row errors.
- [x] 3.4 Run bounded and then full parallel fast-path backfill for residual existing-source-text rows and record worker summaries.

## 4. Identifier Metadata Source Lane

- [x] 4.1 Add or rescope identifier enrichment so DOI, OpenAlex, Crossref, and arXiv rows update source fields without running summary generation in the same loop.
- [x] 4.2 Keep DOI quality gates and contradiction issue filing; add tests and report buckets for bad DOI, provider miss, provider error, and usable source persisted.
- [x] 4.3 Configure Crossref polite-pool `mailto` usage and provider timeout/rate-limit reporting for this lane.
- [x] 4.4 Run bounded identifier enrichment and re-audit newly source-backed rows before summary generation.

## 5. Full-Text Slow Lane

- [x] 5.1 Split PDF/full-text fetching into a bounded slow-lane CLI/report with timeout, HTTP status, content-type, size-cap, duplicate-content, and parse-failure counts.
- [x] 5.2 Persist usable abstract, intro, or excerpt evidence only; do not write `summary_zh` in the full-text slow lane.
- [x] 5.3 Add tests for 403, timeout, bad content type, size cap, duplicate PDF/content, and fetched-but-no-usable-text residuals.
- [x] 5.4 Run a capped slow-lane shard and close interrupted or superseded workers as `partial` with checkpoint evidence.

## 6. Prof-Page-Only Parser And Title Repair

- [x] 6.1 Audit remaining `prof_page_only` rows by title quality, official link evidence, source page, parser provenance, and existing identifier evidence.
- [x] 6.2 Add targeted parser/title cleanup for common pollution classes without author-name paper-list discovery.
- [x] 6.3 Run conservative title re-resolution shards and migrate or alias official Professor-page evidence only for high-confidence canonical matches.
- [x] 6.4 Record unresolved or low-confidence `prof_page_only` residuals with next-action evidence.

## 7. Final Summary And Residual Closure

- [x] 7.1 Re-run the existing-source summary fast path after source lanes produce new usable abstracts or excerpts.
- [x] 7.2 Re-audit active Paper gaps and residual buckets after all completed lanes.
- [x] 7.3 Update `acceptance.md`, `change-log.md`, and `.agents/runs/paper-source-gap-remediation-lanes/verification.md` with executed commands, artifacts, skipped checks, and remaining risks.
- [x] 7.4 Run `openspec validate "paper-source-gap-remediation-lanes" --strict` and the relevant targeted test suite before closing the change.
