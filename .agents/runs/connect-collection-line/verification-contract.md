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

## Round 8 (2026-09-19) — `/admin` model configuration, backend half (I2/I3/I4/I5)

Appended before any production-code edit by this slice (AGENTS.md §4). The page half
(I1/I6) is a sibling agent's; this contract covers the endpoints, the catalogue row and
the two read-only embedding rows it depends on.

### RED artifacts

1. `apps/admin-console/tests/test_canonical_v2_model_discovery_api.py` (new)
   - I2: `GET /api/canonical-v2/admin/connections/presets` → 200 with a non-empty
     preset table (no deployment/customer host in it: no `100.64.`, no `star.sustech`,
     no `18188`), the profile list read from `_LLM_PROFILES[*].local`, a non-empty
     `chat_profile`, and an `embedding_frozen` block.
   - I2/I3 gating: both new routes answer 401 without a session (they ride
     `/api/canonical-v2`, so the gate must cover them like every other admin API).
   - I3 success: sorted + de-duplicated ids, `count`, `request_url` built through the
     shared `_join` (a base URL already ending in `/v1` is honoured), `elapsed_ms`, one
     call only, 3 s timeout (shorter than the test probe's 5 s), `truncated` only when
     the 500-id cap cut the list.
   - I3 defaults: an empty body resolves the runtime-effective endpoint/credential
     exactly like `/connections/test` (managed-file rerank base URL is used), and
     nothing is persisted.
   - I3 failures (stub only, never a real socket): 401/403 → `unauthorized`,
     `URLError` → `unreachable`, timeout → `timeout`, 404 → `not_supported`,
     unparseable/empty body → `bad_response`; `request_url` and `elapsed_ms` present in
     every case, HTTP status present whenever there was one, no 500.
   - I3 secrecy: a submitted key never appears in the response, and an upstream body
     that echoes it comes back redacted inside `body_excerpt`.
   - I3 rate limit: a second immediate call is 429 `rate_limited` with `Retry-After`,
     and the second attempt never reaches the transport.
   - No console database: the models route answers with `DATABASE_URL` /
     `DATABASE_URL_TEST` / `CANONICAL_V2_DATABASE_URL` unset and
     `app.state.console_dsn = None`.
2. `apps/admin-console/tests/test_managed_config_catalogue.py` (extended)
   - `serving.chat_llm_profile` exists, is `text`/`serving`, carries no
     `connection`/`test_arg`, is editable for a file/default store, and is projected
     through `_FIELD_ENV_VARS` as `CHAT_LLM_PROFILE`.
   - an unknown profile name is **rejected on save** with a message naming the value and
     the available profiles, and nothing is written; a known name (and an alias) saves.
   - `extraction_endpoints.embedding_base_url` / `embedding_model` are in
     `PAGE_READONLY_FIELDS` with non-empty reasons, come back `editable: false`, and are
     refused on write with the reason (422 `display-only`).
3. `apps/admin-console/tests/test_managed_runtime_bootstrap.py` (extended)
   - a saved `serving.chat_llm_profile` is projected as `CHAT_LLM_PROFILE` by
     `apply_managed_runtime_config`, and an environment value stays the winner.

Captured RED (production code absent): `ModuleNotFoundError` for the new service symbols
/ `404` for both routes, `KeyError: 'serving.chat_llm_profile'` in the catalogue, and the
two embedding paths missing from `PAGE_READONLY_FIELDS`.

### GREEN evidence required

- Layer ①: the three suites above, fixture = the shipped route graph over scratch managed
  files + a fake HTTP transport (no socket, no provider, no state directory).
- Layer ②: `test_canonical_v2_admin_config_api.py`, `test_canonical_v2_admin_secrets_api.py`,
  `test_canonical_v2_connection_tests.py`, `test_admin_config_single_channel.py`,
  `test_admin_config_page_shell.py`, `test_canonical_v2_runtime_sources.py` — zero new
  failures.
- Layer ③: none possible for the routes themselves (no live service restart in this
  slice); the page half's real-browser pass is the sibling agent's evidence.

### What will NOT be claimed

- No fallback profile is silently applied when an operator saves an unknown name: the save
  fails. (The *environment* path keeps the serving line's tolerant behaviour — an env value
  the serving line would tolerate must not make every admin read fail; see §"I5 findings".)
- `GET /connections/presets` is read-only but still session-gated; it is not a public
  provider list.
- The preset base URLs are generic examples; none of them is reachable-checked here.
