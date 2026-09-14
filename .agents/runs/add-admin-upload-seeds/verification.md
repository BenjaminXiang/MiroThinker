# Verification: add-admin-upload-seeds (W3)

Branch `feat/admin-upload-seeds` (baseline `feat/admin-jobs-console` @ `3d9dd7c0`).
Layered per the user rule of 2026-08-18: ① new tests of this slice, ② pre-existing suites with the
failure-set diff, ③ real-interaction evidence, then the two special reports the W3 task contract asks
for (④ the subprocess verdict, ⑤ the orphan-process defect) and ⑥–⑦ the honest gaps and quota.

---

## ① New tests written in this slice

Commands (all run in `/home/longxiang/MiroThinker/.worktrees/admin-upload-seeds/apps/admin-console`):

```
uv run --no-sync pytest -q tests/test_canonical_v2_uploads_registry.py tests/test_canonical_v2_uploads_store.py \
  tests/test_canonical_v2_uploads_runtime.py tests/test_canonical_v2_uploads_api.py tests/test_canonical_v2_seeds_api.py
uv run --no-sync pytest -q tests/test_canonical_v2_jobs_runner.py
```

| Cluster | File | Cases | What it locks | Fixture source |
|---|---|---|---|---|
| R1 registry closure | `tests/test_canonical_v2_uploads_registry.py` | 8 | Every W3 task exists with a fixed argv, its script resolves in the repo, upload tasks declare the upload token as their only caller value, mode/limit stay in closed sets, and the injection matrix (path separator, whitespace, `;`, leading dash, over-length, unknown token, undeclared name) is refused before any argv exists | constructed scenarios |
| R2 ledger | `tests/test_canonical_v2_uploads_store.py` | 7 | Admit/list/newest-first/domain filter/detail, duplicate identity lookup, failed-then-retry, summary truncation + credential redaction, no workbook bytes on disk | constructed scenarios |
| R3 admission | `tests/test_canonical_v2_uploads_runtime.py` | 17 | Domain white list, `.xlsx`/empty/oversize, sha256 identity, cross-process advisory lock exclusion, duplicate 409 carrying the first upload, failed upload does not poison the hash, dry-run writes nothing, gate switch-off recorded as `skipped`, gate refusal recorded as `rejected` with the gate code, effective quotas reach the child env | constructed scenarios; stub gate spawn |
| R4/R7 API + pages | `tests/test_canonical_v2_uploads_api.py` | 10 | 202 admit, 409 duplicate, 422 domain, 400 shape, 413 size, 503 commit without Postgres (dry-run still admitted), list/detail payloads, all six pages 200 with all seven nav targets, degradation blocks present | constructed scenarios |
| R6 seed surface | `tests/test_canonical_v2_seeds_api.py` | 5 (1 skipped without a test DB) | Every seed endpoint 503 without Postgres, `sample` without a limit refused, out-of-set mode/limit refused, the trigger uses the declared task and its argv, run polling, CRUD round trip | constructed scenarios; CRUD needs `DATABASE_URL_TEST` |
| R5 process-group kill | `tests/test_canonical_v2_jobs_runner.py` (extended) | +1 | A timed-out spawn leaves no grandchild alive | constructed scenario mirroring `uv run` (direct child spawns a worker) |

Totals for the touched suites: **140 passed, 1 skipped** (the seed CRUD integration case, which needs a
configured test database); the R5 case also passes when run alone.

Two pre-existing W2 registry tests were **fact-updated, not weakened** (see `verification-contract.md`
and the log §3): the task census is now `PLAN_WHITELIST | W3_ADDITIONS` (exact — an extra or missing
task still fails) and the "fixed token tuple" case supplies stub resolvers for declared tokens. The
behavioural locks (unknown task, undeclared parameter, out-of-set value) are untouched.

## ② Pre-existing regression suites — before/after with zero new failures

**Why the "before" run is not re-run.** W3's baseline commit is the W2 tip `3d9dd7c0`, and the W2 slice
recorded a complete run of this same suite at that exact commit in the same environment
(no `DATABASE_URL_TEST`). That artifact is therefore W3's before-run; re-running it would produce the
same numbers from the same tree.

