# Tasks: connect-collection-line

## A · Console DSN contract (single source)

- \[x\] A1 `backend/deps.py`: `resolve_console_dsn()` — the only reader of
  `DATABASE_URL` / `DATABASE_URL_TEST`; returns `str | None`; blank strings count as
  unset. → verify: unit tests for both names, precedence, blank handling.
- \[x\] A2 `backend/main.py`: resolve once at start, carry on `app.state`, hand the
  value to the jobs gate; log configured/not-configured (never the DSN itself).
  → verify: app test for both states. **Note:** the line is emitted at INFO on the
  `backend.main` logger, which the current process logging configuration does not
  surface; the wiring is proved instead by `/proc/<pid>/environ` plus a real call of
  `_resolve_console_database()` and of `PostgresProbe.describe()`
  (`available: True, source: DATABASE_URL`).
- \[x\] A3 Repoint the reachable readers at the resolved value:
  `canonical_v2_seeds._seed_connection`, the uploads precheck path
  (`canonical_v2_uploads` → `upload._resolve_upload_dsn`), and
  `canonical_v2_admin_status`'s build-database freshness text. → verify: with only
  `CANONICAL_V2_DATABASE_URL` set, the console reports its database unavailable and
  gated endpoints answer a stable 503 `console_database_not_configured` (never 500).
- \[x\] A4 `PostgresProbe.ENV_ORDER` drops `CANONICAL_V2_DATABASE_URL` and gains
  `resolved_dsn()`; probe and injection share it. → verify: probe tests for the two
  accepted names and the now-ignored one.

## B · Gate injects the DSN into spawned jobs

- \[x\] B1 `JobRuntime._execute` injects `DATABASE_URL` (when resolved) into the child
  env beside the four existing keys. → verify: runner test asserts the key, its
  absence when unresolved, and keeps the existing "env is never persisted" assertion
  green.

## C · Provisioning and wiring (this deployment)

- \[x\] C1 Create `miroflow_collection_v1` with the destructive-target marker; apply
  alembic to head (`V042`); verify the five key tables and a real `list_seeds` read.
  → verify: dry run on a throwaway database first (43 revisions, 0.8 s, 42 tables),
  then the keeper database; offline CRUD rehearsal through the console store and the
  crawler's `_load_seed`.
- \[x\] C2 systemd drop-in `database-url.conf` carrying the console DSN;
  `daemon-reload`; restart; wait for `/api/health`. → verify: boot 660 s, health 200,
  `DATABASE_URL` present in the serving process environment, public faces unchanged
  (`/chat` 200, gates 302).
- \[ \] C3 Live-line verification **page half pending a session**: the no-session half
  passed (probe available, new page markers served). Still to run with an
  authenticated operator: `/seeds` 200 with the imported registry, create → update →
  delete, trigger, `/jobs` run visibility.

## D · Roster import and adapter coverage

- \[x\] D1 `apps/admin-console/scripts/import_professor_seeds.py` (idempotent,
  dry-run default, `--apply` to write): parse with `parse_roster_seed_markdown()`,
  skip by `seed_url` via `get_seed_by_url`, report created/skipped/unresolved.
  → verify: 10 unit tests (stub registry, no database) + a real dry run
  (50 parsed → 39 distinct → would_create 38) and a real `--apply` (38 rows, second
  run creates 0).
- \[ \] D2 pkusz registry matcher with a test (done: `pkusz-szdw-hub`, 5 tests) and
  corrected SZTU URLs. **38 of 39 resolve** — the `nmne.sztu.edu.cn`
  `picturers.jsp` entry has no `/szdw…` URL on its host (all such paths 404) and the
  `sztu-teacher-family` matcher is deliberately narrow, so it is skipped by the
  importer and recorded here rather than papered over by a broad matcher.

## E · Entry honesty and failure visibility

- \[x\] E1 `nav_auth.js` hides `[data-requires-postgres]` entries when the console
  database is available=false; `main.html` marks `/seeds` and `/upload` (and now
  loads the shared script). → verify: page-shell tests + fail-open cases.
- \[x\] E2 `/upload` commit control and copy agree in the degraded state; dry-run
  stays reachable because the backend still admits it.
- \[x\] E3 `GET /api/canonical-v2/admin/seeds/{id}/runs` carries `status`,
  `exit_code`, `stderr_excerpt`; `seeds.html` renders the reason for a failed row
  (escaped + truncated) and explains `console_database_not_configured`.
  → verify: API test + page-shell test.

## F · Verification

- \[x\] F1 Targeted suites green (**132 passed, 1 skipped** admin-console;
  **251 passed** professor subset); full `apps/admin-console` before/after of
  130 failure lines each, `comm` empty in both directions (zero new failures).
- \[x\] F2 One real `preview` and one `sample` (limit=5) run through the gate's own
  entry: preview `succeeded` in **7.5 min** (`items_processed: 1`); sample
  `succeeded` and wrote **professor 5 / professor_affiliation 5 / source_page 9**;
  the registry view reads `success`. The first preview attempt was killed by the
  operator's own 280 s timeout and its row had to be released by hand (finding
  below).
- \[x\] F3 Evidence under `.agents/runs/connect-collection-line/`; ledger row ticked;
  human log appended; index line updated.

## G · Defect fixed while verifying

- \[x\] G1 `open_pipeline_run` / `close_pipeline_run` used `now()` — Postgres's
  *transaction start* — so a crawl that writes inside one transaction recorded
  `finished_at == started_at` (a 7.5-minute crawl logged as 3 ms, and the registry's
  最近运行 time derived from it). Changed to `clock_timestamp()`; proved on the real
  database (2 s sleep inside one transaction → delta `0:00:00` before,
  `0:00:02.002` after) and locked by
  `tests/storage/test_pipeline_run.py::test_close_records_elapsed_time_not_the_transaction_start`
  (RED `1 failed, 3 passed` → GREEN `4 passed`).

