# Design: add-admin-config-center

## 1. Context and decision summary

Authoritative plan: `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md`
§2 (principles), §3 (line A), §6 (W1 acceptance row), §7 (risks). The 2026-09-13 user decision
supersedes §3.3 where they differ:

| Plan §3.3 said | User decision (2026-09-13), implemented here |
|---|---|
| New serving-side SQLite `settings` table + audit table | **Managed configuration file** `config/managed/settings.json`, edited via web, read by services/scripts at startup |
| Config content = collection switches + quotas | **Endpoints, model tiers, key-file inventory, path variables (no plaintext secrets)** + system status panel |
| Build the page from the plan | **Dry run first, page second** — the page renders only fields the dry run proved necessary |

Decision log (this slice):

- **D-W1-1** Managed file, not a settings table. A file is inspectable, diffable, survives the
  "centre builds / site consumes" split, and needs no migration. Rejected: SQLite settings table
  (second source of truth beside env, opaque to ops, needs a migration on every field).
- **D-W1-2** Env wins, always. Every whitelist field that has an existing environment variable is
  resolved as `env > file > default` and the API reports which source won. Rejected: file-wins
  (would silently change serving behavior and invalidate frozen replay evidence).
- **D-W1-3** No serving-process re-wiring. The dry run (§2) showed the serving process needs no new
  input; re-wiring would change retrieval inputs and require re-running the replay gate. The one
  real consumer is an operator CLI (§5).
- **D-W1-4** Secrets never enter the managed file, the API response body, or the audit trail. Key
  material is reported as `configured: bool` plus a 4-character suffix.
- **D-W1-5** Repair `admin/status` by degrading, not by upgrading the ephemeral object. The
  ephemeral gap feedback is a build/serve artifact of `complete_candidate_runner.py`; teaching the
  admin console to accept a capability-less operations object keeps the repair inside the
  admin-console layer (the only layer this slice owns).

## 2. Dry-run inventory

Evidence: `.agents/runs/admin-config-center-w1/dry-run-inventory.json` (probe executed 2026-09-14
against the live process `PID 1992450`, the live serving root, the live 18188 index root, and the
repo). "Read at" cites `file:line`. "Effect" = when a change takes effect.

### 2.1 Serving-line environment variables (observed in live `/proc/1992450/environ`)

