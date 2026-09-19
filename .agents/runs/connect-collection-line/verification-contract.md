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

## Round 10 (2026-09-19) — `/admin` page batch: dedupe the rerank probe + 「全部测试」

Appended before any production-code edit by this slice (AGENTS.md §4). Page half only
(`admin.html` / `admin.js` / `admin.css`, the two marker suites and the render harness);
no backend Python, no service restart, 18188 untouched.

### RED artifacts

1. `apps/admin-console/tests/test_admin_model_roles_page.py` (extended — markers over the
   shipped assets plus the real `CONNECTIONS` table):
   - the aggregate probe table covers exactly the connections the server can test: six
     probes (llm ×2, embedding, rerank, bocha, serper), in this order, labels included —
     a connection can neither be dropped nor probed twice by accident;
   - the run is sequential (`Promise.all` absent), spaced by a constant ≥ the server's
     `min_interval_seconds`, and prints `测试中 n/6…`;
   - the button is re-enabled in `finally` (never stuck after an error);
   - a role without an endpoint is skipped locally (「未配置端点，已跳过」) *before* any
     request is built;
   - the aggregate line and the single-role button share one response→wording mapping;
   - card 2 carries no rerank probe and points at the role block, while the 重排模型 block
     keeps its own 测试 (the connectivity coverage is moved, not deleted).
2. `apps/admin-console/tests/test_admin_config_page_shell.py` (updated):
   - `id="testRerank"` is gone, replaced by the pointer assertion;
   - the aggregate control is script-built (`>全部测试<` must not be in the shell, like
     every other probe control).

Captured RED: `5 failed, 79 passed` (the five new/extended markers; the aggregate symbols
do not exist at HEAD) — full command and output in `verification.md` §Round 10.

### GREEN evidence required

- Layer ①: the two suites above (markers) — fixture = the shipped static files and the real
  backend connection table, no network.
- Layer ②: `test_admin_config_page_shell.py`, `test_admin_config_single_channel.py`,
  `test_canonical_v2_admin_secrets_api.py`, `test_nav_postgres_gating.py`,
  `test_admin_model_roles_page.py` — zero new failures.
- Layer ③: the render harness `model-roles-harness/render_check.cjs` runs admin.js in the DOM
  stub against the real fixtures: the aggregate run issues six sequential requests with
  measured spacing ≥ 1000 ms, renders one line per role, reports 429 and skipped roles, and
  leaves the button usable. (The harness is not CI; it is the behaviour evidence.)

### Pre-existing defect found while preparing this slice

`degradedPresetScenario` in the harness still asserts "an empty endpoint field ⇒ no
outbound call", which round 9 deliberately changed (`roleBaseUrl` falls back to the
runtime-effective endpoint shown on the card). The scenario is red at HEAD
(`5 !== 4`); it is corrected here to the shipped contract, and a *true* no-endpoint case
(field empty **and** runtime endpoint empty) is added for the skip line.

### What will NOT be claimed

- No real-browser pass (no scratch console started: the slice forbids restarts) and no live
  check on 18188 — the page ships with the next hot update.
- 对话模型 and 采集模型 share the `llm` connection: six probes consume the client's whole
  6/min budget, so a run started right after a model-list fetch renders 限频 lines for its
  tail. That is reported to the operator, not hidden.

## 后续批次 (2026-09-19) — nmne SZTU legacy roster adapter

Appended before production-code edits; same TDD boundary (AGENTS.md §4).

### Contract

- `https://nmne.sztu.edu.cn/picturers.jsp?urltype=tree.TreeTempUrl&wbtreeid=1004` is the
  college's 师资队伍 list (8 teacher cards per page, 8 pages) — one live GET, saved verbatim
  (line endings normalised) as
  `apps/miroflow-agent/tests/data_agents/professor/fixtures/sztu/nmne_picturers_1004.html`.
- `resolve_seed_adapter_name()` returns the new adapter name for that seed, and the matcher
  accepts only the verified host + `/picturers.jsp` + the verified `wbtreeid` set
  (1004 / 1033 / 1034 / 1035 / 1036 / 1351 / 1352).
