# Acceptance: enable-customer-site-collection-task-buttons

| # | Criterion | Evidence |
|---|---|---|
| A1 | Company-product input exists and is readable | `code/docs/专辑项目导出1768807339.xlsx`, 200 rows, sheet `sheet1` |
| A2 | Raw collection DB has paper/professor work | `paper` 500, `professor` 200, `source_page` 200, `professor_seed` 185 |
| A3 | `paper-search-mcp` import works | `pip show paper-search-mcp` 0.1.4; dry-run `papers_processed=1` |
| A4 | Six non-news collection tasks have bounds | task argv includes `--limit` 50/20/50/100/20/10 |
| A5 | Company-product dry-run succeeds | `--limit 1 --dry-run` exit 0; `companies_considered=1` |
| A6 | Paper-search dry-run succeeds | `papers_total=1`, `papers_processed=1`, `persist_errors=0` |
| A7 | Paper-summary dry-run succeeds | `papers_processed=1`, `summaries_written=1` |
| A8 | Paper-DOI dry-run succeeds | `papers_total=1`, `papers_processed=1` |
| A9 | Professor-rescrape extracts a bio | `examined=1`, `fetched OK=1`, `bio extracted=1` |
| A10 | Professor-paper dry-run succeeds | `profs_processed=1`, `papers_linked_total=4` |
| A11 | Serving unaffected | `/api/health`, `/main`, `/chat` 200 after restart; candidate DB/pack untouched |
| A12 | Build-only tasks remain disabled | `task_views`: 7 collection `available=true`; 3 ops `postgres_unavailable`; import/seed links only |
| A13 | Page-path run succeeds | manual gate run `6f046e6d-04c9-433e-81af-952c0ad6f320` `professor-homepage-rescrape`: `succeeded`, exit 0, 19 fetched, 8 bios stored |
| A14 | Company-product real run succeeds | run `22692758…`: `succeeded`, 50 considered, 40 products inserted, 28 rows; `aliases` jsonb patch applied |
| A15 | Professor-paper real run succeeds | run `16cbf070…`: `succeeded`, 10/10 professors, 55 papers linked |
| A16 | Paper-DOI real run succeeds | run `fae18beb…`: `succeeded`, exit 0, 100 candidates, 92 pipeline issues |
| A17 | Paper-summary real run succeeds | run `c45782b4…`: `succeeded`, 50/50 papers, 50 summaries written |
| A18 | Paper-search real run succeeds | run `0659393a…`: `succeeded`, 20/20 papers, 19 abstracts found |

## Rollback

- Restore `jobs.py.bak-limit-*`, remove the generated XLSX, delete rows marked
  `canonical_source='manual'` / pilot professor ids, uninstall `paper-search-mcp` if desired,
  restart.
- The serving candidate DB, serving pack and index are not touched.