| Name | Read at | Effect | Sensitive | Live value |
|---|---|---|---|---|
| `CHAT_LLM_PROFILE` | `canonical_v2/knowledge_serving_isolated.py:1907,5777,5875`, `llm_judgments.py:304`, `canonical_v2_query_interpreter.py:170` | first use per process | no | `deepseekv4flash` |
| `CHAT_CONTEXTUAL_INTERPRETATION` | `canonical_v2_query_interpreter.py:72` | per turn | no | `on` |
| `CANONICAL_V2_LEXICAL_INDEX` | `knowledge_read_isolated.py:160,7169` | startup (lane on/off) | no | `0` |
| `CANONICAL_V2_LEXICAL_INDEX_ROOT` | `knowledge_read_isolated.py:161,7173` | startup | no | unset |
| `CANONICAL_V2_ACCESS_LOG_DB` | `s12a/complete_candidate_runner.py:479` | startup | no | `/var/tmp/mirothinker-canonical-v2-s12f/access-logs.sqlite3` |
| `CANONICAL_V2_CORRECTIONS_DB` | `complete_candidate_runner.py:504` | startup | no | `/var/tmp/mirothinker-canonical-v2-s12f/corrections.sqlite3` |
| `CANONICAL_V2_MANUAL_RECALL_DIR` | `complete_candidate_runner.py:529` | startup | no | `/var/tmp/mirothinker-data-v2/manual-recall-v1` |
| `CANONICAL_V2_TURN_DEBUG_DIR` | `services/canonical_v2_chat.py:1328`, `knowledge_read.py:49` | per turn | no | `.agents/runs/close-workbook-gaps/turn-debug` |
| `CANONICAL_V2_LEXICAL_INDEX_DEBUG` | `knowledge_read_isolated.py:7332` | per call | no | unset |
| `CANONICAL_V2_RERANK_BASE_URL` / `_MODEL` / `_API_KEY` / `_API_KEY_FILE` / `_TIMEOUT_SECONDS` / `_MAX_DOCUMENTS` / `_DEBUG` | `canonical_v2/rerank_client.py:74,89,105,108,226,231,235` | startup | key yes | all unset (lane parked: `~/.config/systemd/user/canonical-v2-backend.service.d/rerank.conf.pending`) |
| `CHAT_LLM_TIMEOUT_SECONDS` | `knowledge_serving_isolated.py:5788,5807,5884` | per call | no | unset (default 30) |
| `CHAT_LLM_SYNTHESIS` | `api/chat.py:4672` | per turn | no | unset (default on) |
| `CHAT_AUGMENT_WEB` | `api/chat.py:3336,3433` | per turn | no | unset (default 1) |
| `CHAT_QUERY_CLASSIFIER` | `api/chat.py:794` | per turn | no | unset (default on) |
| `CHAT_SYNTHESIS_TIMEOUT` | `api/chat.py:87` | process start | no | unset (default 60.0) |
| `CHAT_E_WEB_FALLBACK_THRESHOLD` | `backend/deps.py:49` | per turn | no | unset |
| `TURN_TRACE_DIR` | `services/canonical_v2_turn_trace.py:320`, `web_lane_resilience.py:52` | per turn | no | unset (default `.agents/runs/.../turn-trace`) |
| `WEB_LANE_DAILY_QUOTA` | `web_lane_resilience.py:287` | per web call | no | unset (no cap) |
| `DATABASE_URL` / `DATABASE_URL_TEST` | `api/chat.py:1885`, `api/seeds.py:278`, `backend/deps.py:68` (legacy/SPA surface only) | per call | **yes** | unset on the V2 serving line |
| `CANONICAL_V2_DATABASE_URL`, `CANONICAL_V2_EXPECTED_DATABASE`, `CANONICAL_V2_TARGET_KIND`, `CANONICAL_V2_BACKUP_GATE_ROOT` | `backend/canonical_v2_deps.py:33` | per call (lazy) | **yes** | **unset** → `/api/canonical-v2/operations/gaps` answers 503 on the live line |

### 2.2 Provider credentials (never plaintext in UI/logs; suffix only)

| Provider | Resolution order | Read at | Live observation |
|---|---|---|---|
| Bocha | `BOCHA_API_KEY` env → repo-root `.bocha_api_key` | `providers/bocha_search.py:11,61` | env unset; key file present at **main repo root only** (36 B) |
| Serper | `SERPER_API_KEY` env → `.serper_api_key` | `providers/web_search.py:13,55` | env unset; file present (41 B, main repo root only) |
| Local/SGLang LLM | `<profile>_API_KEY` env → `LOCAL_LLM_API_KEY` → `.sglang_api_key` | `professor/llm_profiles.py:11-16,50-61` | env unset; `.sglang_api_key` present (27 B) |
| DeepSeek (active profile `deepseekv4flash`) | `DEEPSEEK_API_KEY` env → `.deepseek_api_key` | `llm_profiles.py:75-83,111-125` | env unset; `.deepseek_api_key` present (35 B, mode 600) |
| DashScope (online lane of `gemma4`/`qwen35`/`mirothinker`) | `DASHSCOPE_API_KEY` env → `.dashscope_api_key` | `llm_profiles.py:90-95` | env unset; **no key file** → online lane of those profiles unusable |
| Crossref | `CROSSREF_USER_AGENT` env | `providers/crossref.py` | unset (default UA) |
| OpenAlex / Semantic Scholar | `OPENALEX_API_KEY`/`OPENALEX_KEY`; `SEMANTIC_SCHOLAR_API_KEY`/`S2_API_KEY` | `providers/openalex.py:12,71`, `semantic_scholar.py:5-19` | env unset, no key files → keyless mode |
| Rerank (`qwen3-reranker-8b`) | `CANONICAL_V2_RERANK_*` (serving module) / `.sglang_api_key` (domain module `providers/rerank.py:52`) | as §2.1 | unset; lane disabled |

