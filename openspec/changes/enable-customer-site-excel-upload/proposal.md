# Proposal: enable-customer-site-excel-upload

Human doc: `docs/plans/2026-10-22-customer-site-excel-upload.md`
(execution log: `docs/plans/2026-10-22-customer-site-excel-upload-log.md`).

## Why

The customer needs upload → ETL → store → queryable for user-supplied materials, including Excel.
The existing admin company-document upload already writes operator-attested chunks into the manual
recall sidecar, which the serving runtime unions into the vector lane at query time. It accepts
PDF/DOCX/TXT/MD but rejects `.xlsx`; the separate `/upload` build import is unavailable on this
serving node (no build-time PostgreSQL).

## What Changes

- Extend the company-document upload to accept `.xlsx` **and analyse its structure first**:
  detect the header row, map columns to company/professor/patent/paper canonical fields, and
  recommend a domain + confidence before anything is written.
- Preview returns the analysis (`domain`, `confidence`, `mapping`, `row_count`, sample rows) plus the
  flattened text for the manual-recall fallback.
- Add `POST /company-documents/structured`: re-analyse the workbook and insert the mapped rows into
  the corresponding raw collection table (`company`, `professor`, `patent`, `paper`), with
  `quality_status='needs_review'` / `identity_status` as appropriate. It also writes a manual-recall
  document so the upload appears in the admin list.
- Update the data-browse upload panel to show the detected structure and a “按识别结构入库” button.

## Capabilities

### Modified Capabilities

- `manual-recall-company-documents` — XLSX structure analysis and domain-specific structured ingest.

## Impact

- No build-time PostgreSQL, serving-pack rebuild, or index change.
- Uploaded content is queryable immediately; citations point to the uploaded file label.
- Out of scope: structured canonical import of every row into `company`/`patent`/`professor`
  tables, and build-time index backfill. Large workbooks are capped at 24k characters per upload.
- Rollback: restore `canonical_v2_manual_recall.py` and `browse.html` from `.bak-xlsx-*`, restart.
