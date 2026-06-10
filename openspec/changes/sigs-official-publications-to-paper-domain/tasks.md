## 1. Parser Regression

- [x] 1.1 Add Ahmed SIGS RED regression covering author-prefixed numbered citations.
- [x] 1.2 Add regression coverage proving official publication extraction is not truncated to a fixed top-N.
- [x] 1.3 Implement SIGS author-prefixed citation splitting so `clean_title`, `authors_text`, `venue_text`, and `year` are correct.
- [x] 1.4 Add LLM-assisted extraction fallback tests for variable SIGS and cross-institution citation formats with source-span validation.

## 2. Paper-Domain Bridge

- [x] 2.1 Add bridge tests proving more than five official page publications are resolved/upserted/linked.
- [x] 2.2 Add bridge guard/tests preventing malformed author-list titles from reaching external title resolution.
- [x] 2.3 Implement bridge guard and ensure `professor_paper_link` uses `link_status='verified'`, `is_officially_listed=true`, and page-tier evidence.
- [x] 2.4 Wire homepage paper ingest and CLI to optionally use the validated LLM publication extractor.
- [x] 2.5 Add Crossref, Semantic Scholar, and DBLP title-level resolver cascade before arXiv/web fallback, with conservative confidence tests and DBLP canonical-source storage support.

## 3. Summary, Full-Text, And Index Follow-Up

- [x] 3.1 Verify the summary backfill path can target Ahmed or linked paper IDs with DOI metadata enrichment.
- [x] 3.2 Verify page-only papers without abstracts do not fabricate `abstract_clean` and remain enrichment/review candidates.
- [x] 3.3 Verify targeted paper Milvus refresh can be driven by linked paper IDs or changed-since after summary updates.
- [x] 3.4 Add institution-scoped paper `summary_zh` backfill support so SIGS can be processed as one bounded batch.

## 4. Runtime Rollout

- [x] 4.1 Run Ahmed dry-run and record publication count, title correctness, resolver hits, page-only count, and issue count.
- [x] 4.2 Run Ahmed real paper/link bridge when DB and provider prerequisites are available.
- [x] 4.3 Run Ahmed summary backfill and targeted paper Milvus refresh when prerequisites are available.
- [x] 4.4 Run a random SIGS 10-professor sample and record per-professor parse/ingest/enrichment outcomes.
- [x] 4.5 Run full SIGS with a resume checkpoint after Ahmed and sample acceptance.
- [x] 4.6 Run a cross-institution parser quality audit and record non-SIGS suspicious/low-recall findings.
- [x] 4.7 Validate sampled SIGS records in both frontend detail pages and backend retrieval/chat recall after Milvus refresh.

## 5. Acceptance And Reporting

- [x] 5.1 Record OpenSpec acceptance evidence for parser tests, ingest tests, Ahmed validation, summary/index checks, and any skipped prerequisites.
- [x] 5.2 Update `tasks.md` statuses as each slice is completed.
- [x] 5.3 Report remaining failure reasons and rollout risks without claiming unverified completion.
- [x] 5.4 Record a version checkpoint for the SIGS paper parser/bridge/resolver/summary/report slice and its V024-V040 migration-chain dependency before further rollout writes.
