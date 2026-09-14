# Design: add-admin-upload-seeds

Source of truth: `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md`
§4 承接原则, §4-C1/C2, §2 principle 4, §6 W3, §7 W3 risk. Evidence:
`.agents/runs/add-admin-upload-seeds/current-state.md`. Gate under reuse: W2
(`openspec/changes/add-admin-jobs-console/`, `src/data_agents/canonical_v2/jobs.py`).

## 1. Verification surface

Deterministic backend surface, so the primary oracle is **contract + integration**, not eval:

| Surface | Oracle | Why |
|---|---|---|
| Domain white list, `.xlsx` shape, size cap, hash dedup, parameter injection refusal | contract tests (HTTP + module) | the refusal set is enumerable and must be fail-closed |
| Advisory lock and re-entrancy | integration test with two real processes / a held lock file | an in-process stub cannot prove cross-process exclusion |
| Gate reuse (switch/quota/breaker/PG probe) | integration test through `JobRuntime` + the HTTP surface | W3 must be shown to pass the *same* gate, not a copy |
| PG-absent degradation | HTTP test with the probe forced unavailable + a live no-PG scratch server | §2 principle 4 is a runtime property; it must be observed at the HTTP boundary |
| Upload → batch status → duplicate rejection → seed CRUD → preview trigger → run visible | real-interaction smoke on scratch port **18292** against a scratch Postgres | the acceptance line is a sequence of real operations, not a unit property |
| Dry-run parse of a real XLSX | same smoke, real 2–3 row workbook | proves the re-mounted chain actually parses, at zero quota |

Not applicable: retrieval/answer/replay assertions (no RAG behaviour is touched) and browser
automation (the pages are static and are asserted by served-markup checks, as W1/W2 did).

## 2. Where the problem belongs

The plan phrases C1 as "旧 `upload.py` 链…以 V2 路由受限重挂". Read literally that means "re-register
the legacy router". That cannot be the whole answer here, for two reasons found in the current state:

1. The legacy router's every write is Postgres-backed, so re-registering it as-is produces a surface
   that 500s (not 503s) on a serving host without Postgres — it violates §2 principle 4.
2. Its subprocess spawns build the command line themselves (`sys.executable`, ad-hoc env), so a
   re-mounted trigger would bypass W2's gate and its lock/quota/breaker. The task contract requires
   the gate to be **reused, not bypassed**.

So the layer split is: keep the legacy *work* (parse, import, enrichment scheduling, crawl) exactly
where it is, and put the **admission decision** (white list, shape, hash, dedup, lock, gate) in one
new module that owns the serving-side facts. The HTTP layer stays thin — it validates shape and maps
typed refusals to codes, exactly like W2's API module does.

## 3. Options considered

**A. Re-register the legacy routers verbatim, add a probe middleware.** Rejected: the legacy routes
take `Depends(get_pg_conn)`, which raises before any handler can degrade; a middleware cannot choose
a response for a dependency failure without touching every route. It also leaves the trigger path
outside the gate.

**B. Re-implement import/seed logic in the new module.** Rejected: duplicates the domain logic that
the plan explicitly says to reuse, and creates a second source of truth for import semantics.

**C. (chosen) Thin V2 routes + a new "front door" module that owns admission, staging, ledger and
gate dispatch, delegating all real work to the legacy chain through one declared task per chain.**
The legacy modules stay untouched and remain the CLI fallback (which is also W3's rollback story:
"路由摘除即回旧状（CLI 仍可用）").

## 4. Dynamic paths versus a closed argv

W2's `JobTask.argv_for` accepts only values from a declared closed set, which is what makes an
injection impossible. An upload, however, has a server-generated path that cannot be enumerated at
import time. Two ways out:

- **Token parameters (chosen).** `JobTask` gains `token_params: Mapping[str, Callable[[str], str]]`.
  The caller may only pass an **opaque token** matching `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`; the
  module resolves it server-side (for uploads: `UploadStore` → staged path; the resolver re-validates
  that the resolved path is inside the staging root) and raises `JobParameterError` for anything
  unknown. No caller text can reach argv: a rejected token never yields a command, and a resolved
  token always yields a path this process constructed earlier.
- Letting the route append the path to `argv` directly. Rejected: that is exactly the bypass the
  white list exists to prevent.

## 5. Data model (serving side)

`CANONICAL_V2_UPLOADS_DB` → `uploads.sqlite3`, schema `canonical-v2-uploads-v1`:

```
upload(upload_id PK, domain, filename, content_sha256, size_bytes, staged_path,
       status, dry_run, run_id, operator, created_at, updated_at, summary_json)
  index (domain, content_sha256)   -- duplicate lookup
  index (created_at desc)          -- page listing
```

