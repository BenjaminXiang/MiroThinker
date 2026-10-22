# Design: enable-customer-site-excel-upload

## Structure analysis

`backend/services/excel_structure.py` scans the first 12 rows of each sheet, scores every row
against four canonical alias maps (company/professor/patent/paper), and picks the row with the most
matches as the header. Every header is mapped to a canonical field; the domain with the largest
mapping wins. The preview returns `domain`, `confidence`, `mapping`, `row_count`, sample rows and
warnings. Unmatched columns are retained in `source_index` order so later values do not shift.

## Extraction / recall fallback

`openpyxl` still flattens the sheet into `header: value` blocks for the manual-recall fallback,
capped at 24,000 characters. The existing preview/confirm path remains for operators who want the
text-only sidecar.

## Structured ingest

`backend/services/excel_ingest.py` consumes the analysis + rows and upserts into the raw
collection tables:

| Domain | Table | Upsert key |
|---|---|---|
| company | `company` | `unified_credit_code`, else stable `company-upload-*` id |
| professor | `professor` (+ `professor_seed` when school/homepage) | stable name+school id |
| patent | `patent` | `patent_number`, else stable id |
| paper | `paper` | `doi`, else stable id |

All rows are written with `quality_status='needs_review'`; patent/paper use
`identity_status='unverified'`, professor/company `needs_review`. The endpoint also writes a
manual-recall document so the upload appears in the admin list.

## Query path

The manual sidecar is loaded into the serving runtime, but live diagnostics showed the answer
evidence retention drops manual candidates (see Known limitation). The structure-first ingest is
independent of that limitation: it writes the structured rows into the collection DB.

## Limits

- 10 MiB upload cap (existing).
- 24,000 extracted characters per upload; larger workbooks are truncated. Operators should split
  large files or upload per company.
- One `company_name` per confirmed document; the UI selects the company in data browse.

## Known limitation (2026-10-22)

Live diagnostics showed the manual provider is active (`active=3`), the query lane appends all
three upload chunks (`appended=3`, top cosine `0.8754`), but the final `retrieval_done` and answer
retain only release/web evidence. The upload is stored and listed, but chat auto-recall is **not**
working; the next slice must change answer evidence retention or add a dedicated upload evidence
lane. The experimental score boost and 2-slot reservation were reverted.

## Out of scope

- Structured `import_company_xlsx_to_postgres` / build-time PG import.
- Serving-pack/index rebuild so uploaded rows appear in the release lookup view.
- Bulk multi-company workbook splitting.
