# Verification: add-admin-config-center (W1)

Layered evidence per AGENTS.md §7 (user rule 2026-08-18). Contract:
`.agents/runs/admin-config-center-w1/verification-contract.md`.

Worktree `admin-config-center` / branch `feat/admin-config-center`, based on the live serving
commit `f961eece` (`codex/canonical-v2-s12a-ready`). The live 18188 service was never restarted or
reconfigured; `.worktrees/canonical-v2-s11-consolidation` and `.worktrees/data-rebuild` were not
touched.

---

## ① New tests written this slice — 45 cases, all passing

Command (all three files, from `apps/admin-console`):

```
uv run python -m pytest tests/test_managed_settings_store.py \
  tests/test_canonical_v2_admin_config_api.py \
  tests/test_canonical_v2_admin_status_repair.py -q -p no:randomly
→ 45 passed
```

| File | Cases | What it locks | Fixture source |
|---|---|---|---|
| `tests/test_managed_settings_store.py` | 26 | schema defaults with a missing file; partial-file fill; corrupt-file fallback to defaults; whitelist rejection (`unknown_toggle`, `index_root`, …); credential-shaped rejection (`api_key`, `token`, `database_url`, `credential_file`) including a pre-existing poisoned file being ignored; atomic write via `os.replace` with no temp residue and a directory listing of exactly `settings.json` + `audit.jsonl`; audit before/after/operator/changed + `+00:00` timestamp; append-only audit; no-op patch writes nothing; env-over-file precedence with per-field `source` and `editable=False`; env type mismatch rejection; ill-typed value rejection (`not-a-url`, URL with embedded credentials, relative path, out-of-range ints); restart reads the patched value; `CANONICAL_V2_MANAGED_SETTINGS` override; committed template validates against the schema | constructed scenarios, real temp directories, `os.replace` observation, in-process environment mappings |
| `tests/test_canonical_v2_admin_config_api.py` | 15 | `GET /config` defaults + `source`/`editable`; `GET→PATCH→GET` round trip with on-disk persistence and audit operator `operator-li`; anonymous operator recorded as `anonymous`; 5 rejection cases → 422 with a real store file never created and no audit record; `system-status` 200 with per-block degradation (pack/index/operations unavailable, disk ok, collection-history reason names `pipeline_run`); runtime-manifest path preferred when a runtime is installed; health-check never echoes key material (sentinel generated in-process, only 4-character suffixes allowed) and `reachable` values reflect the injected probe; unconfigured providers return 200 with `configured: false`; `/admin` served with all three endpoint paths + `立即检查`; `/logs` links to `admin`; env override reported through the API | real FastAPI route graph (`backend.main:app`) + `TestClient`; constructed provider/probe doubles; no mock of the code under test |
| `tests/test_canonical_v2_admin_status_repair.py` | 4 | the reported defect: a `gap_operations` object with only `record`/`apply_remediation` (`_EphemeralKnowledgeGapFeedback` shape) yields 200 with `gap_summary.state="unavailable"` and a reason that names the missing capability, while release id / manifest version / manifest sha / per-domain counts stay present; an operations-capable object yields 200 with `gap_summary.state="available"` and the page payload; a page that fails exact validation degrades instead of raising; a genuine storage exception still surfaces as 500 | constructed scenario mirroring the live pack-mode composition |

No test fixture, assertion message, or captured artifact contains real credential material; the only
credential-derived values in any artifact are the provider-key suffixes that the acceptance
criteria explicitly require.

## ② Pre-existing regression suite — unchanged failure set

```
# before (HEAD f961eece, no W1 changes)
uv run python -m pytest -q -p no:randomly --tb=no -rf
→ 96 failed, 979 passed, 29 skipped, 122 errors in 192.17s

# after (W1 changes applied)
uv run python -m pytest -q -p no:randomly --tb=no -rf
→ 96 failed, 1024 passed, 29 skipped, 122 errors in 183.16s
```

Set comparison over the reported `FAILED` lines:

```
comm -13 failures-before.txt failures-after.txt  → 0 lines   (no new failure)
comm -23 failures-before.txt failures-after.txt  → 0 lines   (no failure removed by accident)
```

