# W3 current-state evidence + subprocess verification point (2026-09-14)

Slice: `add-admin-upload-seeds` (W3 数据正门承接) on branch `feat/admin-upload-seeds`
(parent `feat/admin-jobs-console` @ `3d9dd7c0`).

Two questions are answered here, read-only first, then by a live probe:

1. What exists today for the XLSX upload chain and the professor-seed chain, and what do they need?
2. **The W3 first technical verification point**: can the legacy `subprocess` chain (`uv run
   scripts/...`) run inside the V2 admin shell, with env pass-through, cwd, uv on PATH and timeouts?

## 1. What exists today

| Fact | Evidence |
|---|---|
| The upload API (`backend/api/upload.py`) and the seed API (`backend/api/seeds.py`) still carry the full legacy business logic, but **neither module is mounted**: `backend/main.py` includes only chat/operations/consumers/corrections/manual-recall/access-logs/admin-config/jobs, and the `/api/{path:path}` catch-all returns 404. | `apps/admin-console/backend/main.py:83-97` |
| Every upload path is Postgres-backed: `_handle_upload` opens a `pipeline_run` row and inserts a source page through `get_pg_conn`; company import goes to `import_company_xlsx_to_postgres`, patent import to `_run_patent_upload_pipeline`, both through `_resolve_upload_dsn()`. | `backend/api/upload.py:83-100,126-213,754-804,1167-1257` |
| Professor seed CRUD + trigger are Postgres-backed: `get_pg_conn` dependency, `backend/storage/seeds.py` SQL helpers, `claim_seed_for_trigger`, `open_pipeline_run`. | `backend/api/seeds.py:66-235` |
| The seed **trigger runs in-process**, not as a subprocess: `_schedule_seed_run` submits to a module-level `ThreadPoolExecutor` which calls `run_single_seed(...)` in the serving process. | `backend/api/seeds.py:251-286,387-408` |
| The legacy enrichment chain **is** a subprocess chain: `_schedule_company_enrichment_batch` spawns `sys.executable scripts/run_company_upload_enrichment_batch.py --batch-id …` with `cwd=apps/miroflow-agent` and `start_new_session=True`; the per-connector news/signal runs use `sys.executable scripts/run_company_news_ingest.py` etc. through `subprocess.run`. | `backend/api/upload.py:858-912,968-1066,1094-1136` |
| `sys.executable`, not `uv run`, is what the legacy chain actually spawns. The §4-C1 plan text says `uv run scripts/...`; the code says `sys.executable`. Both are exercised by the probe below. | `backend/api/upload.py:867,987,1016,1029` |
| The serving host has no domain Postgres. The only reachable Postgres on this machine are the candidate-build container (`127.0.0.1:55458`, used by 18188) and an unrelated listener on `25432`; neither is the domain database, and the serving process is started with `--database-url` as a CLI argument, not as a `DATABASE_URL` env var. | `ps -o cmd -p 1992439`, `ss -ltn`, W2 `current-state.md` §3 |
| The scratch-Postgres convention for tests is `DATABASE_URL_TEST` (must not contain `miroflow_real`), with Alembic migrations applied by `conftest`. | `apps/admin-console/tests/conftest.py:25-74` |
| W2's gate is the single funnel for triggers: `JobRuntime.trigger()` → PG probe → breaker → switch → quota → cross-process `flock` → `start_run` → spawn. `JobTask.argv_for` refuses any parameter that is not in a declared closed set, and `_spawn_subprocess` is the only spawn helper. | `src/data_agents/canonical_v2/jobs.py:186-217,1113-1124,1299-1401` |

## 2. Subprocess verification point — **RESULT: the legacy subprocess chain runs inside the V2 shell**

Probe: `.agents/runs/add-admin-upload-seeds/probe/probe_server.py`, launched exactly like the V2
shell is launched (`cd apps/admin-console && uv run python …`), listening on the W3 scratch port
**18292** (18188 untouched). The probe calls W2's own `_spawn_subprocess` unchanged, so the answer
applies to the gate that W3 must go through. Raw output:
`probe/probe-result.json` (captured 2026-09-14).

Shell process (the parent the question is about):