| Side | Command | Source | Result |
|---|---|---|---|
| before | `cd apps/admin-console && uv run pytest -q` at `3d9dd7c0` | `/home/longxiang/MiroThinker/.worktrees/admin-jobs-console/.agents/runs/admin-jobs-console-w2/full-suite-after.txt` (+ `failures-after.txt`), copied here as `full-suite-before.txt` / `failures-before.txt` | `96 failed, 1130 passed, 29 skipped, 122 errors in 188.45s` |
| after | same command on this branch | `full-suite-after.txt` | `96 failed, 1192 passed, 30 skipped, 122 errors in 200.67s` |

Failure-set comparison (module::test ids; the `FAILED`/`ERROR` prefix is stripped first, then both
lists are sorted, then `comm`):

```
sed 's/^\(FAILED\|ERROR\) //' failures-before.txt | sort -u > before.ids
sed 's/^\(FAILED\|ERROR\) //' failures-after.txt  | sort -u > after.ids
comm -13 before.ids after.ids  →  failures-new-comm.txt   (empty)
comm -23 before.ids after.ids  →  failures-fixed-comm.txt (empty)
```

Result: **0 new failures, 0 fixed** — the failing id set is unchanged at **218 entries**, and the
counts move only in the expected directions (`passed` +62 = the new cases in this slice plus the
parametrized cases the extended task table adds; `skipped` +1 = the seed CRUD case that needs a test
database). The pre-existing failures are the W2 set: tests that need a configured Postgres or a live
service, none of them in a module this slice touches.

Pre-existing failures are unrelated to this change (they are the same set W2 recorded: tests that need
a configured Postgres or a live service). The newly added test files all pass; the two W2 registry
cases that had to change were updated in the same commit as the table extension.

## ③ Real-interaction evidence — scratch 18292

Environment: scratch Postgres container on **18293** (throwaway, dropped and recreated for this run,
Alembic `upgrade head`), scratch storage under `/var/tmp/w3-smoke-18292/`, scratch managed settings,
synthetic workbooks (3 company rows; 2 patent rows). **18188 was never addressed or restarted.**

Transcript: `.agents/runs/add-admin-upload-seeds/scratch-18292-smoke-transcript.txt`
(raw HTTP bodies: `scratch-18292-*.json`, pages: `scratch-18292-page-*.html`).

```
health=200; /upload /seeds /jobs /browse /logs /admin → 200
company upload (commit)      → 202; gate run succeeded (exit 0, 1888 ms, command = declared argv)
domain store after import    → company 3 · import_batch 1 · company_enrichment_batch 1
duplicate upload (same bytes)→ 409 duplicate_upload carrying the first upload_id + status
batch progress on detail     → available=true, companies 3/3, items {queued: 3}
patent dry-run upload        → 202 → succeeded, rows_read=2, records_parsed=2, imported=0
seed create/list/update      → 201 / 200 / 200
seed preview trigger         → 202, task admin-seed-refresh, run recorded, mode=preview
seed sample without limit    → 422
seed runs                    → 200, the triggered run is listed (status failed, adapter_missing)
seed delete / re-read        → 204 / 404
upload ledger after          → 2 records (company succeeded, patent dry-run succeeded)
```

No-Postgres phase (second scratch server on the same port, no DSN in its environment):

```
/api/health                                  → 200
POST /uploads/company (commit)               → 503 upload_requires_postgres
GET  /seeds, POST /seeds, POST /seeds/{id}/trigger → 503 seeds_require_postgres
GET  /uploads (ledger)                       → 200, postgres.available=false
/upload, /seeds                              → 200, degradation blocks present in the markup
```

Transcript: `.agents/runs/add-admin-upload-seeds/scratch-18292-nopg-transcript.txt`.

Cleanup: the scratch servers were stopped and `ss -ltn` shows **no listener on 18292**; 18188's health
remained 200 with the same PIDs (1992439/1992450) throughout.

## ④ The W3 subprocess verification point — verdict: **runs, no degradation needed**

Evidence: `.agents/runs/add-admin-upload-seeds/current-state.md` §2 and the raw probe output
`probe/probe-result.json` (probe launched the way the V2 shell is launched, calling W2's own
`_spawn_subprocess`).

