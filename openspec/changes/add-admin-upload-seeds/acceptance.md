# Acceptance: add-admin-upload-seeds (W3)

Source: `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §6 W3 row, plus
§4-C1/C2 and §2 principle 4.

> **W3 数据正门承接** … 管理区完成一次企业 XLSX 上传→批次跑完→域库有增量；seed CRUD+触发抓取成功；
> 同 hash 重复上传被去重 ｜ 回滚：路由摘除即回旧状（CLI 仍可用）

## Acceptance line → evidence

| # | Acceptance claim | Evidence required | Status |
|---|---|---|---|
| A1 | The operator can upload an enterprise XLSX from the admin zone and a batch runs | smoke 18292: `POST /api/canonical-v2/admin/uploads/company` → gate run → `succeeded`, with `import_batch`/`company_enrichment_batch` rows created in the scratch Postgres and `batch` progress readable from the upload detail | pending |
| A2 | The domain store gains data | smoke 18292: the scratch Postgres `company` row count increases by the number of companies in the 2–3 row test workbook, read back with SQL after the import run | pending |
| A3 | Seed CRUD works and a trigger succeeds | smoke 18292: create → read → update → list → trigger `preview` → run visible in the seed's run history → delete | pending |
| A4 | The same hash uploaded twice is de-duplicated | smoke 18292: second `POST` of identical bytes answers 409 `duplicate_upload` naming the first `upload_id`, and the import batch count is unchanged | pending |
| A5 | No Postgres ⇒ 503 + hidden entries, service alive | smoke 18292 no-PG phase: upload commit and every seed endpoint answer 503 with the documented code, both pages render with the dependent controls hidden, `/api/health` stays 200 | pending |
| A6 | Triggers cannot bypass the W2 gate | R4/R6 tests: switch-off, quota-zero and breaker-open refusals apply to W3 tasks exactly as to W2 tasks; the injection matrix is refused at parameter validation | pending |
| A7 | Rollback is route removal | the legacy modules are unmodified and still importable; no CLI script was replaced | pending |

## Definition of done

- All tasks in `tasks.md` checked, or an explicit gap recorded in `.agents/runs/add-admin-upload-seeds/verification.md`.
- New tests green; full `apps/admin-console` suite has **no new failure** versus the pre-change baseline.
- `openspec validate add-admin-upload-seeds --strict` passes.
- Quota spent during acceptance is reported honestly (target: 0 web-search calls, 0 LLM calls; the
  smoke uses a 2–3 row synthetic workbook, dry-run where possible, and seed mode `preview` only).
- `docs/plans/2026-09-14-upload-seeds-log.md` written and `docs/plans/index.md` carries one new line.

## Explicit non-goals

- No full seed recollection, no enrichment run, no Milvus write during acceptance.
- No W4/W6/W7 surface.
- No fix for the known Bocha/Serper worktree-root key lookup (recorded only).
- No production data: every acceptance workbook is synthetic and every database is scratch.