- The extractor reads the roster from the CMS card template (`a.jbox` + `div.ptitle`) and
  reuses `_build_discovered_professor_seeds` — no second parser.

### RED artifacts

`apps/miroflow-agent/tests/data_agents/professor/test_sztu_nmne_picturers_adapter.py`
- matcher accepts the corpus URL and its pagination URL (`?a237185t=8&a237185p=2&…&wbtreeid=1004`),
  rejects `ai.sztu.edu.cn/szdw/jytd/jxjs.htm`, `nmne.sztu.edu.cn/xygk.htm`, the same page
  with an unverified `wbtreeid`, and the bare path with no `wbtreeid`;
- extractor returns the fixture's 8 teacher entries (name + absolute profile URL) and
  produces nothing on a non-roster SZTU page;
- `resolve_seed_adapter_name()` resolves the corpus seed URL.
- Superseded assertion to flip: `test_pkusz_adapters.py::test_legacy_sztu_picturers_url_stays_unresolved`
  — it locked design §6's "fix the data" decision, which the live page falsified.
- Superseded expectations to update: `apps/admin-console/tests/test_import_professor_seeds.py`
  (the nmne URL is no longer `skipped_unresolved`).

### GREEN evidence required

- Layer ①: the new suite + the flipped pkusz assertion + the admin-console importer suite.
- Layer ②: `cd apps/miroflow-agent && uv run pytest -q -p no:randomly -p no:cacheprovider
  tests/data_agents/professor -k "adapter or roster or pkusz or sztu"` — all green.
- Layer ③: `apps/admin-console/scripts/import_professor_seeds.py --dsn …` (dry-run, no
  `--apply`) over the real corpus → 39 distinct urls, 0 unresolved.

### What will NOT be claimed

- No live crawl of the college. The seed page yields its 8 entries, but the crawl stops
  there: `extract_roster_page_links` finds no pagination link and
  `_should_continue_after_roster_entries` has no `/picturers.jsp` case, so the other 7 pages
  of the same list are not reached. Recorded as a follow-up, not fixed here.
- Only page 1 of the corpus URL is kept as a fixture; the sibling column pages
  (1004/1033/1034/1035/1036/1351/1352) were fetched once each to pick the matcher set and
  are not fixtures.

## 后续批次 — SPA 构建 + 文案去重 (2026-09-19)

Appended before this batch's page/frontend edits (AGENTS.md §4). Two independent
follow-ups: the React SPA must still type check and build after `interrupted` landed, and
`/admin` card 2 must stop holding a second copy of the rerank runtime facts.

### 1. SPA (`apps/admin-console/frontend/`)

Contract: `SeedLastRunStatus` gained `interrupted` (`frontend/src/api.ts:772`) and its
label map (`Seeds.tsx:44`), but the two other `Record<SeedLastRunStatus, …>` tables were
missed. Fix = add the missing key to both tables; the union and the label map stay exactly
as the earlier batch wrote them; nothing else in the SPA changes.

RED artifact: `npx tsc -b` at HEAD → `TS2741` ×2 — `Seeds.tsx(57,7)` (`STATUS_TAG_COLOR`)
and `Seeds.tsx(120,11)` (the counts record).

### 2. `/admin` card 2 ↔ 重排模型 role block (page)

Contract: what rerank is *in effect* has one home — the 重排模型 role block. Card 2 keeps
the fields it owns (`serving.rerank_timeout_seconds`, `serving.rerank_max_documents`,
`serving.web_topical_floor`) and replaces its runtime row with a muted pointer; the runtime
badge, the pending-restart pill and `runtime_note` are not rendered twice.

RED artifacts (new markers):
1. `tests/test_admin_config_page_shell.py::test_card_two_carries_no_second_copy_of_the_rerank_runtime_state`
2. `tests/test_admin_model_roles_page.py::test_card_two_delegates_the_rerank_runtime_state_instead_of_copying_it`
3. `...::test_the_rerank_role_block_keeps_the_runtime_facts_card_two_gave_up`

Captured RED with only the page untouched: `3 failed, 29 passed`; after correcting the
third test's source-shape literal (the row title is written across lines in `admin.js`),
the dedupe RED is the two above (`2 failed, 30 passed`).