The `+45 passed` is exactly the new tests. Artifacts: `full-suite-before.txt`,
`full-suite-after.txt`, `failures-before.txt`, `failures-after.txt`, `failures-new.txt` (empty),
`failures-delta-removed.txt` (empty).

**Pre-existing reds, named honestly** (confirmed pre-existing by `git stash`-ing the two modified
source files and re-running):

- `tests/test_main_milvus_env.py::test_main_sets_milvus_real_client_env_when_absent` — the V2 shell
  does not set `MILVUS_USE_REAL_CLIENT` (legacy SPA-era expectation).
- `tests/test_canonical_v2_consumer_migration.py::test_s9j_static_chat_uses_typed_public_copy` —
  static chat copy drift.
- `tests/test_canonical_v2_consumer_migration.py::test_s11b_candidate_app_exposes_only_release_bound_v2_consumers`
  — factory-signature assertion (`_has_keyword_only_runtime_parameter`).
- `tests/test_canonical_v2_review_http.py` — 17 errors from the review-app factory setup.
- The remaining ~90 failures / ~120 errors are environment-gated: they require a Postgres domain
  database (`DATABASE_URL_TEST`), which this shell does not set.

Note on the s11b failure: `git diff` over `backend/main.py` shows only an import, a
`shell.include_router(...)` line, and the `/admin` route — `create_canonical_v2_candidate_app`'s
signature is untouched. The failure reproduces with the W1 changes stashed.

## ③ Scratch-port real-interaction smoke (port 18288, never 18188)

Service: `uvicorn backend.main:app --host 127.0.0.1 --port 18288` with
`CANONICAL_V2_MANAGED_SETTINGS=/tmp/w1-scratch/managed/settings.json` plus the live sidecar
environment variables (`CANONICAL_V2_ACCESS_LOG_DB`, `CANONICAL_V2_CORRECTIONS_DB`,
`CANONICAL_V2_MANUAL_RECALL_DIR`, `CANONICAL_V2_SERVING_PACK`, `CANONICAL_V2_INDEX_ROOT`) read-only.
Server log: `scratch-18288-server.log`.

Status codes (real HTTP):

```
GET  /admin                                        -> 200
GET  /logs                                         -> 200
GET  /api/canonical-v2/admin/config                -> 200
PATCH/apis.../admin/config (unknown field)         -> 422
POST /api/canonical-v2/admin/providers/health-check-> 200
GET  /api/canonical-v2/admin/system-status         -> 200
GET  /api/canonical-v2/admin/status                -> 503  (no runtime installed on this bare shell; dependency-level, not 500)
GET  /api/canonical-v2/operations/gaps             -> 503  (same, pre-existing behaviour)
```

Config round trip: `PATCH {"collection":{"max_llm_calls_per_run":712},"paths":{"access_log_retention_days":45}}`
with `X-Remote-User: smoke-operator` → 200, `changed` lists both paths; the file lands at
`/tmp/w1-scratch/managed/settings.json` (mode 600) with `audit.jsonl` (mode 600) containing one
record whose `operator` is `smoke-operator` and whose `changed` matches. Illegal requests (unknown
key, credential-shaped key, wrong type) → 422 with the file byte-identical afterwards and no audit
growth; the sentinel secret `sk-smoke-secret-9931` appears 0 times in both the settings file and the
audit log (`grep -c` = 0).

`system-status` against the live artifacts (`scratch-system-status.json`):

```
pack:        ok   candidate-v2-20260819-r1  generated 2026-09-10T06:34:12Z  build 2026-09-07T15:56:13Z
record_counts: company 7089 · paper 24520 · patent 11504 · professor 3958
index_marker: ok  expected 8848197caaa665fa…  observed 8848197caaa665fa…  (match)  release candidate-v2-20260819-r1
freshness:   ok  per-domain record counts + pack build age 520608 s
collection_history: unavailable — "…pipeline_run history lives in the build/release database, not on the serving host"
operations:  corrections ok (0 active / 3 reverted / 2 added, latest 2026-08-03) ·
             access_log ok (960 sessions / 1599 turns, latest 2026-09-13T09:05Z) ·
             manual_recall ok (0 entries)
storage:     lookup ok (47071 lookup_document) · corrections ok · access_log ok ·
             pack ok (5 members) · index_root ok (milvus.db 1.0 GB, .milvus.db.lock present)
disk:        / 36.7 % used · /var/tmp 36.7 % · /md1 88.9 %   (retention_days = 45 from the scratch file)
```

