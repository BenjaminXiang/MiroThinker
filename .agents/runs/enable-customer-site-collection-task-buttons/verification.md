# Verification: enable-customer-site-collection-task-buttons

Date: 2026-10-22 (Asia/Shanghai)
Customer host: `100.64.0.96` / `/root/deploy/fullstack-v2`

## 1. Data bootstrap

`miroflow_collection_v1` after bootstrap:

| Table | Rows |
|---|---|
| `paper` | 500 |
| `professor` | 200 |
| `source_page` | 200 |
| `professor_seed` | 185 |
| `company` | 7,089 |
| `company_news_item` | 73 |

Paper mix: 200 `needs_enrichment` (missing abstract), 200 `ready` with `summary_zh=NULL`,
100 `identity_status='unverified'` for DOI verification. Existing rows were preserved with
`ON CONFLICT DO NOTHING`.

Company-product input: `code/docs/专辑项目导出1768807339.xlsx`, 200 companies with websites,
sheet `sheet1`.

## 2. Packaging

`paper-search-mcp==0.1.4` installed into `/root/deploy/fullstack-v2/.venv`; pulled `pypdf`,
`feedparser`, `feedparser-sgmllib`. `import paper_search_mcp` succeeds.

## 3. Task argv

After the `jobs.py` patch, the six non-news collection tasks resolve to:

```text
company-official-product-capture  ... --limit 50
paper-search-backfill             ... --limit 20
paper-summary-zh-backfill         ... --limit 50
paper-doi-verify                  ... --limit 100
professor-homepage-rescrape       ... --apply --confirm-real-db --limit 20
professor-homepage-paper-ingest   ... --resume --limit 10
```

`uv run python` is replaced by `/root/deploy/fullstack-v2/.venv/bin/python` at trigger time.
Jobs test suite: 101 passed (worktree `canonical-v2-s11-consolidation`).

## 4. Script checks

| Check | Result |
|---|---|
| company-product `--limit 1 --dry-run` | exit 0; `companies_considered=1` |
| company-product real `--limit 50` | run `22692758…`; succeeded, exit 0; 50 considered, 111 pages, 40 products extracted/inserted, 28 `company_product` rows |
| paper-search `--limit 1 --dry-run` | exit 0; `papers_processed=1`, `abstracts_found=1`, `summaries_written=1`, `persist_errors=0` |
| paper-summary `--limit 1 --dry-run` | exit 0; `papers_processed=1`, `summaries_written=1`; DeepSeek 200 |
| paper-doi `--limit 1 --dry-run` | exit 0; `papers_total=1`, `papers_processed=1`, `papers_unverified=1` |
| professor-rescrape `--limit 5 --apply --confirm-real-db` | exit 0; `examined=5`, `fetched OK=5`, `bio extracted=1`, `bios stored=1` |
| professor-paper `--dry-run --limit 1` | exit 0; `profs_processed=1`, `papers_linked_total=4` |
| professor-paper real `--limit 10` | run `16cbf070…`; succeeded, 10/10 professors, 55 papers linked |
| paper-doi real `--limit 100` | run `fae18beb…`; succeeded, exit 0; 100 candidates, 92 pipeline issues |
| paper-summary real `--limit 50` | run `c45782b4…`; succeeded, 50/50 papers, 50 summaries written |
| paper-search real `--limit 20` | run `0659393a…`; succeeded, 20/20 papers, 19 abstracts found |

Known small bug: `run_paper_search_backfill.py --help` raises an argparse `%` formatting error;
the actual task command (no `--help`) is unaffected.

`company-official-product-capture` first real run exposed a schema mismatch: `company.aliases`
is `jsonb`, while the script used `%s = ANY(aliases)`, producing
`WrongObjectType: op ANY/ALL (array) requires array on right side` when a record needed alias
resolution. Patched to `aliases @> to_jsonb(%s::text)`; backup
`run_company_official_product_capture.py.bak-aliases-*`.

## 5. Service

`systemctl restart miro-fullstack-v2` executed at 17:00:57 after the `jobs.py` sync; boot completed
in 11m33s. New PID `3269640`; `systemctl is-active = active`; `/api/health`,
`https://gxzx-coze-api.idea.edu.cn/main`, `/chat` all 200. `jobs.py` mtime 17:00:51 is before the
process start 17:00:56, so the service loaded the bounded argv.

`task_views()` after restart: 7 collection tasks `available=true`; 3 ops
`postgres_unavailable`; import/seed `available=true` but token-led (page links, no run button).

Page-path run (manual trigger through the same `JobRuntime.trigger` gate as the button):
`professor-homepage-rescrape` run `6f046e6d-04c9-433e-81af-952c0ad6f320` — `succeeded`,
exit 0, 20 candidates, 19 fetched, 8 bios stored; `professor.profile_raw_text` 9 rows.

## 6. Out of scope / still unavailable

- `ops-milvus-backfill`, `ops-milvus-backfill-dry-run`, `ops-retrieval-validation`:
  `postgres_unavailable` (no build-time PG DSN).
- 3 upload imports: page links; upload page has no writable build PG.
- 2 seed refreshes: page links; seed page has no `DATABASE_URL`.

These require a build-capable node or a separate build DB; no attempt was made to point the
serving node at a production build DB.
