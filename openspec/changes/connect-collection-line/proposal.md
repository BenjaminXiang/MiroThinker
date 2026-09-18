# Proposal: connect-collection-line

## Why

The admin zone's Postgres-backed surfaces are dead on this host, and the cause is
structural rather than a missing flag:

- `/seeds` (professor roster registry + crawl trigger) answers **503
  `seeds_require_postgres`** on the live line; `/upload`'s commit path dies the same
  way. The gate's probe reads `CANONICAL_V2_DATABASE_URL` / `DATABASE_URL` /
  `DATABASE_URL_TEST` (`src/data_agents/canonical_v2/jobs.py:1142`), while the serving
  process receives its database as a **command-line argument** (`--database-url …`,
  pinned in the s12g serve command) and carries **no** DSN variable in its
  environment. Nothing in the repository projects the argv DSN into the environment.
- Sixteen DSN-resolution sites disagree on names and failure modes. Two of them are
  inconsistent with each other in the worst way: the probe accepts
  `CANONICAL_V2_DATABASE_URL`, but the seeds connection
  (`backend/api/canonical_v2_seeds.py:109`) does not — a deployment in that shape
  shows a green probe and then 500s on the first read.
- No database on this host has the schema these surfaces need: no `professor_seed`,
  no `pipeline_run`; the 43-revision alembic chain has never been applied to any host
  database, and there is no collection/domain database at all.
- The gate never injects a DSN into the processes it spawns
  (`jobs.py:1587-1592` copies the parent environment and adds four `MIROTHINKER_*`
  keys), so a triggered crawl reaches a database only by inheriting ambient env.
- The registry is empty and the 39 historical seeds in
  `apps/miroflow-agent/scripts/e2e_seeds/*.md` have no importer; three of them point
  at URLs no registered adapter can serve (two wrong-shaped SZTU URLs and Peking
  University Shenzhen, which has extraction support but no registry entry).
- A failed run is undiagnosable from the page: `/seeds` renders a "失败" pill only,
  while the exit code and stderr live in the jobs ledger.

## What Changes

Behaviour-affecting (configuration contract, admin API payloads, one new script, the
adapter registry, page behaviour):

1. **One console DSN contract.** `DATABASE_URL` is *the* console/collection database.
   `backend/deps.py` gains the single resolver every console surface uses; the value
   is resolved once at application start and carried on `app.state`.
   `CANONICAL_V2_DATABASE_URL` keeps exactly one meaning — the *serving* database of
   the V2 operations surface — and stops being accepted as a substitute by the probe.
2. **The gate injects the DSN once.** `JobRuntime._execute` injects the resolved
   console DSN into every spawned job's environment, at the same seam that already
   adds the quota/job keys, so `run_admin_seed_refresh.py` and
   `run_admin_upload_import.py` no longer depend on ambient env.
3. **Provisioning is documented, not coded.** A collection database
   (`miroflow_collection_v1`, destructive-target marker
   `miroflow:destructive-target:v1:isolated-candidate:miroflow_collection_v1`, alembic
   head `V042`) is created on the local cluster and the console reads it through a
   systemd drop-in; the repository ships the re-runnable create/migrate/verify
   runbook.
4. **Roster import.** One idempotent script parses `scripts/e2e_seeds/*.md` with the
   existing `parse_roster_seed_markdown()` and creates missing rows through the
   console's own `create_seed` store; dry-run by default, `--apply` to write.
5. **Adapter coverage.** A registry matcher for `pkusz.edu.cn` (extraction support
   already exists in `roster.py` / `discovery.py` / `parser.py`) plus corrected URLs
   for the two wrong-shaped SZTU entries, so all 39 historical seeds resolve.
6. **Entry honesty.** The shared nav script hides gated entries when no console
   database is configured — the "hidden page entries" half of
   `add-admin-upload-seeds` that was never implemented — and `/upload` stops claiming
   its button is hidden while showing it.
7. **Failure visibility.** `GET /api/canonical-v2/admin/seeds/{id}/runs` carries
   `status` / `exit_code` / `stderr_excerpt`, and `/seeds` renders the reason inline.
8. **The registry is editable in place.** Each `/seeds` row has 修改: school,
   department and roster URL are edited inline and saved through the existing
   `PUT /seeds/{id}` — school sites reorganise, and the alternative (delete +
   recreate) would lose the id and its run history.
9. **The config page speaks in model roles.** `/admin`'s connection card becomes
   模型与连接, organised the way every comparable product (LobeChat, Open WebUI,
   LibreChat, Dify, Cherry Studio) organises it — by *role* rather than by storage
   location: 对话模型 / 采集模型 / 嵌入模型 / 重排模型 / Web 搜索. Each role gets a
   provider preset table (display name + default base URL + docs link + whether a key
   is needed), a **fetch model list** action that probes `{base_url}/v1/models` with
   the *unsaved* form values and lets the operator pick (with manual id entry as a
   first-class fallback), the resolved request URL shown before testing, and the
   existing "save ≠ test, restart to apply" semantics. 嵌入模型 is presented as a
   **服务于检索索引的冻结值**（页面只读 + 说明"改它要重建索引"），with the
   collection-side override shown separately and labelled as such.
10. **The jobs page speaks to operators.** The task catalog carries `group` and
   `operator_hint` (plain-language "what it does / when to use it") and an invariant
   test forbids a task without them; `/jobs` groups the 15 tasks by purpose, shows
   Chinese statuses, plain-language tags and either 立即运行 with Chinese parameter
   selects or a link to the page that owns the task (seed → `/seeds`, upload →
   `/upload`), moving ids/commands/cron into a collapsed 技术细节. The run list also
   serialises run samples so a failed row shows its reason inline.

## What stays the same

Retrieval, fusion, rerank, answer, the serving pack and `/chat`. The degradation
principles hold: with no console database the gated surfaces refuse with a stable
code and a hidden/degraded entry — never a 500, never a crash. The legacy
PG-dependent routers (`pipeline`, `pipeline_issues`, `dashboard`, …) stay unmounted;
their diagnostics are not worth re-mounting a fleet of off-line dependencies.
