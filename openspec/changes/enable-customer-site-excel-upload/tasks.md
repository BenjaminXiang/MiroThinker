# Tasks: enable-customer-site-excel-upload

- [x] 1.1 Add `.xlsx` to the allowed suffixes and extract rows with `openpyxl`.
- [x] 1.2 Return `row_count` in preview; keep the 24k extraction cap.
- [x] 1.3 Accept `.xlsx` in the data-browse upload input and hint text.
- [x] 1.4 Add a preview regression test; run the manual recall API tests + ruff.
- [x] 1.5 Attempt an exact display-name/model-token boost; reverted after it did not change the answer.
- [x] 1.6 Deploy the backend files and `browse.html`; restart.
- [x] 1.7 Live preview a 2-row company workbook.
- [x] 1.8 Confirm the workbook and verify a manual recall point is created.
- [x] 1.9 Verify a chat query can recall the uploaded content, including a unique model token.
  Product+attribute, product-only and company-name queries answer with the uploaded token and
  cite the manual handle; an unrelated query cites no upload; the reverted document disappears
  from answers. Evidence: `.agents/runs/enable-customer-site-excel-upload/verification.md` §7.
- [x] 1.10 Update docs and human log.

## 2. Structure-first ingest

- [x] 2.1 Add `excel_structure.analyze_workbook` for company/professor/patent/paper; add four-domain tests.
- [x] 2.2 Add `excel_ingest` structured upserts for company/professor/patent/paper.
- [x] 2.3 Add `POST /company-documents/structured`, preview analysis payload, and the upload-panel button.
- [x] 2.4 Live company ingest: 2 rows inserted into `company` with `needs_review`.
- [x] 2.5 Live professor/paper ingest: one row each inserted.
- [x] 2.6 Live patent ingest after `_patent_type` normalization restart.
- [x] 2.7 Update user/ops docs and PDF with the structure-first flow.
