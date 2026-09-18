# Design: connect-collection-line

## 1. Why one name (`DATABASE_URL`) and not a new one

The console's Postgres surfaces were always written around `DATABASE_URL`:
`backend/deps.py:4` documents it as "Postgres DSN for app runtime and tests", and the
legacy modules (`api/upload.py`, `api/seeds.py`, `api/pipeline.py`, `api/chat.py`,
`seed_cron.py`) all read it. The failure was never the name — it was that five
reachable readers each invented their own rule, and that nothing ever *gave* the
process a value.

So the change is: keep the established name, remove the duplicated rules, and make
the value travel. Introducing a third name would add configuration surface for no
behaviour.

**`CANONICAL_V2_DATABASE_URL` is a different thing and stays different.** It names the
*serving* database for the V2 operations surface (`backend/canonical_v2_deps.py:20`),
and a test already locks that `DATABASE_URL` must not substitute for it
(`tests/test_canonical_v2_operations_api.py:260-277`). Accepting it in the console
probe (today's behaviour) is precisely the bug that yields "probe green, first read
500s". After this change the probe reads `DATABASE_URL` / `DATABASE_URL_TEST` only.

## 2. Where the value lives, per process

- **Console process**: resolved once at start from the environment
  (`backend/deps.py:resolve_console_dsn()`), carried on `app.state.console_dsn`, and
  read from there by every console surface — the seeds store connection, the uploads
  precheck, the freshness text of the admin status payload, and the jobs gate.
- **Spawned job processes**: the gate injects `DATABASE_URL` into the child
  environment (`JobRuntime._execute`, the single seam that already writes
  `MIROTHINKER_*`). The child (a fresh `python` process running
  `scripts/run_admin_seed_refresh.py`) then resolves it through its own existing
  `resolve_dsn` path — unchanged.
- **The serving line** keeps receiving its database as an argument; nothing in this
  change redirects the serving stack, and no serving-side reader is touched.

The probe and the injection share one resolution (`PostgresProbe.resolved_dsn()`), so
"probe says available" and "the child can connect" can no longer disagree.

## 3. Degradation semantics (unchanged in spirit, now consistent)

| State | Gated API | Page |
|---|---|---|
| console DSN configured, database reachable | 200 | full surface |
| console DSN configured, database unreachable | 503 `seeds_require_postgres` | degraded: create card hidden, reason shown, nav entry hidden |
| console DSN not configured | 503 `console_database_not_configured` | same degraded state (the message names the variable to set) |

A missing configuration never produces a 500: the resolver returns `None` and callers
translate that into the same stable 503 code path they already use.

## 4. Provisioning, as a runbook (not a code path)

The repository does not create databases at runtime. The deployment steps
(create + comment marker + `alembic upgrade head` with the three explicit
`ALEMBIC_*` values + verify) live in the human plan and in
`deploy/README.md`; the marker comment
(`miroflow:destructive-target:v1:isolated-candidate:<name>`) is required by
`resolve_destructive_database_target` and is what makes the target provable.

## 5. Roster import

Reuse `parse_roster_seed_markdown()` (`src/data_agents/professor/parser.py:38`) — the
same parser the professor pipeline already uses — then write through
`backend/storage/seeds.py:create_seed`, skipping rows whose `seed_url` already exists
(`get_seed_by_url`). Idempotent by construction; dry-run by default because it writes
to a live database.

## 6. Adapter coverage decision

`resolve_seed_adapter_name` is URL-pattern based and returns `None` before any fetch,
so an unregistered URL can never be crawled through `/seeds`
(`seed_runner.py:245-321` marks it `adapter_missing`). For the three unresolved
historical seeds:

- `https://www.pkusz.edu.cn/szdw.htm` — extraction support exists
  (`roster.py:620-621`, `discovery.py:86`, `parser.py:27`,
  `institution_registry.py:36`); only the registry matcher is missing → **add it**.
- `https://ai.sztu.edu.cn/info/1332/6055.htm` — a *profile* page, not a roster →
  **fix the data** (the college's `/szdw/jytd/…` roster resolves to
  `sztu-teacher-family`).
- `https://nmne.sztu.edu.cn/picturers.jsp?…` — a legacy CMS path that the
  `sztu-teacher-family` matcher (`roster.py:1536-1542`) deliberately does not match →
  **fix the data** (use the college's `/szdw` list URL).

Broadening the matcher to swallow arbitrary SZTU paths would match non-roster pages;
the registry stays pattern-based and narrow.

## 7. Why entry hiding now

`add-admin-upload-seeds` wrote "degrade to 503 with hidden page entries" and
implemented only the 503 half; `/jobs` even disables its buttons on
`postgres.available`, but the nav links on `/main` are static HTML. One shared script
(`nav_auth.js`, loaded by all six pages) hides `[data-requires-postgres]` entries when
the single status source reports no console database — the same signal the pages
already fetch.

## 8. Out of scope

Retrieval/answer/serving behaviour; re-mounting legacy PG routers; running the crawl
with LLM enrichment on (stays off by default); the C6 rebuild pipeline that turns
collected rows into a serving pack.