`status ∈ {queued, running, succeeded, failed, rejected, skipped}` — `skipped` mirrors the gate's
switch/quota/window suppression so the page can show "why nothing happened". The ledger never stores
file content, environment, or credentials; the summary is a bounded projection of the child's
`{"job_summary": …}` line, redacted by the gate's `redact_secrets`.

Rationale for a second SQLite file rather than reusing `jobs.sqlite3`: the jobs store is the gate's
run history and is schema-versioned by W2; an upload lifecycle is a different concern with a
different retention and a different rollback boundary. The two are joined by `upload.run_id`.

## 6. Duplicate policy

Three layers, deliberately in this order:

1. **In-flight lock** — `flock` on `<locks>/upload-<domain>-<sha16>.lock`, reusing W2's `JobLock`, so
   two simultaneous identical uploads cannot both pass admission.
2. **Ledger lookup** — `(domain, sha256)` already present with a non-failed status ⇒ 409
   `duplicate_upload` carrying the original `upload_id`, its status and timestamp. This is the answer
   on a serving host with no Postgres.
3. **Legacy PG preflight** — when Postgres is reachable, the legacy `_load_active_duplicate_upload`
   is consulted as before, so a re-upload of a file that was imported *before* W3 (or imported by
   CLI) is still refused.

A previously **failed** upload does not block a retry of the same file — otherwise a transient
failure would permanently poison the hash.

## 7. Degradation boundary (§2 principle 4)

| Endpoint | No Postgres |
|---|---|
| `GET /api/canonical-v2/admin/uploads` (ledger list) | 200 — the ledger is serving-side |
| `POST /api/canonical-v2/admin/uploads/{domain}` | 503 `upload_requires_postgres` |
| `GET /api/canonical-v2/admin/uploads/{id}` | 200 ledger fields, `batch: null` |
| `GET /api/canonical-v2/admin/seeds*`, `POST/PUT/DELETE` | 503 `seeds_require_postgres` |
| Seed trigger | 503 |
| `/upload`, `/seeds` pages | 200, but the page hides the PG-dependent form and states why |

The probe is W2's `PostgresProbe` (`available()` / `describe()`), not a new one, and it is evaluated
per request so a database that comes up later is picked up without a restart.

## 8. Task declarations added to the gate

| Task id | argv (fixed) | cwd | gate flags |
|---|---|---|---|
| `upload-company-import` | `uv run python scripts/run_admin_upload_import.py --domain company --upload-id {upload_id}` | `apps/admin-console` | collection-gated, quota `web_search`, window-bound |
| `upload-patent-import` | same with `--domain patent` | `apps/admin-console` | collection-gated, quota `llm` |
| `upload-professor-import` | same with `--domain professor` | `apps/admin-console` | collection-gated, quota `llm` |
| `professor-seed-refresh` | `uv run python scripts/run_admin_seed_refresh.py --seed-id {seed_id} --trigger-mode {mode} [--limit {limit}]` | `apps/miroflow-agent` | collection-gated, quota `web_search` |

`seed_id` is an integer token (`^\d{1,12}$`), `mode` is a closed set, `limit` is a closed set
(`5/20/50/100`) required only for `sample` — the gate's existing refusal shapes cover all of them.
Env override `COMPANY_UPLOAD_ENRICHMENT_DISABLE_AUTORUN=1` is honoured by the legacy chain and is set
in the acceptance smoke so that a *tracked* batch is created without running any enrichment.

## 9. Risks and rollback

| Risk | Handling |
|---|---|
| W3 declares tasks that spawn `uv run`; the W2 timeout kill leaks the grandchild (§2.1 of the evidence) | fix the spawn helper: `start_new_session=True` + `os.killpg(SIGKILL)` on timeout, with a regression test |
| A new module could drift into re-implementing import semantics | the import path is only ever the legacy chain, invoked through one declared task; no import logic is copied |
| The upload ledger and the legacy PG state can disagree | the ledger is explicitly the *serving-side* record; PG remains the authority for import/batch rows and is read for batch progress when reachable |
| Rollback | remove the router/page lines (legacy CLI unaffected); delete the SQLite file |

## 10. Verification intent

`verification-contract.md` (created before production-code edits) names the RED artifacts R1–R6, the
GREEN evidence, and the non-goals. The acceptance smoke runs on **18292** with a scratch Postgres,
scratch storage and a 2–3 row test workbook; no full crawl is ever triggered and the only seed mode
exercised is `preview`.