**Key-file resolution caveat (dry run finding).** `providers/bocha_search.py` and
`providers/web_search.py` search the *import path* ancestors plus `cwd` ancestors; `llm_profiles.py`
additionally walks above the checkout root. The worktree checkout
`.worktrees/admin-config-center` has **no** key files, so a process started from the worktree
resolves keys only because `llm_profiles.py` walks to `/home/longxiang/MiroThinker`. The Bocha and
Serper readers do **not** walk above the checkout root — a worktree-launched collection script would
see an unconfigured Serper/Bocha key. Recorded here as an operational hazard for W6; not fixed in
this slice (fixing it means touching provider resolution, out of scope).

### 2.3 LLM / embedding / rerank tiers (hard-coded constants + overrides)

| Tier | Constant | Override | Notes |
|---|---|---|---|
| Professor / collection LLM profiles | `professor/llm_profiles.py:76` `_LLM_PROFILES` (5 profiles: `gemma4`, `qwen35`, `mirothinker`, `ark`, `deepseekv4flash`, `deepseekv4lite`) | `LLM_PROFILE`, per-profile `*_API_KEY` | profile table hard-钉; per-profile `LOCAL_LLM_BASE_URL`/`LOCAL_LLM_MODEL`, `ONLINE_LLM_BASE_URL`/`ONLINE_LLM_MODEL` when `apply_endpoint_env_overrides=True` (`llm_profiles.py:246-262`) |
| Answer LLM (serving) | same table, profile from `CHAT_LLM_PROFILE` | as above | the answer/synthesis + query-rewrite + judge paths all read the one profile |
| Embedding | pack manifest `embedding_model_id` = `Qwen/Qwen3-Embedding-8B` | none | identity is hash-bound by the serving pack; **not configurable** |
| Rerank (serving lane) | `rerank_client.DEFAULT_MODEL = qwen3-reranker-8b`, `DEFAULT_TIMEOUT_SECONDS = 3.0`, `DEFAULT_MAX_DOCUMENTS = 128` | `CANONICAL_V2_RERANK_*` | lane off (`rerank.conf.pending`) |
| Rerank (domain/legacy) | `providers/rerank.py:13-15` `_DEFAULT_RERANK_URL=http://100.64.0.27:18006/v1`, model `qwen3-reranker-8b`, timeout 60 | constructor args only | pre-canonical era |

### 2.4 Paths, storage, and retention

| Item | Source | Live value | Health probe 2026-09-14 |
|---|---|---|---|
| Serving pack dir | `--serving-pack` CLI (unit file) / `CANONICAL_V2_SERVING_PACK` env (`complete_candidate_runner.py:239`) | `/var/tmp/mirothinker-data-v2/serving-pack-run14-sealed` | `manifest.json` readable; `release_id=candidate-v2-20260819-r1`, `generated_at=2026-09-10T06:34:12Z`, `embedding_model_id=Qwen/Qwen3-Embedding-8B`; small-member hashes match the registry |
| Live index root | `--index-root` CLI | `/var/tmp/mirothinker-data-v2/index-v1` | marker sha256 `8848197c…97c8` **equals** the value passed to the live process → marker check passes |
| Pack `lookup.sqlite3` | pack manifest file registry | 665,395,200 B | `quick_check=ok`; `lookup_document`=47,071, `lookup_manifest`=7, `build_metadata`=2, `build_receipt`=1 |
| Live `index-v1/lookup.sqlite3` | index root | 665,395,200 B | `quick_check=ok`, same table counts |
| `index-v1/milvus.db` | index root | 1,078,865,920 B | present; opened by the running milvus-lite child (lock held) |
| `index-v1/vector_matrix.npz` | index root | 1,676,917,131 B | present |
| `relationships.json` | pack | 3,357,118,726 B | present (hash check skipped: >64 MB) |
| access log | `CANONICAL_V2_ACCESS_LOG_DB` | 5,550,080 B | `quick_check=ok`; sessions=960, turns=1,599; `schema_version=canonical-v2-access-log-v1` |
| corrections | `CANONICAL_V2_CORRECTIONS_DB` | 4,096 B (+177 KB WAL) | `quick_check=ok`; `field_corrections`=3, `added_records`=2; `schema_version=canonical-v2-corrections-v1` |
| manual recall | `CANONICAL_V2_MANUAL_RECALL_DIR` | dir exists, **0 entries** today (the older `s12f/manual-recall-v1/manual-recall.json`, 279 KB, belongs to the previous serving root) | read-only listing |
| Log retention | `deploy/purge-access-logs.sh:6` `RETENTION_DAYS=90`, cron 03:41 | 90 days | not exposed anywhere before this slice |
| Backup | cron 03:17 `deploy/backup-canonical-v2.sh` | daily | — |
| Disk | `/` (contains `/var/tmp`) | 1.89 TB total, 1.20 TB free (36.7 % used) | `/md1`: 19.1 TB total, 2.13 TB free (88.9 % used) |

