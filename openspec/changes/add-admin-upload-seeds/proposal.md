# Proposal: add-admin-upload-seeds

## Why

The authoritative product plan
(`docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §4 承接原则 + §4-C1/C2,
§6 W3) scopes the **data front door** as the W3 slice of the wrap-up: an operator must be able to get
new XLSX data in and to manage professor collection seeds from the admin zone, without a shell.

Today neither is possible on the V2 shell, although the business logic still exists:

- `backend/api/upload.py` (XLSX upload: hash dedup, advisory lock, dry-run, company enrichment batch
  scheduling, patent in-process import, professor `pipeline_v3`) and `backend/api/seeds.py`
  (`professor_seed` CRUD + trigger) are both **unmounted** — `backend/main.py` never includes them and
  the `/api/{path:path}` catch-all answers 404.
- There is no page: `/browse`, `/logs`, `/admin`, `/jobs` exist, but no upload or seed surface.
- Both chains are Postgres-backed, and the serving host has no domain Postgres. The plan's §2
  principle 4 therefore applies literally: the PG-dependent surface must be probe-gated, degrade to
  503 with hidden page entries, and must never take the service down.

Verified read-only and by live probe before this change
(`.agents/runs/add-admin-upload-seeds/current-state.md`):

- The §4-C1 risk ("旧链 subprocess 调 `uv run scripts/...`，需验证 V2 壳进程环境") is **resolved
  positively**: inside a shell launched the way the V2 shell is launched, `uv run python <script>`
  and `sys.executable <script>` both run the legacy scripts with correct cwd, env pass-through and
  timeout behaviour (probe cases A–F). No degradation path is needed.
- The same probe found a real defect in the W2 spawn helper: `subprocess.run(timeout=…)` kills only
  `uv`, leaving the real python grandchild running while the gate records `failed` and releases the
  lock. W3's jobs run through exactly that path, so the kill must reach the process group.
- W2's gate (`src/data_agents/canonical_v2/jobs.py`) is the single funnel every trigger must pass.
  W3 must not build a second one; it must declare its tasks in the same table.

## What Changes

Behavior-affecting: a new public admin API surface
(`/api/canonical-v2/admin/uploads*`, `/api/canonical-v2/admin/seeds*`), two new operator pages
(`/upload`, `/seeds`), a new serving-side SQLite upload ledger, two thin CLI entry points for the
gate to spawn, and one deliberate extension of the shared gate (server-resolved opaque token
parameters + process-group kill on timeout). No retrieval, fusion, rerank, answer, serving-pack or
collection-script behaviour is touched; no new framework and no new front-end stack is introduced.

**In scope**

1. **XLSX upload, re-mounted under a V2 route** — domain white list `company/patent/professor`,
   `.xlsx` only with a size cap, sha256 content hash, duplicate rejection (409 + the original upload
   id), a cross-process advisory lock per (domain, hash) reusing W2's `JobLock`, a dry-run mode that
   parses and reports without writing, and staging under the existing admin upload root.
2. **One gate for every upload and seed trigger** — the upload import and the professor-seed refresh
   are declared in W2's `JOB_TASKS` and started through `JobRuntime.trigger()`, so re-entrancy,
   switch, quota, breaker and PG probe apply unchanged and cannot be bypassed.
3. **Upload ledger on the serving side** — one SQLite database (`CANONICAL_V2_UPLOADS_DB`, default
   sibling of the jobs database) recording upload id, domain, filename, sha256, size, staged path,
   status, gate run id, operator, timestamps and the bounded result summary, so the page can track a
   batch even when the build-time Postgres is not reachable.
4. **Professor seed management** — `professor_seed` CRUD reusing the existing storage helpers, a
   `full/sample/preview` trigger that goes through the gate, and run polling backed by the gate's run
   history.
5. **Two pages** — `/upload` (drop file, pick domain, dry-run or commit, per-upload status and
   company-batch progress) and `/seeds` (seed table, create/edit/delete, trigger, run history), both
   carrying the same top navigation as `/browse`, `/logs`, `/admin`, `/jobs`.
6. **Graceful degradation without Postgres** — every PG-dependent endpoint answers 503 with a stable
   code and the page hides the corresponding entry; the service keeps serving.

**Out of scope** (owned elsewhere, listed so the boundary is explicit)

- W4 (quality/workbench surfaces, `issues.html`, the remaining task-ops actions, SPA retirement).
- W6 (cron declaration/installation, the periodic runs themselves, automatic cadence).
- W7 (release pipeline).
- Repairing the known Bocha/Serper worktree-root key-lookup defect — recorded, not fixed.
- Rewriting or re-testing the legacy chain's business logic: W3 re-mounts it behind a V2 route with a
  domain white list and a gate; it does not reimplement import, enrichment or crawling.

## Impact

| Area | Change |
|---|---|
| New capability | `admin-data-frontdoor` (spec delta below) |
| New code | `apps/miroflow-agent/src/data_agents/canonical_v2/uploads.py`, `apps/admin-console/backend/api/canonical_v2_uploads.py`, `apps/admin-console/backend/api/canonical_v2_seeds.py`, `apps/admin-console/backend/static/upload.html`, `apps/admin-console/backend/static/seeds.html`, `apps/admin-console/scripts/run_admin_upload_import.py`, `apps/miroflow-agent/scripts/run_admin_seed_refresh.py` |
| Touched | `apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py` (token-parameter declaration + process-group kill only), `apps/admin-console/backend/main.py` (routers + pages), the nav block of `browse.html`/`logs.html`/`admin.html`/`jobs.html` |
| Unchanged | every collection/import script's behaviour, `managed_config.py` schema, W1/W2/W5 surfaces, `pipeline_run` usage on the serving host |
| Rollback | drop the router/page lines; the SQLite ledger is inert (no migration, no external contract) |