```
executable  = …/apps/admin-console/.venv/bin/python
uv_on_path  = /home/longxiang/.local/bin/uv     (PATH already carries ~/.local/bin)
virtual_env = unset
```

| # | Case | argv | cwd | Result |
|---|---|---|---|---|
| A | uv run + echo child | `uv run python -c <echo>` | `apps/miroflow-agent` | **rc=0 in 0.06 s**; child exe = `apps/miroflow-agent/.venv/bin/python3`; cwd correct; sentinel env var arrived |
| B | sys.executable + echo child | `sys.executable -c <echo>` | `apps/miroflow-agent` | **rc=0 in 0.03 s**; child exe = admin-console venv python; env/cwd correct |
| C | legacy script through uv | `uv run python scripts/run_company_upload_enrichment_batch.py --help` | `apps/miroflow-agent` | **rc=0 in 0.75 s** — module-level imports (`psycopg`, `src.data_agents…`) resolved, argparse help printed |
| D | legacy script through sys.executable | same script, `sys.executable` | `apps/miroflow-agent` | **rc=0 in 0.72 s** |
| E | timeout 1 s on a 30 s sleeper | `uv run python -c "time.sleep(30)"` | `apps/miroflow-agent` | `TimeoutExpired` raised at 1.0 s → W2 records exit 124 / `failed` |
| F | bad cwd | — | non-existent dir | `FileNotFoundError` at launch → W2 records a `failed` run |

Detail that matters:

- **env pass-through works**: the sentinel variable set by the parent arrived in the child in both A
  and B, so quota/`DATABASE_URL`/`MIROTHINKER_JOB_*` injection through `_execute` reaches the
  grandchild. `uv run` adds only `UV_INDEX_URL` and `UV_RUN_RECURSION_DEPTH` to the child env.
- **nested `uv run` is fine**: uv sets `UV_RUN_RECURSION_DEPTH` (depth 2 here) instead of refusing;
  the inner run reused the project venv with no re-sync (`--no-sync` also verified: rc=0, 0.03 s).
- **first-run cost**: the very first `uv run` in a worktree builds the local `miroflow-tools` +
  `miroflow-agent` packages (~2.2 s) before the venv exists; afterwards a spawn is 0.03-0.06 s.
  A cold *serving* host therefore pays a one-time sync cost inside the first triggered run.

### 2.1 Consequence: `subprocess.run(timeout=…)` leaks the grandchild — found by the same probe

`uv run` execs a **grandchild**. `subprocess.run(..., timeout=N)` kills only the direct child
(`uv`), so the real python process survives as an orphan. Reproduced deterministically:

```
TimedOut after 3s; captured stdout: b'w3orphanmarker\n'
orphan_survivors: 1
    368806 …/apps/miroflow-agent/.venv/bin/python3 -c import time,sys;print('w3orphanmarker',…
```

W2's gate records that run as `failed` (exit 124) and **releases the flock**, while the orphan keeps
running — for a collection task that means an unrecorded process that can still spend quota and
write rows, and the freed lock lets a second copy start. W3 declares jobs that go through exactly
this path, so the kill has to reach the whole process group. Fix is in scope and named in the
verification contract (R5): `start_new_session=True` on the spawn plus `os.killpg(..., SIGKILL)` on
timeout. The known Bocha/Serper worktree-root key-lookup defect is **recorded only, not fixed**.

**Verdict: no degradation is needed.** The plan's fallback ("保留 CLI 导入 + 简化状态页") is not
invoked.

## 3. What the legacy chains need, per W3 requirement

| Requirement | Needs PG? | Note |
|---|---|---|
| Upload: hash dedup / advisory lock / dry-run / staging | no | dedup can be served from a serving-side ledger; dry-run parse (`import_company_xlsx`, `import_patent_xlsx`) is a pure local parse |
| Upload: import into the domain store + enrichment batch scheduling | **yes** | `pipeline_run`, `import_batch`, `company_snapshot`, `company_enrichment_batch` are all Postgres |
| Seed: `professor_seed` CRUD | **yes** | table lives in PG |
| Seed: trigger run + run polling | **yes** | `run_single_seed` + `pipeline_run` |

So §2 principle 4 applies literally: with no PG the surface must answer 503 and hide the page
entries, and must not take the service down.
