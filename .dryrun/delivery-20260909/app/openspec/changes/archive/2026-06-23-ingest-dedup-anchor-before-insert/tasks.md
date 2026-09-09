# Tasks — ingest-dedup-anchor-before-insert

> Status 2026-06-23: fix applied (removed author-overlap gate → title+year-only content
> anchor) + 194 homepage_ingest tests GREEN. Archiving (real-DB ingest 4.1 deferred).

## 1. Verification contract & baseline
- [x] 1.1 Verification contract = this OpenSpec change (the spec/design define the RED/GREEN).
- [x] 1.2 Baseline: 25,527 dup groups + 162x biggest (confirmed 2026-06-22 scan); root cause = author-overlap gate miss (confirmed 2026-06-23 investigation).

## 2. Content-anchor dedup fix
- [x] 2.1 Extended `_find_existing_canonical_homepage_paper` (homepage_ingest.py:2482) — removed the author-overlap gate (lines 2510-2519) → title+year-only content anchor.
- [x] 2.2 Anchor normalization = `_page_only_reuse_title_key` (matches `canonical_writer._build_paper_id`'s title branch).
- [x] 2.3 The query follows `paper_merge_alias` (existing JOIN at lines 2528-2532, unchanged).

## 3. Tests (RED → GREEN)
- [x] 3.1 RED: `test_page_only_publication_reuses_existing_canonical_title_year` (updated — asserts `not any("authors_display" in sql)`, the gate is gone).
- [x] 3.2 Normalization consistency verified (code review — `_page_only_reuse_title_key` ≡ `_build_paper_id` title fallback).
- [x] 3.3 GREEN: 194 homepage_ingest tests passed.
- [x] 3.4 Regression: existing same-prof dedup tests pass (194 total).

## 4. Real evidence
- [ ] 4.1 Deferred — real-DB ingest (2 profs, same co-authored paper → 1 paper + 2 links). Unit tests are the primary evidence.

## 5. Acceptance, validation, ledger
- [x] 5.1 `acceptance.md` filled.
- [x] 5.2 `openspec validate ingest-dedup-anchor-before-insert --strict` exits 0.
- [x] 5.3 Registered in `openspec/change-ledger.md`.