### 2.5 Collection scripts (plan §5.3) — present, but **not scheduled**

All seven scripts exist under `apps/miroflow-agent/scripts/`: `run_company_news_ingest.py`,
`run_company_official_product_capture.py`, `run_paper_search_backfill.py`,
`run_paper_summary_zh_backfill.py`, `run_paper_doi_verify.py`, `run_profile_bio_rescrape.py`,
`run_homepage_paper_ingest.py`.

The **only** cron entries on this host are daily backup (03:17), access-log purge (03:41) and an
unrelated GitHub backup. There is **no** collection cron and **no** `deploy/cron/` declaration file
yet (W6 scope). Consequence for this slice: the "per-domain last successful collection" panel has no
scheduled producer to read.

### 2.6 Dry-run findings that changed the design

1. **`pipeline_run` is not reachable at serving time.** The plan (§3.2a) expected freshness from the
   latest successful `pipeline_run` row. `pipeline_run` exists only in the build/release Postgres
   (`alembic/versions/V001_init_source_layer.py`); the serving database
   (`miroflow_candidate_v2_20260819_r1`, the one the live process points at) has no such table, and
   **the live process has no `CANONICAL_V2_DATABASE_URL` at all**. Per-domain freshness therefore
   has to be derived from artifacts that exist on the serving host: the pack's `build_manifest`
   timestamp, the per-domain record counts, and the operational stores (corrections / added records
   / manual recall / access log) that *do* carry per-domain timestamps. The API reports the
   `pipeline_run` view as `unavailable` with a reason, never as a fabricated number.
2. **The `admin/status` 500 is a real, still-live defect** and its cause is narrower than
   "operations environment not configured" (`deploy/README.md:145`): the pack-mode composition
   supplies the ephemeral in-process gap feedback, which has no `list_for_admin`.
3. **A new serving-side SQLite settings store is unnecessary.** The dry run surfaced no serving knob
   that is both non-sensitive and safe to change from a web form; the operational knobs that *are*
   safe (domain switches, per-run quotas, collection window) have no consumer yet, so the file is
   designed for the W6 consumer and one CLI consumer now.
4. **"Endpoints / model tiers" is a read-only concern, not an editable one.** Endpoints are
   pinned per profile in code and hash-bound where they matter (embedding identity). The whitelist
   therefore exposes a *read-only* endpoint view plus a single editable "extraction endpoint"
   group for collection-time use; serving-side endpoint editing is explicitly rejected.
5. **Fields the plan did not name but the panel needs**: the marker-hash comparison value, the
   pack's per-domain record counts, the access-log/corrections/manual-recall row counts, the
   retention days, and the `CANONICAL_V2_DATABASE_URL`-unset degradation marker.
6. **Fields the plan implied but are not needed**: a pack *version* string distinct from
   `release_id` (the manifest only has `pack_id`/`release_id`/`schema_version`); a "keepwarm/会话缓存
   状态" field (the keepwarm cycle is a runner-factory argument, no runtime state exposed); a
   serving-pack path editor (the path is a process argv pin; editing it from the web cannot affect
   the running process and would be a second source of truth).

## 3. Managed configuration contract

### 3.1 File and location

