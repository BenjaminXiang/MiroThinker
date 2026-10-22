# Tasks: enable-customer-site-collection-task-buttons

Status legend: `[ ]` pending, `[~]` in progress, `[x]` done with evidence.

## 1. Setup

- [x] 1.1 Create the OpenSpec change and scope it to collection buttons only.

## 2. Data / packaging

- [x] 2.1 Generate `code/docs/专辑项目导出1768807339.xlsx` from `company` (200 websites), sheet
      named `sheet1`.
- [x] 2.2 Bootstrap `paper` 500 rows, `professor` 200 rows, `source_page` 200 rows,
      `professor_seed` 185 rows from the serving-pack lookup.
- [x] 2.3 Install `paper-search-mcp==0.1.4` into the service venv.

## 3. Task definitions

- [x] 3.1 Add `--limit` to the six non-news collection tasks.
- [x] 3.2 Run the jobs test suite in the worktree.
- [x] 3.3 Deploy `jobs.py` and restart `miro-fullstack-v2`.

## 4. Verification

- [x] 4.1 `company-official-product-capture --limit 1 --dry-run` exits 0.
- [x] 4.2 `paper-search-backfill --limit 1 --dry-run` processes one paper.
- [x] 4.3 `paper-summary-zh-backfill --limit 1 --dry-run` writes one summary.
- [x] 4.4 `paper-doi-verify --limit 1 --dry-run` selects one unverified DOI paper.
- [x] 4.5 `professor-homepage-rescrape --limit 1` extracts one bio.
- [x] 4.6 `professor-homepage-paper-ingest --dry-run --limit 1` links one professor.
- [x] 4.7 `/jobs` returns the bounded argv for all six tasks; ops remain disabled.
- [x] 4.8 `/api/health`, `/main`, `/chat` remain 200.

## 5. Docs

- [x] 5.1 Update the ops manual task matrix and human log.
- [x] 5.2 Update user manual wording if needed.
