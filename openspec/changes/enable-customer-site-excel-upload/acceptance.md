# Acceptance: enable-customer-site-excel-upload

| # | Criterion | Evidence |
|---|---|---|
| A1 | XLSX preview works | `_extract_text("测试企业材料.xlsx")` → `xlsx`, 2 row blocks, header/value text |
| A2 | API preview accepts XLSX | test `test_preview_xlsx_flattens_rows` passes; live preview returns `row_count=2` |
| A3 | Confirm stores recall chunks | live `/company-documents` returns `doc_id` + `chunk_count`; `manual-recall.json` point count increases |
| A4 | Immediate queryability | **Passed** (2026-10-23): upload `doc-924835…` (STRICT-9000 / 30kg) — product+attribute, product-only and company-name queries all answer with the uploaded token and cite `local-source-57861b25eafa73e0`; unrelated query cites no upload; after revert the same query returns “no public information”. A fresh post-restart upload `doc-c831b705…` (NOVA-7700 / 18kg) passes company-name and product-only queries with `local-source-3947662581cc8a44`. |
| A5 | No build/index dependency | no `DATABASE_URL`, no serving-pack change, no restart needed after confirm |
| A6 | Tests / lint | `test_excel_structure.py` + manual recall API: 18 passed; ruff clean |
| A7 | Structure detection | company/professor/patent/paper workbooks detected with `high` confidence and correct mappings |
| A8 | Company structured ingest | live endpoint: 2 rows inserted into `company`, `quality_status=needs_review`, unique credit codes |
| A9 | Professor/paper structured ingest | live endpoint: 1 professor + 1 paper inserted; `professor_seed` row created for the professor |
| A10 | Patent structured ingest | live endpoint after normalization: 1 row inserted, `patent_type='发明'`, unique patent number |
| A11 | UI structure display | preview shows domain/confidence/mapping; “按识别结构入库” button posts the file |

## Rollback

Restore `canonical_v2_manual_recall.py` / `excel_structure.py` / `excel_ingest.py` / `browse.html`
from `.bak-*`, restart; optionally delete the test rows by their `*-upload-*` ids.

The 2026-10-23 recall fix touches
`apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` and
`knowledge_serving_isolated.py`; restore their `.bak-manualquery-20261023-0032`
copies and restart to roll back.
