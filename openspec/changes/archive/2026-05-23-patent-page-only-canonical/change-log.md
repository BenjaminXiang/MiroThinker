# Change Log: patent-page-only-canonical

## 2026-05-15 - Initial scope

- Expanded ledger placeholder into a full OpenSpec change for
  title-only page patent canonical handling.

## 2026-05-23 - Storage strategy selected

- Selected nullable canonical patent rows instead of a separate
  `patent_candidate` table.
- Recorded the rationale and rollback behavior in `design.md`.
- Added V026 migration coverage for nullable page-only rows, numbered
  patent uniqueness, and downgrade backfill.

## 2026-05-23 - Evidence URL persistence

- Added V032 to persist homepage patent evidence URL / anchor on
  `professor_patent_link`.
- Updated homepage patent ingest so title-only and numbered prof-page
  patent links retain provenance while preserving existing link
  idempotency.

## 2026-05-23 - Title-only promotion behavior

- Defined same-professor/same-evidence/same-title promotion semantics in
  `design.md`.
- Updated homepage patent ingest so a later page-discovered patent
  number promotes the existing title-only canonical row when no other
  row owns that patent number.
- Added malformed blank-title handling so invalid candidates remain
  `pipeline_issue` diagnostics and do not become canonical rows.
