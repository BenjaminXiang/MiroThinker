# Verification contract: add-admin-upload-seeds (W3)

Created before any production-code edit (2026-09-14), per AGENTS.md §4 TDD boundary and
`openspec/config.yaml`.

## Deliverable under test

The W3 data front door on the Canonical V2 admin shell: a re-mounted XLSX upload chain (domain white
list, hash dedup, advisory lock, dry-run, committed import dispatched through the shared gate,
serving-side upload ledger, batch/task tracking) and a professor-seed surface (CRUD + gated
`full/sample/preview` trigger + run polling), both degrade to 503 with hidden page entries when
Postgres is unreachable.

## Acceptance line (from `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §6, W3 row)

> 管理区完成一次企业 XLSX 上传→批次跑完→域库有增量；seed CRUD+触发抓取成功；同 hash 重复上传被去重

## First technical verification point (resolved before implementation)

Legacy subprocess chain inside the V2 shell — **runs** (probe cases A–F, `current-state.md` §2), with
one defect found: a timed-out `uv run` child leaves an orphan grandchild (§2.1). No degradation path
is invoked; the orphan leak is fixed as R5.

## RED artifacts (written with/after the implementation; must fail on the pre-change code)

The whole surface is new, so every artifact fails on the pre-change code by collection error /
404 (`ModuleNotFoundError` for the new modules, `404 canonical_v2_route_not_found` for the new paths,
`JobTaskUnknownError` for the new task ids).

| # | Artifact | Locks |
|---|---|---|
| R1 | `apps/admin-console/tests/test_canonical_v2_uploads_registry.py` | White list closure for W3: the declared upload/seed tasks exist with fixed argv whose script path exists; closed parameters refuse out-of-set values; token parameters refuse malformed tokens (separator, whitespace, `..`, shell metacharacter, over-length) and unknown tokens; a bare-path string is refused; an upload token resolves to a path inside the staging root. |
| R2 | `apps/admin-console/tests/test_canonical_v2_uploads_store.py` | Serving-side ledger: admit/list/newest-first/domain filter/detail; duplicate lookup by `(domain, sha256)`; terminal status and bounded summary; no file content, no environment, credential-shaped summary text redacted; schema opens idempotently. |
| R3 | `apps/admin-console/tests/test_canonical_v2_uploads_runtime.py` | Admission: domain white list (refuses `paper`), `.xlsx`-only, empty payload, size cap; sha256 identity; the `(domain, hash)` flock excludes a second holder; duplicate ⇒ 409 carrying the original id; failed upload does not poison the hash; dry-run writes nothing (no import rows, no enrichment scheduling, no quota env). |
| R4 | `apps/admin-console/tests/test_canonical_v2_uploads_api.py` | HTTP surface: 202 admit with upload id + run id; 409 duplicate; 422 bad domain / injected token; 413 oversized; 503 when Postgres is unavailable; ledger list and detail; page routes `/upload`, `/seeds` serve and carry the shared nav; every pre-existing page carries links to the new pages. |
| R5 | `apps/admin-console/tests/test_canonical_v2_jobs_runner.py` (extended) | Process-group kill on timeout: after a timed-out run, the spawned child's process group has no surviving member (the pre-change code leaves an orphan — demonstrated in the probe). |
| R6 | `apps/admin-console/tests/test_canonical_v2_seeds_api.py` | Seed surface: list/read/create/update/delete against the scratch Postgres; unique URL ⇒ 409; trigger admits only `preview/sample/full`, `sample` without `limit` refused, mode/limit reach the gate as declared parameters, unknown seed ⇒ 404; run history readable; all endpoints 503 without Postgres. |
| R7 | `apps/admin-console/tests/test_canonical_v2_data_frontdoor_pages.py` | Page parity: `/upload` and `/seeds` return 200, carry the six-link navigation, and hide the Postgres-dependent controls when the probe reports unavailable. |

## GREEN evidence required

1. **New tests** (R1–R7) pass, each cluster named with what it locks and where its fixture comes from.
2. **Pre-existing suites**: full `apps/admin-console` pytest before and after, failure sets diffed with
   `comm` (`failures-before.txt` / `failures-after.txt` / `failures-new.txt`); no new failure.
3. **Real interaction** on scratch port **18292** (never 18188), scratch Postgres on a scratch port,
   scratch storage + config, with a synthetic 2–3 row workbook:
   upload → batch status → duplicate rejected → seed CRUD → preview trigger → run record visible,
   then a no-Postgres phase for the 503 + hidden-entry degradation, then the service stopped and
   18292 confirmed unbound.
4. **Layered report** in `verification.md` (new tests / pre-existing suites / real-interaction), no
   aggregate "all green".
5. **Quota honesty**: the number of web-search and LLM calls actually spent, with the mechanism that
   prevented spending (dry-run, synthetic workbook, `COMPANY_UPLOAD_ENRICHMENT_DISABLE_AUTORUN=1`,
   `preview`-only seed mode).

## Explicit non-goals for verification

- No retrieval/answer/replay assertion: no RAG behaviour is touched.
- No full seed recollection, no enrichment execution, no Milvus write.
- No OS cron installation (W6).
- No W4/W6/W7 surface.
- No production data and no production service: the acceptance database is a throwaway container and
  the 18188 service is neither restarted nor addressed.

## Failure policy

Stop and report instead of working around if: a pre-existing live database or the 18188 service would
be touched; the white list cannot be kept closed (some caller text reaches argv); the shared gate
cannot be reused without changing W2 semantics; or the full suite gains a new failure attributable to
this change.