| Question | Answer | Criterion |
|---|---|---|
| Can the shell spawn the legacy scripts? | Yes — `uv run python scripts/run_company_upload_enrichment_batch.py --help` rc=0 in 0.75 s from inside the shell process (case C), `sys.executable` variant rc=0 (case D) | the script's own module-level imports resolved and argparse ran |
| Does the environment reach the child? | Yes — the sentinel variable set by the parent arrived in the grandchild (cases A/B), so the gate's quota/`DATABASE_URL`/`MIROTHINKER_JOB_*` injection works | child self-report |
| Is the working directory right? | Yes — `apps/miroflow-agent` for the collection tasks, `apps/admin-console` for the upload task; a bad cwd fails at launch and is recorded as a failed run (case F) | child self-report / launch error |
| Is `uv` reachable? | Yes — `~/.local/bin/uv` is on the PATH the shell inherits; nested `uv run` is allowed and only adds `UV_RUN_RECURSION_DEPTH` | probe shell report |
| Do timeouts work? | Yes, and the kill now covers the process group (case E + R5) | `TimeoutExpired` at 1 s; run recorded as exit 124 / failed |
| Cost of a cold shell? | First `uv run` in the worktree builds the local packages (~2.2 s); afterwards 0.03–0.06 s | measured |

Consequence: the plan's fallback ("保留 CLI 导入 + 简化状态页") is **not** invoked.

## ⑤ Orphan-process defect (R5): found by the same probe, fixed here, W2-owned

Reproduction (probe §2.1, deterministic):

```
TimedOut after 3s; captured stdout: b'w3orphanmarker\n'
orphan_survivors: 1
  368806 …/apps/miroflow-agent/.venv/bin/python3 -c import time,sys;print('w3orphanmarker',…
```

`subprocess.run(timeout=…)` kills only the direct child; `uv run` puts the real worker in a
**grandchild**, which survives. The gate therefore recorded `failed` (exit 124), **released the flock**,
and left a process that could still spend quota, write rows, and be joined by a second run.

- Fix (landed in `9c58cdfa`, `apps/miroflow-agent/src/data_agents/canonical_v2/jobs.py`):
  `start_new_session=True` on the spawn and `os.killpg(..., SIGKILL)` on timeout, then reap with
  `communicate()` so the timeout still carries stdout/stderr.
- Regression: `test_a_timed_out_spawn_leaves_no_grandchild_behind` (fails on the pre-fix helper).
- Ownership: the defect is in **W2's** spawn helper (cross-slice). W3 must fix it because W3 declares
  tasks that run through `uv run`; fixing it is *using* the shared gate, not replacing it. All W2 tests
  still pass (see ②).

## ⑥ Not verified / deliberately out of scope

1. **The seed crawl itself.** The smoke seed points at a synthetic `.invalid` school with no registered
   adapter, so the run ends `adapter_missing`: the gate admission, the subprocess boundary, the
   argument wiring and the run record are all exercised, the crawl is not. Running a real `preview`
   against a real roster issues an outbound request, which is a product decision to make explicitly.
2. **`test_seed_crud_round_trip` skips without `DATABASE_URL_TEST`.** The same CRUD was exercised for
   real in the 18292 smoke; making it a permanent regression needs a standing test database.
3. **No RAG/retrieval/replay assertion**: no retrieval, fusion, rerank, answer or citation behaviour is
   touched by this slice.
4. **W4/W6/W7 surfaces** are untouched by design.

## ⑦ Quota actually spent

| Resource | Spent | Mechanism that prevented spending |
|---|---|---|
| Web-search (Serper/Bocha) calls | **0** | synthetic workbooks; `COMPANY_UPLOAD_ENRICHMENT_DISABLE_AUTORUN=1` so the enrichment batch is created but never executed; seed mode `preview` only, against an adapter-less seed |
| LLM calls | **0** | same; no import path in this smoke invokes an LLM |
| Outbound network fetches | **0** | every URL in the fixtures is `example.com` / `.invalid`; the seed never reached the crawl stage |
| XLSX rows processed | 3 (company, committed) + 2 (patent, dry-run) | synthetic, generated for this run |

Full-suite runs consume no quota (Postgres-dependent cases skip without `DATABASE_URL_TEST`).
