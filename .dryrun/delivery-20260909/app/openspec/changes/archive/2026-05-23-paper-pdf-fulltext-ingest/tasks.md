# Tasks: paper-pdf-fulltext-ingest

## 1. PDF discovery

- [x] T1.1: Extend professor publication parsing to preserve direct PDF
  links.
- [x] T1.2: Attach PDF links to page-discovered paper candidates.
- [x] T1.3: Add tests for relative, absolute, and DOI-adjacent PDF
  links.

## 2. Fetch and caps

- [x] T2.1: Extend full-text fetcher for professor-page PDF URLs.
- [x] T2.2: Enforce byte-size, timeout, content-type, redirect, and
  per-run caps.
- [x] T2.3: File `pipeline_issue` diagnostics for cap violations.
- [x] T2.4: Add mocked HTTP tests for each cap.

## 3. Persistence

- [x] T3.1: Persist raw PDF by sha256 or approved blob reference.
- [x] T3.2: Write extracted text to `paper_full_text` with provenance.
- [x] T3.3: Dedupe repeated PDF fetches by sha256.
- [x] T3.4: Add persistence tests.

## 4. Verification

- [x] T4.1: Run paper full-text tests.
- [x] T4.2: Run homepage ingest tests affected by PDF links.
- [x] T4.3: Run a bounded sample with direct professor-page PDF links.
