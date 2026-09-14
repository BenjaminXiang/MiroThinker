# Acceptance: add-admin-upload-seeds (W3)

Source: `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §6 W3 row, plus
§4-C1/C2 and §2 principle 4.

> **W3 数据正门承接** … 管理区完成一次企业 XLSX 上传→批次跑完→域库有增量；seed CRUD+触发抓取成功；
> 同 hash 重复上传被去重 ｜ 回滚：路由摘除即回旧状（CLI 仍可用）

## Acceptance line → evidence

| # | Acceptance claim | Evidence | Status |
|---|---|---|---|
| A1 | The operator can upload an enterprise XLSX from the admin zone and a batch runs | `scratch-18292-upload-commit.json` (202, upload id + run id), `scratch-18292-upload-detail.json` (gate run `succeeded`, exit 0, 1888 ms), `scratch-18292-run-detail.json` (recorded command = the declared argv), `scratch-18292-domain-delta.txt` (`import_batch` 1, `company_enrichment_batch` 1) | Passed |
| A2 | The domain store gains data | `scratch-18292-domain-delta.txt`: `company` = **3** rows from a 3-row synthetic workbook (names: 云脉智能科技 / 海岳医疗器械 / 新材料研究院) | Passed |
| A3 | Seed CRUD works and a trigger succeeds | `scratch-18292-seed-{create,list,update,delete,after-delete}.json` (201 / 200 / 200 / 204 / 404); `scratch-18292-seed-trigger.json` (202, `admin-seed-refresh`, run id); `scratch-18292-seed-runs.json` (run visible, mode `preview`); `scratch-18292-seed-run-detail.json` | Passed (see G1 for the crawl outcome) |
| A4 | The same hash uploaded twice is de-duplicated | `scratch-18292-upload-duplicate.json`: 409 `duplicate_upload` naming the first `upload_id` and its status; `scratch-18292-uploads-after.json` shows exactly two records (one per workbook) | Passed |
| A5 | No Postgres ⇒ 503 + hidden entries, service alive | `scratch-18292-nopg-transcript.txt`: upload commit 503 `upload_requires_postgres`, seeds list/create/trigger 503 `seeds_require_postgres`, `/api/health` 200, `/upload` + `/seeds` 200 with the hidden blocks present, upload ledger still readable (200) | Passed |
| A6 | Triggers cannot bypass the W2 gate | `test_canonical_v2_uploads_runtime.py` (switch-off ⇒ recorded `skipped` with reason; gate refusal ⇒ ledger `rejected` with the gate code; the child env carries the effective quotas), `test_canonical_v2_uploads_registry.py` (injection matrix), `test_canonical_v2_seeds_api.py` (mode/limit closure, task mapping) | Passed |
| A7 | Rollback is route removal | `backend/api/upload.py` and `backend/api/seeds.py` are **unmodified** (`git diff --stat 3d9dd7c0 -- apps/admin-console/backend/api/upload.py apps/admin-console/backend/api/seeds.py` is empty); every legacy CLI stays usable | Passed |

## Definition of done

- Tasks: see `tasks.md` — all implementation and verification tasks checked; the residual items are
  named below.
- New tests green; the full `apps/admin-console` suite shows **no new failure** versus the W2 baseline
  (see `verification.md` §2 for why the W2 after-run is the correct before-run for W3).
- `openspec validate add-admin-upload-seeds --strict` passes.
- Quota: **0 web-search calls, 0 LLM calls, no external network call** — the smoke used a synthetic
  3-row workbook and a 2-row patent workbook, dry-run where the domain allows it, the enrichment
  autorun disabled, and seed mode `preview` only.
- Human docs: `docs/plans/2026-09-14-upload-seeds-log.md` written, `docs/plans/index.md` carries one
  new line, `openspec/change-ledger.md` registered.

## Residual items (explicit, not hidden)

- **G1**: the seed `preview` run ends `adapter_missing`, because the smoke seed points at a synthetic
  school with no registered adapter by design (no external crawl was performed). The trigger path,
  the gate admission, the subprocess boundary and the run record are all exercised; only the crawl
  itself is not, and deliberately so.
- **G2**: the seed CRUD integration test (`test_seed_crud_round_trip`) is skipped without
  `DATABASE_URL_TEST`; the smoke covered the same CRUD against a real scratch Postgres.
- **G3**: the retirement of the legacy SPA routes and the `issues.html`/workbench surfaces are W4.

## Explicit non-goals

- No full seed recollection, no enrichment execution, no Milvus write during acceptance.
- No W4/W6/W7 surface.
- No fix for the known Bocha/Serper worktree-root key lookup (recorded only).
- No production data: every acceptance workbook is synthetic and every database is scratch.
