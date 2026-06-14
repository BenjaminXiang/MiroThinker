# Acceptance: paper-pdf-fulltext-ingest

## Spec validation

- [x] `openspec validate paper-pdf-fulltext-ingest` exits 0.

## PDF ingest

- [x] Direct professor-page PDF links are discovered.
- [x] Fetch caps are enforced and tested.
- [x] Raw PDF bytes or blob references are keyed by sha256.
- [x] Extracted text is written to `paper_full_text` with provenance.
- [x] Duplicate PDFs are deduped by sha256.
