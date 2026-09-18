# Verification contract: connect-collection-line

Written before production-code edits (AGENTS.md §4 TDD boundary).

## RED artifacts (must fail before the change)

1. `apps/admin-console/tests/test_console_dsn_single_source.py`
   - only `CANONICAL_V2_DATABASE_URL` set → the console reports its database
     **unavailable** and a gated endpoint answers 503 `console_database_not_configured`
     (today: the probe accepts that name and the read then 500s).
   - `DATABASE_URL` wins over `DATABASE_URL_TEST`; blank values count as unset.
2. `apps/admin-console/tests/test_canonical_v2_jobs_runner.py` (extended)
   - the spawned child env carries the resolved `DATABASE_URL`; when unresolved the
     key is absent; the existing "env is never persisted" test stays green.
3. `apps/admin-console/tests/test_canonical_v2_seeds_api.py` (extended)
   - `GET /seeds/{id}/runs` payload carries `status`, `exit_code`,
     `stderr_excerpt` for a completed run.
4. `apps/admin-console/tests/test_admin_core_pages.py` (extended)
   - `nav_auth.js` hides `[data-requires-postgres]` nav entries when the console
     database is unconfigured; `main.html` marks `/seeds` and `/upload`.
5. `apps/miroflow-agent/tests/data_agents/professor/` (extended)
   - the pkusz matcher resolves `https://www.pkusz.edu.cn/szdw.htm` to a registered
     adapter and the two corrected SZTU URLs resolve to `sztu-teacher-family`.
6. `apps/admin-console/tests/test_import_professor_seeds.py` (new)
   - the importer parses the historical corpus, skips existing `seed_url`s, reports
     created/skipped/unresolved, and never writes without `--apply`.

## GREEN evidence required per line

- Layer ①: the tests above, fixture-driven (temporary schema / stub runners), no live
  state directory touched.
- Layer ②: full `apps/admin-console` suite before/after with a byte-identical failure
  set (the suite carries 25 pre-existing failures + 105 errors on this checkout).
- Layer ③: on the live line — `/seeds` 200 empty list; a real
  create → update → delete cycle; the first real `preview` run (its `pipeline_run`
  row in `miroflow_collection_v1`); then a `sample limit=5` run; quota actually spent
  reported; `/chat` 200 and gate codes unchanged.

## What will NOT be claimed

- The crawl's LLM enrichment stays disabled; profiles from `preview` contain no
  rows (discovery-only by design) and `sample` may still report `adapter_missing`
  for URLs outside the registry.
- No claim about collected data reaching `/chat`; that requires the C6 rebuild and is
  explicitly out of scope.

## Round 6 (2026-09-19) — `/jobs` operator clarity

Appended before the page rewrite; same TDD boundary (AGENTS.md §4).

### RED artifacts

1. `apps/admin-console/tests/test_canonical_v2_jobs_registry.py`
   - `test_every_task_carries_operator_copy_for_the_page` — every declared task has a
     `group` in the four allowed values, a non-empty `operator_hint` that does not leak a
     script path, and the ids per group are exactly the listed sets.
   - `test_task_payload_exports_the_operator_columns` — `as_dict()` carries both keys.
   - Captured RED with `jobs.py` at HEAD: `AttributeError: 'JobTask' object has no
     attribute 'group'` / `KeyError: 'group'` → `2 failed, 45 deselected`.
2. `apps/admin-console/tests/test_canonical_v2_jobs_api.py`
   - the list payload carries `group` / `operator_hint` / `token_params` for a real task;
   - `/jobs` serves the explainer, the four group titles, `技术细节`, `立即运行`,
     `复位熔断` and the `去 Seed 管理页` link.
3. Page rendering has no browser in this slice: the page's own inline script is executed
   against a real `task_views()` payload in a DOM stub
   (`.agents/runs/connect-collection-line/jobs-page-harness/render_check.cjs`). It is the
   GREEN evidence for "renders everything from the payload", not a unit test, and it does
   not run in CI.

### GREEN evidence required

- Layer ①: the two new registry tests plus the extended API test, fixture = the real
  white list and a real payload.
- Layer ②: the jobs / uploads / seeds / shell / gating suites listed in `verification.md`;
  zero new failures (one pre-existing chat-branding failure, re-confirmed at HEAD).
- Layer ③: the render harness asserting groups, hints, badges, tags, disabled reasons,
  token-task links, the history row shape and the unchanged trigger POST body.

### What will NOT be claimed

- No real-browser pass (no scratch console was started: the slice forbids service
  restarts / touching 18188). Round 4/5's browser measurements are not repeated here.
- The inline failure reason in 运行历史 shows `exit_code`; the stderr excerpt only appears
  if the list payload carries it, which today it does not
  (`JobRun.as_dict(include_samples=False)`). One backend line would close that, and the
  slice's constraints exclude backend Python.