- Default path: `<repo root>/config/managed/settings.json` (repo root = three parents above
  `apps/miroflow-agent/src/data_agents/canonical_v2/managed_config.py`, i.e. the same convention
  `llm_profiles.py` uses).
- Override: `CANONICAL_V2_MANAGED_SETTINGS` (admin console also accepts this name; tests and
  scratch runs point it at a temp dir).
- Missing file, missing keys, or an unreadable file ⇒ defaults (never an error).
- The path is git-ignored runtime state. The schema module and the committed template
  `config/managed/settings.example.json` are the versioned artifacts.

### 3.2 Whitelist schema (all non-sensitive; `extra="forbid"`)

```jsonc
{
  "schema_version": 1,
  "collection": {
    "enabled": { "company": true, "paper": true, "patent": true, "professor": true },
    "max_web_searches_per_run": 200,   // 0..10000
    "max_llm_calls_per_run": 500,      // 0..100000
    "window_start_hour_utc": 17,       // 0..23  (01:00–06:00 Asia/Shanghai)
    "window_end_hour_utc": 22          // 0..23, must exceed start (no overnight wrap)
  },
  "extraction_endpoints": {
    "llm_base_url": null,              // http(s) URL or null
    "llm_model": null,                 // 1..200 chars or null
    "embedding_base_url": null,
    "embedding_model": null,
    "rerank_base_url": null,
    "rerank_model": null
  },
  "paths": {
    "serving_pack_dir": null,          // absolute path or null
    "access_log_retention_days": 90    // 1..3650
  }
}
```

Explicitly **excluded** (and why): every `*_API_KEY` / `*_API_KEY_FILE` (secret), every
`DATABASE_URL*` (secret-bearing DSN), `CANONICAL_V2_BACKUP_GATE_ROOT` and all `CANONICAL_V2_S11B_*`
(build-time release gates whose mutation would weaken a fail-closed check), serving-pack / index
roots and SQLite paths (process argv pins; a web edit cannot affect a running process and would
create a second source of truth), `.milvus.db.lock` paths, and the retrieval-policy switches
(`CANONICAL_V2_LEXICAL_INDEX*`) frozen by accepted replay evidence.

### 3.3 Resolution precedence and override reporting

For each field that duplicates an environment variable the effective value is
`env > file > default`, and the API returns the winner:

```
collection.max_web_searches_per_run  ← WEB_LANE_DAILY_QUOTA            (env wins)
collection.max_llm_calls_per_run     ← (no env)                        (file wins)
paths.access_log_retention_days      ← CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS (env wins)
extraction_endpoints.llm_base_url    ← LOCAL_LLM_BASE_URL              (env wins)
extraction_endpoints.llm_model       ← LOCAL_LLM_MODEL                 (env wins)
extraction_endpoints.rerank_base_url ← CANONICAL_V2_RERANK_BASE_URL    (env wins)
extraction_endpoints.rerank_model    ← CANONICAL_V2_RERANK_MODEL       (env wins)
paths.serving_pack_dir               ← CANONICAL_V2_SERVING_PACK       (env wins)
```

The page renders "由 env 覆盖" for any field whose source is `env` and disables its input.

### 3.4 Write path

1. `PATCH` body is validated by the Pydantic model; unknown keys raise 422 (no partial writes).
2. Serialisation is canonical (`sort_keys=True`, 2-space indent, trailing newline).
3. Atomic write: `tempfile.mkstemp` in the target directory → `os.replace` onto the target.
4. Audit: one JSON object per line appended to `config/managed/audit.jsonl` under an exclusive
   `fcntl.flock`, containing `at`, `operator` (from `X-Remote-User`, else `anonymous`), `action`,
   `before`, `after`, `changed` (sorted key paths). The audit file is never rewritten.

## 4. API surface (all under `/api/canonical-v2/admin`)