### GREEN evidence required

- Layer ①: the three markers above plus the page-shell marker; the SPA's own evidence is
  `tsc -b` + `vite build` + its `vitest` suite (there is no Seeds unit test to extend).
- Layer ②: the brief's four suites — `test_admin_config_page_shell.py`,
  `test_admin_model_roles_page.py`, `test_admin_config_single_channel.py`,
  `test_nav_postgres_gating.py` — zero failures.
- Layer ③: `model-roles-harness/render_check.cjs` — the shell renders with no card-2
  runtime node, the pointer is inside card 2, and the rerank role still fills its state node.

### What will NOT be claimed

- No `已中断` filter pill and no summary-stat cell in the SPA: the new status is counted and
  labelled (type-correct), but the toolbar has no pill for it — a product decision left to
  the main line.
- No real-browser pass and no live 18188 check: the static page ships with the next hot
  update.
- Human docs (`docs/plans/` round log + index) and OpenSpec `tasks.md` / `acceptance.md`
  are not touched by this batch.

## 后续批次 — `/operations/gaps` 的 500 (2026-09-19)

Appended before this batch's edits (AGENTS.md §4). Second occurrence of one defect class
(see `## RED artifacts` here and the earlier admin-status repair).

```
Reported symptom:    GET /api/canonical-v2/operations/gaps → 500
                     AttributeError: '_EphemeralKnowledgeGapFeedback' object has no
                     attribute 'list_for_admin' (live, 2026-09-19 23:34)
Expected invariant:  an endpoint that needs an administrator capability the injected
                     operations object does not implement answers its module's 503
                     ("Canonical V2 operations are unavailable"), never an unhandled
                     AttributeError; a capable object's real errors stay visible
Likely defect class: L3 (missing boundary guard) + C1 (test-matrix gap: the guard added
                     for the admin status surface was not swept across sibling call sites)
Why systemic:        the two call sites were written in the same module as the guarded
                     one; the fix landed on the surface where the first traceback pointed
Search plan:         every `list_for_admin` / `get_for_admin` call site in
                     `apps/admin-console` (the administrator-only interface on the
                     injected object)
Proposed fix level:  Level 3 — one shared guard in `backend/api/canonical_v2_operations.py`,
                     used by both endpoints, matching `canonical_v2_admin._gap_summary`
Regression test plan: ephemeral-shaped mirror → 503 on both endpoints; Postgres-shaped
                     mirror → 200/404; exploding mirror → 500 (guard must not swallow)
Out of scope:        the live line (needs a service restart), any other static page, any
                     other backend module, the human/OpenSpec docs (main line owns them)
```

### RED artifacts (must fail before the change)

1. `tests/test_canonical_v2_admin_status_repair.py::test_gaps_degrade_without_administrator_capability`
   (both endpoints) — today 500 (AttributeError escapes the endpoint).
2. `tests/test_canonical_v2_operations_api.py::test_browse_gaps_503_renders_a_neutral_state`
   — today the page renders the red `知识缺口加载失败 · HTTP 503` box.

### GREEN evidence required

- Layer ①: the two markers above plus
  `...::test_gaps_keep_pages_and_404_when_capable` and
  `...::test_gaps_keep_capable_object_errors_visible` (the guard must not hide real errors).
- Layer ②: `tests/test_canonical_v2_admin_status_repair.py` +
  `tests/test_canonical_v2_operations_api.py` — zero failures. (`test_canonical_v2_consumers_api.py`
  named in the brief does not exist on this branch.)
- Layer ③: not available offline — the fix reaches the live line only after a restart; the
  brief forbids restarting.

### What will NOT be claimed