## H · `/jobs` operator clarity (round 6)

The page listed 15 tasks flat, with the script path as the primary label and no statement of
when to press anything. Behaviour-affecting (payload contract + page), implemented on the
slice contract supplied by the operator.

- \[x\] H1 `JobTask` gains required `group` (`collection | import | seed | ops`) and
  `operator_hint`; both exported by `as_dict()`, both populated for all 15 declared tasks.
  → verify: `test_every_task_carries_operator_copy_for_the_page` +
  `test_task_payload_exports_the_operator_columns` (RED `AttributeError` / `KeyError`
  before the fields existed → GREEN `47 passed`).
- \[x\] H2 `/jobs` renders four group sections with their purpose lines, the operator hint
  per task, a status badge with a local `YYYY-MM-DD HH:mm`, capability tags and the trigger
  controls; task id / command / timeout / cron move into a per-task `<details>`.
  → verify: page-shell markers in `test_canonical_v2_jobs_api.py` + the render harness over
  a real `task_views()` payload
  (`.agents/runs/connect-collection-line/jobs-page-harness/`).
- \[x\] H3 Token tasks keep no trigger: `seed_id` → `/seeds`, `upload_id` → `/upload`.
  (The brief's single `/seeds` link would have sent upload operators to the roster page.)
- \[x\] H4 运行历史 keeps the filter / refresh / breaker-reset flow and the detail panel;
  rows show Chinese status, local times, 秒/分 durations and the failure reason inline.
- \[ \] H5 (not done) the inline failure reason has no stderr to show: the list payload
  serialises runs with `include_samples=False`. One backend line
  (`as_dict(include_samples=True)` for failed rows) closes it; the page already renders the
  excerpt when present.

## I · Model configuration on `/admin` (roles, presets, model discovery)

- \[x\] I1 The connection card becomes 模型与连接 organised by role (对话模型 /
  采集模型 / 嵌入模型 / 重排模型 / Web 搜索), each showing the runtime-effective value,
  its origin and the actions that apply.
- \[x\] I2 `GET /api/canonical-v2/admin/connections/presets` — a small generic provider
  table (本地 OpenAI 兼容 / DeepSeek / 阿里云百炼兼容模式 / OpenAI / 硅基流动 / 自定义)
  with default base URLs, docs links and whether a key is needed, plus the chat-profile
  list and the current selection. No deployment-specific hosts baked in.
  → **backend done** (`canonical_v2_admin_config.py:416-446`,
  `canonical_v2_connection_tests.py:140-248`); verify: 5 route tests in
  `tests/test_canonical_v2_model_discovery_api.py`. Page half = I1.
- \[x\] I3 `POST /api/canonical-v2/admin/connections/{key}/models` — probe
  `{base_url}/v1/models` with the *unsaved* form values (same body as
  `connections/test`, same rate limit), returning the id list, the exact request URL
  and elapsed ms, or a structured error (unauthorized / unreachable / not_supported /
  timeout). Stores nothing.
  → **backend done** (`canonical_v2_admin_config.py:448-493`,
  `canonical_v2_connection_tests.py:461-627`; 3 s timeout, 512 KB read, 500-id cap,
  `body_excerpt` redaction); verify: 11 route tests incl. all five error codes and the
  key-never-echoed case. Page half = I1.
- \[x\] I4 对话模型 becomes a profile picker: a new catalogue row
  (`serving.chat_llm_profile` → `CHAT_LLM_PROFILE`) so the choice travels the existing
  save→restart path, with the profile's model/base_url shown before saving.
  → **backend done** (`managed_config.py:59,228,505-512,745,913-941`; unknown names are
  refused on save — the check sits on the write path, not in the schema, because the
  schema also validates env-overridden documents the serving line tolerates); verify:
  2 catalogue tests + 1 bootstrap test. Page half = I1.
- \[x\] I5 嵌入模型 is labelled as the frozen serving-index value (page read-only, with
  the rebuild consequence spelled out); the collection-side override is shown
  separately and labelled as not affecting the serving index.
  → **backend done** (both rows in `PAGE_READONLY_FIELDS`, `managed_config.py:86-96`,
  reasons spell out the frozen bundle *and* that no runtime code reads the projected
  variables); verify: `test_the_frozen_embedding_rows_are_display_only`. Page copy = I1.
- \[x\] I6 Tests: route tests for the two new endpoints, a page-shell test for the role
  card, and an invariant that every role renders the runtime-effective value.
  → route tests **done** (20 in `tests/test_canonical_v2_model_discovery_api.py`);
  the page-shell test and the role invariant belong to the page half.

## Findings recorded, not fixed here

- A killed crawl leaves its `pipeline_run` row in `running` forever (no heartbeat,
  no timeout finalizer, no stale sweep), so the registry shows that seed as
  "进行中" indefinitely while `/jobs` knows the truth. Candidate slice.
- A crawl of one seed takes minutes (SUSTech preview: 7.5 min), which is why the
  gate's 5400 s task timeout and the 20 s per-request fetch timeout matter; a
  page-level trigger should not be expected to return in seconds.
- `pipeline_run.seed_id` is a nullable TEXT column and is empty in practice — the
  seed association lives in `run_scope->>'seed_id'` (as the registry store's SQL
  assumes); querying the column directly finds nothing.
- The startup `console_database=` INFO line is invisible under the current process
  logging configuration.
- The upload commit preflight can still 500 (not 503) when the console database is
  unconfigured on a path that does not pass the gate; unchanged from before.
- `backend/deps.py` carries two pre-existing ruff F401s (present at HEAD).