| Method + path | Response | Notes |
|---|---|---|
| `GET /config` | `{schema_version, settings, effective, fields[]}` | `fields[]` carries `path`, `type`, `env_var`, `source`, `editable`, `label` |
| `PATCH /config` | updated `GET` payload + `changed[]` | 422 on unknown/ill-typed field; 503 if the store is unwritable |
| `GET /system-status` | pack / index-marker / counts / ops / storage / disk blocks | every block is independently degradable with `state: ok\|unavailable` |
| `POST /providers/health-check` | per-provider `{configured, suffix4, reachable, detail}` | bounded probe, no plaintext; `configured` may be true while `reachable` is false |
| `GET /status` (existing) | 200 always | `gap_summary` becomes `{state:"available", page:{...}}` or `{state:"unavailable", reason:"..."}` |

`system-status` blocks:

- `pack`: `release_id`, `pack_id`, `schema_version`, `generated_at`, `build_created_at`,
  `manifest_version`, `build_run_id`, `record_counts` (per published projection), `manifest_sha256`
  from `release_verification`, `file_registry`.
- `index_marker`: expected sha256 (process argv / manifest), observed sha256 of the live marker,
  `matches` bool, `target_kind`, `release_id`.
- `freshness`: canonical `as_of`, pack `build_created_at`, per-domain `record_count`, and a
  `collection_history` sub-block that is `unavailable` with an explicit reason when the build-time
  `pipeline_run` source is absent.
- `operations`: corrections (active/reverted, per domain, latest `created_at`), added records
  (per domain), manual-recall entries, access-log sessions/turns and latest `last_active_at`.
- `storage`: SQLite `quick_check` + tables/counts + file size for the live lookup/corrections/
  access-log databases, plus `milvus_db` presence/size.
- `disk`: free/total/used-percent for `/`, `/var/tmp` and `/md1`.
- `config`: file path, whether it exists, `schema_version`.

## 5. The real consumer

`apps/miroflow-agent/scripts/settings_status.py` — `uv run python scripts/settings_status.py
[--json] [--check-keys]`:

- loads the managed file through the shared loader (same defaults, same env precedence);
- prints one row per effective field with `source = env|file|default`;
- `--check-keys` prints provider key presence + suffix only (never plaintext);
- exit code 1 when a requested `--require KEY` is missing (usable from a future W6 cron wrapper).

The serving process is deliberately **not** re-wired (D-W1-3). The env-priority rule means that
even a future serving-side consumer cannot silently change behavior that env already pins.

## 6. Verification surface

| Layer | Artifact |
|---|---|
| Unit | `apps/admin-console/tests/test_managed_settings_store.py` — schema defaults, whitelist rejection, secret rejection, atomic write (no temp residue, `os.replace` used), audit append, env precedence |
| API contract | `apps/admin-console/tests/test_canonical_v2_admin_config_api.py` — `GET→PATCH→GET` round trip, 422 on unknown field / non-whitelisted key / secret key, `system-status` 200 with degraded blocks, `providers/health-check` shape + no plaintext |
| Regression (the reported defect) | `apps/admin-console/tests/test_canonical_v2_admin_status_repair.py` — a runtime whose `gap_operations` lacks `list_for_admin` returns 200 with `gap_summary.state="unavailable"`; an operations-capable runtime still returns the page payload |
| Existing suite | `apps/admin-console` full `pytest` (baseline recorded before the change) |
| Real interaction | scratch service on **port 18288** with a scratch config dir: page 200, API round trip, 4xx on illegal input, no key plaintext in any response body |
| Consumer | `settings_status.py` run against the repo and against a scratch config dir |

Oracle strength: the API tests assert response bodies and status codes over the real FastAPI route
graph (not mocks of it); the status-repair test reproduces the live `AttributeError` shape
(a capability-less operations object) as a constructed scenario; the scratch smoke is a real HTTP
interaction with the assembled app.

## 7. Rollback

Delete the router include + `/admin` route + `admin.html` and revert the `status()` degradation:
the serving line falls back to today's behavior (status 500, no config page). No data migration, no
schema change, no touch of the serving pack, index, or the 18188 service. `config/managed/` is
ignored runtime state and can be deleted independently.

## 8. Human doc cross-link

`docs/plans/2026-09-14-admin-config-center-dry-run.md` (dry-run findings, Chinese) and
`docs/plans/2026-09-14-admin-config-center-log.md` (append-only execution log, Chinese).