- No live 18188 verdict: line 47 is hit only by the running process, so the 500→503 change is
  verified by `TestClient` against the same dependency wiring (`main.py:248-250` overrides
  `get_knowledge_gap_operations` with the candidate runtime's `gap_operations`).
- Human docs (`docs/plans/` round log + index) and OpenSpec `tasks.md` / `acceptance.md`
  are not touched by this batch; the main line owns the round entry.

## 后续批次 — 知识缺口台账（后端）(2026-09-20)

Appended before production-code edits (AGENTS.md §4). The demand-side half of the
knowledge-gap loop is write-only on this deployment: the feedback endpoint's
`gap_operations` is the in-process ephemeral object, so a filed `GapSignal` is lost
on restart, and the read surface (`/api/canonical-v2/operations/gaps`) needs the
build-line Postgres schemas this deployment does not have.

### Contract

- `apps/admin-console/backend/storage/chat_gaps.py` — one SQLite ledger
  (`chat-gaps.sqlite3`), resolved from the environment in this order:
  `CANONICAL_V2_CHAT_GAPS_DB` (this ledger's own override, the shape every
  sibling ledger has) → parent of `CANONICAL_V2_JOBS_DB` → parent of
  `CANONICAL_V2_ACCESS_LOG_DB` → `admin_auth.DEFAULT_STATE_DIR` (same state
  directory as every other console ledger). No Postgres, no new dependency,
  WAL + `busy_timeout` like its siblings.
- Table `chat_gap(signal_id PK, session_id, turn_id, release_id, feedback_type,
  note, query_trace_id, answer_trace_id, observed_at, recorded_at)`.
- API: `record(entry) -> bool` (True only when a row was inserted; the runtime's
  content-addressed `signal_id` makes a repeat a no-op), `list_recent(limit,
  feedback_type)`, `counts_by_type()`, `total()`.
- Write path stays after `gap_operations.record(signal)` and never changes what the
  feedback endpoint answers: a ledger failure is logged and swallowed.
- Read surface `GET /api/canonical-v2/admin/chat-gaps` (rides the already-gated
  `/api/canonical-v2` prefix), `limit` 1..200 default 50, optional `feedback_type`,
  answer `{"items": [...], "total": N, "counts": {...}}`; no Postgres involved, and
  an empty (or not-yet-created) ledger is a 200 with an empty list.

### RED artifacts (must fail before the change)

1. `apps/admin-console/tests/test_canonical_v2_chat_gaps_store.py` (new) —
   `ModuleNotFoundError`: `backend.storage.chat_gaps` does not exist at HEAD.
2. `apps/admin-console/tests/test_canonical_v2_chat_gaps_api.py` (new) —
   `404` for `GET /api/canonical-v2/admin/chat-gaps` (route does not exist), and the
   two write-path tests fail because no ledger row is ever written.
3. `apps/admin-console/tests/test_canonical_v2_consumer_migration.py` —
   `_KNOWN_API_ROUTES` gains the new route (the shell's route-set assertion).

### GREEN evidence required

- Layer ①: the two new suites, fixture = `tmp_path` SQLite only (never the serving
  state directory): store (insert → list → counts → total, idempotent second
  `record()` returns False, `feedback_type` filter, newest-first, path precedence)
  and HTTP (empty ledger with no console DSN configured, row shape, filter, limit
  bounds 0 / 201 → 422, 401 without a session, filed feedback lands in the ledger,
  broken ledger leaves the HTTP result unchanged).
- Layer ②: `test_canonical_v2_admin_status_repair.py`, `test_canonical_v2_operations_api.py`,
  `test_admin_gate.py`, `test_canonical_v2_access_log_api.py` — zero new failures.
- Layer ③: none possible — the endpoint ships with the next hot update; this slice
  does not restart services and does not touch 18188 or the live state files.

### What will NOT be claimed

- No live `/browse` panel proof: the page half is the sibling agent's; this slice
  fixes the backend shape (`total` is the whole-ledger count, `counts` the per-type
  breakdown, so `sum(counts.values()) == total` holds regardless of the filter).
- The ledger is a copy, not a replacement: `gap_operations.record()` semantics and
  the build-line Postgres path are untouched, and no `signal_id` is ever deduped
  against the build database.

## 后续批次 — 知识缺口台账（页面）(2026-09-20)

Appended before production-code edits (AGENTS.md §4). The page half of the same loop the
backend batch above opens: `/browse`'s 「V2 Gaps / 知识缺口」 tab still reads the build-line
surface (`api/canonical-v2/operations/gaps`), which this deployment can never answer, and the
served `/chat` page has no way to file the feedback that would ever put a row in the ledger —
so the tab is a dead reader and the write path has no door.

### Contract

- `/browse` (`apps/admin-console/backend/static/browse.html`): the gaps tab reads
  `api/canonical-v2/admin/chat-gaps` (no query params beyond the default limit) and nothing
  else; the operations path, `gapsUnavailableText` and the gap-detail view are deleted. Per
  item: feedback type in Chinese (`incorrect_answer`→「回答不对」, `evidence_gap`→「证据不足」,
  anything else verbatim), the note when present, local time `YYYY-MM-DD HH:mm`
  (`recorded_at`, falling back to `observed_at`) and short session/turn markers (≤8 chars of
  the id's last `:`-separated segment — never a full uuid). Above the list: 「共 N 条反馈」 plus
  the per-type breakdown from `counts`. Empty ledger: 「还没有用户反馈。用户在对话页点「反馈」后，
  会记录到这里。」 The header summary tile labelled 知识缺口 reads the ledger's `total`, `—`
  until it answers.
- `/chat` (`apps/admin-console/backend/static/chat.html`): after an answer, one inline
  「反馈」 control opens a one-line optional note + 提交 / 取消 and POSTs
  `api/canonical-v2/chat/feedback` with `query` (the turn's query), `query_type`
  (`data.query_type`, `"unknown"` when the payload carries none), `answer_text` (the rendered,
  sanitized answer), `feedback_type: "incorrect_answer"` and `note` (trimmed, `null` when
  empty, ≤1000 chars). States idle → open → sending (提交 disabled) → 已反馈 (button greyed,
  no second POST). Failures go through the page's `renderError`; a 409 reads
  「本次会话已过期，无法反馈」, never the machine code.

### RED artifacts (must fail before the change)

1. `.agents/runs/connect-collection-line/gaps-ledger-harness/render_check.cjs` (new) — runs
   `/browse`'s own inline script in a DOM stub with a stubbed ledger payload; at HEAD it fails
   because the page fetches the operations path and renders build-surface cards.
2. `apps/admin-console/tests/test_canonical_v2_real_preview_ui.py` (extended) —
   `test_browse_gaps_tab_reads_the_feedback_ledger` runs the same harness assertions inline;
   RED at HEAD (no `chat-gaps` literal in the page).
3. `apps/admin-console/tests/test_canonical_v2_operations_api.py` — the page assertions in
   `test_canonical_v2_operations_api_is_bounded_read_only_and_quarantined` name the operations
   path; RED after the page moves (the assertion is updated to name the ledger instead), and
   `test_browse_gaps_503_renders_a_neutral_state` is deleted with the code it locks.
4. `apps/admin-console/tests/chat_ui_behavior_test.mjs` (extended) — feedback control markers,
   POST body, sent state, 409 copy; RED at HEAD (no control exists).

### GREEN evidence required

- Layer ①: the four artifacts above.
- Layer ②: `tests/test_canonical_v2_real_preview_ui.py -k browse` (11 pre-existing, all pass),
  `tests/test_canonical_v2_operations_api.py`, `node --test tests/chat_ui_behavior_test.mjs`
  (86/87 at HEAD: the `科创` vs `国先` brand assertion is a pre-existing failure and must not
  change).
- Layer ③: none possible — this slice ships with the next hot update; no restart, no 18188.

### What will NOT be claimed

- No live-page proof: the ledger endpoint is the sibling batch's and is not deployed; the
  page is verified against the contract payload in a DOM stub.
- The `/chat` note is not an evidence path: `answer_text` / `query` travel for shape only —
  the endpoint's own record call uses the session, the type and the note.
- `tests/test_canonical_v2_consumer_migration.py::_assert_static_and_import_quarantine` still
  names the operations path for `/browse`; that assertion is already unreachable (its caller
  fails at `:734` at HEAD) and stays untouched, recorded as pre-existing.
- Human docs (`docs/plans/`) and OpenSpec `tasks.md` / `acceptance.md` are not touched by this
  batch; the main line owns the round entry.