Provider health check (`scratch-provider-health.json`), 0.85 s wall for 7 providers:

```
bocha            configured=True  suffix=9eb1  origin=file:.bocha_api_key   reachable=True   api.bochaai.com → HTTP 405
serper           configured=True  suffix=1e2e  origin=file:.serper_api_key  reachable=False  google.serper.dev → HTTP 403
deepseek         configured=True  suffix=2b92  origin=file:.deepseek_api_key reachable=True  api.deepseek.com → HTTP 200
dashscope        configured=False suffix=-     origin=-                     reachable=None   未配置（env 与 key 文件均缺失）
local_llm        configured=True  suffix=0204  origin=file:.sglang_api_key  reachable=None   (no probe URL)
openalex         configured=False … semantic_scholar configured=False …
```

Credential containment: the response body contains exactly four credential-derived tokens (the four
suffixes, each 4 characters) and no longer token; `grep -icE "sk-|api_key=[^&]|bearer [a-z0-9]"`
over `scratch-18288-server.log` returns 0.

## ④ Live 18188 read-only probe (before-state; no restart)

`live-18188-readonly-probe.txt`:

```
GET /api/canonical-v2/admin/status   -> 500  (Internal Server Error)
journalctl: AttributeError: '_EphemeralKnowledgeGapFeedback' object has no attribute 'list_for_admin'
GET /api/canonical-v2/admin/config        -> 404   (route does not exist on the deployed build)
GET /api/canonical-v2/admin/system-status -> 404
GET /admin                                -> 404
```

## ⑤ Real consumer

`scratch-cli-consumer.txt`:

```
uv run python scripts/settings_status.py --check-keys
→ managed settings : /tmp/w1-scratch/managed/settings.json (exists)
  [file]  collection.max_llm_calls_per_run    = 712
  [file]  paths.access_log_retention_days     = 45
  [deflt] collection.max_web_searches_per_run = 200  <- WEB_LANE_DAILY_QUOTA
  [deflt] … (all remaining fields with their env variable named)
  [key ]  bocha configured suffix=9eb1 origin=file:.bocha_api_key
  [key ]  dashscope MISSING suffix=---- origin=-
uv run python scripts/settings_status.py --require paths.access_log_retention_days   → exit 0
uv run python scripts/settings_status.py --require extraction_endpoints.llm_model    → exit 1
```

Against the repository default path (no scratch override) the same command reports
`config/managed/settings.json (defaults)` — i.e. a missing file is not an error.

## ⑥ Static checks

```
uv tool run ruff@0.8.0 check <9 changed/new files>  → All checks passed!
uv run ruff check <same>                            → All checks passed!
```

`ruff format --check` is **not** applied: the existing repository files (for example
`backend/main.py`, `backend/services/canonical_v2_chat.py`, `serving_pack_loader.py`) are already
unformatted under `ruff@0.8.0 format`, so running the formatter would produce a repo-wide diff
unrelated to this slice. Lint (the `just lint` gate) passes.

## ⑦ What is NOT verified

1. **The live 18188 restart.** The slice forbids restarting it, so the claim is limited to: the
   failure is reproduced from the live journal, the fix is proven by a test that reconstructs the
   exact live object shape, and the same code path returns 200 in the scratch service when a capable
   runtime is present. "18188 returns 200 today" is **not** claimed — it requires a future deploy.
2. **A full replay/retrieval gate run.** Not applicable by construction: no chat, retrieval, fusion,
   rerank, routing, prompt, citation, or serving-pack code was modified (`git diff --stat` covers
   `main.py`, `canonical_v2_admin.py::status()`, `logs.html`, `.gitignore` plus new files). This is a
   deliberate deviation from the "RAG-adjacent ⇒ replay" rule, justified by the zero-touch diff.
3. **`lookup.sqlite3` / `milvus.db` deep health.** Only `quick_check` + table counts + presence/size
   are read; the live Milvus file is held open by the serving process and is never opened here.
4. **Collection scheduling.** No collection cron exists yet (W6), so "last successful collection per
   domain" is reported as `unavailable` with a reason rather than verified as a number.
