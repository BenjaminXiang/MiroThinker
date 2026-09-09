# Acceptance: patent-page-only-canonical

## Spec validation

- [x] `openspec validate patent-page-only-canonical` exits 0.

## Storage decision and migration

- [x] Nullable canonical-row strategy is recorded in `design.md`.
- [x] V026 allows `patent.patent_number` to be NULL while keeping numbered
  patent uniqueness.
- [x] V026 downgrade restores `patent_number` to NOT NULL without deleting
  title-only rows.
- [x] Professor-patent links persist page evidence URL / anchor for
  prof-page patent rows.

## Title-only patent handling

- [x] Title-only patent page evidence is persisted.
- [x] Initial status is `needs_enrichment`, not `ready`.
- [x] Repeated ingest is idempotent.
- [x] Numbered patents still hard-match on patent number.
- [x] A later confirmed patent number can promote or merge the
  title-only candidate.
