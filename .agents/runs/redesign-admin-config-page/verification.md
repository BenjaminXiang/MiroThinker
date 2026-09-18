# Verification: redesign-admin-config-page

Slice: tasks A1–A4, B1–B8, C1, C2 (C3 — live cutover on 18188 + rollback drill — is
the parent session's step and is deliberately untouched here).

Worktree `/home/longxiang/MiroThinker/.worktrees/admin-config-redesign`, branch
`feat/admin-config-redesign` off `0af01f33`. All commands ran in
`apps/admin-console` unless a path says otherwise. Nothing in this slice touched
port 18188, the live managed settings/secrets files, or another worktree: the
scratch smoke ran on **port 18296** against `/tmp/admin-config-smoke/managed/`
(settings.json + secrets.json + admin-auth store), and 18188 was checked only
with `ss -ltnp` to confirm it was untouched.

## 1. RED (before implementation)

```
$ uv run pytest -q -p no:randomly -p no:cacheprovider \
    tests/test_managed_config_catalogue.py tests/test_admin_config_single_channel.py
ImportError: cannot import name 'FIELD_CATALOG' from
  'src.data_agents.canonical_v2.managed_config'
ERROR tests/test_managed_config_catalogue.py
ERROR tests/test_admin_config_single_channel.py            (2 collection errors)

$ uv run pytest -q -p no:randomly -p no:cacheprovider tests/test_managed_settings_store.py
FAILED test_null_clears_a_bool_override_back_to_the_default
FAILED test_null_clears_text_and_non_nullable_numeric_overrides
FAILED test_null_clears_one_domain_toggle_and_keeps_the_others
FAILED test_diff_patch_writes_only_the_changed_keys
FAILED test_patch_preserves_an_operators_hand_written_file
FAILED test_a_corrupt_file_is_replaced_by_the_patch_alone
6 failed, 28 passed
```

The six RED store tests failed for the designed reason: the patch wrote the whole
defaulted document (`{'collection': … 'schema_version': 1 …}`) instead of the
operator's keys, and a `null` on a non-nullable field was a validation error.

## 2. New tests written this slice (layer ①)

30 new tests, all fixture-driven from `tmp_path` settings files + the real FastAPI
route graph (`backend.main:app` with `authorized_client`); no test reads or writes
the live state directory, and no secret value is printed.

| file | new tests | locks |
|---|---|---|
| `tests/test_managed_config_catalogue.py` | 11 | every whitelisted path has a row and no row is an orphan (both directions fail-closed, offenders named); every row carries label/kind/group/order/consumer; int/float rows carry bounds; `(group, order)` unique; endpoint rows name their connection + `test_arg` and nothing else does; each model connection has exactly one `base_url` + one `model` row; row defaults come from `ManagedSettings()`; `/config`'s `fields` carry every catalogue column; payload stays free of credential material |
| `tests/test_managed_settings_store.py` | +8 | `null` clears a bool override (value back to default, `source=default`, key leaves the file); `null` clears text and a **non-nullable** int; `null` clears one nested domain toggle and leaves the others; clearing an unset field is a no-write/no-audit no-op; a two-path diff patch writes exactly those keys and keeps a second patch's untouched override; re-sending the same patch writes nothing (bytes + audit identical); a hand-written partial file survives a patch; a corrupt file is replaced by the patch alone |
| `tests/test_admin_config_single_channel.py` | 4 | the page (html + js) holds no `extraction_endpoints` knowledge and no endpoint field-name literal; no module hand-builds an `"extraction_endpoints": {…}` payload; `/config` is the only PATCH writer in the admin config router; every endpoint path is owned by the connection group with a connection key |
| `tests/test_admin_config_page_shell.py` | 7 | shell loads `admin.css`/`admin.js` and keeps the four card containers + snapshot containers; banner + per-card save buttons exist; `FIELD_SPECS` / `collectPatch` / `providerTable` / `healthCheck` / `立即检查` / `statusTiles` / `configForm` / `secretsTable` are gone from page, script and style; the four API calls live in `admin.js`; banner markers (`项未保存`, `需重启生效`, restart command, clipboard) present; three-state vocabulary (`默认/启用/停用`, `回到默认`) present |

Two pre-existing page-marker tests were updated (B8), not deleted:
`test_canonical_v2_admin_config_api.py::test_admin_page_is_served` (now asserts the
shell assets and that `立即检查` is gone; the `providers/health-check` API itself is
still covered by `test_health_check_never_echoes_key_material`) and
`test_canonical_v2_admin_secrets_api.py::test_admin_page_renders_the_credentials_card`
(now asserts the connection-card containers and the secrets/connections-test calls
in `admin.js`).

```
$ uv run pytest -q -p no:randomly -p no:cacheprovider \
    tests/test_admin_config_page_shell.py tests/test_admin_config_single_channel.py \
    tests/test_managed_config_catalogue.py tests/test_managed_settings_store.py \
    tests/test_canonical_v2_admin_config_api.py tests/test_canonical_v2_admin_secrets_api.py \
    tests/test_admin_console_shell.py tests/test_admin_gate.py tests/test_managed_runtime_bootstrap.py
116 passed in 2.94s
```

## 3. Pre-existing suites re-run (layer ②)

Full `apps/admin-console` suite, same command and environment before and after the
slice (`uv run pytest -q -p no:randomly -p no:cacheprovider`):

| run | result |
|---|---|
| before (commit `0af01f33`) | `25 failed, 1316 passed, 30 skipped, 105 errors in 191.27s` |
| after (frozen slice tip `3cef4563`) | `25 failed, 1346 passed, 30 skipped, 105 errors in 183.30s` |

The 30 extra passes are exactly the 30 new tests. The failure sets are
byte-identical:

```
$ grep -E "^(FAILED|ERROR)" admin_suite_before.txt | sort > before_failures.txt
$ grep -E "^(FAILED|ERROR)" admin_suite_after.txt  | sort > after_failures.txt
$ comm -23 before_failures.txt after_failures.txt   # only-before  → (empty)
$ comm -13 before_failures.txt after_failures.txt   # only-after   → (empty)
```

Both lists (130 lines each) are kept beside this file as
`full-suite-failures-before.txt` / `full-suite-failures-after.txt`. The
pre-existing failures are professor/dashboard/chat-preview/read-turn-trace tests
that need data or PostgreSQL that this checkout does not have; the 105 errors are
the `Refusing to run tests against a real-data database` / seeds-store guards.

## 4. Scratch-port smoke (layer ③, acceptance A1–A6)

Server: `uv run python -m uvicorn backend.main:app --host 127.0.0.1 --port 18296`
with `CANONICAL_V2_MANAGED_SETTINGS` / `CANONICAL_V2_MANAGED_SECRETS` /
`CANONICAL_V2_ADMIN_AUTH_DB` / `CANONICAL_V2_ADMIN_AUTH_KEY` all pointing at
`/tmp/admin-config-smoke/`. Browser: `agent-browser` (Chromium), signed in through
`/main`. Full transcript: `scratch-smoke-transcript.txt`.

**A1 — adding a catalogue row makes the field appear with no client change.**
A temporary `collection.beta_quota: int = Field(default=7, ge=0, le=100)` plus one
`FieldSpec` row was injected into `managed_config.py` (nothing else changed —
`git status --short` showed only that file), the scratch server was restarted:

```
$ curl … /api/canonical-v2/admin/config | …
fields: 24
collection.beta_quota → {'label': '临时验收字段（beta 配额）', 'kind': 'int', 'group': 'collection',
                         'order': 30, 'min': 0, 'max': 100, 'step': 1, 'value': 7, 'source': 'default'}
$ agent-browser eval "…"
{"collection_fields":9,"new_field":{"label":"临时验收字段（beta 配额）… 默认：7","value":"7","min":"0","max":"100","step":"1"}}
$ agent-browser click "#save-collection"
"已保存 1 项：collection.beta_quota。systemctl --user restart canonical-v2-backend 后生效"
settings.json: {"collection": {"beta_quota": 42}, "paths": {"access_log_retention_days": 45}}
```

The temporary field was then removed (`git checkout -- managed_config.py`), the
stray key dropped from the scratch file, the server restarted, and the page went
back to 8 collection fields with `beta_quota_present: false`. `git status --short`
is clean.

**A2 — save writes only the dirty keys; clear returns to `source=default`.**
From the transcript (card 3):

```
### A2 · 保存只写脏键（card 3 保留天数 45，rerank 端点未保存保持脏）
"banner=1 项未保存 · 已保存的改动需重启生效"
settings.json: {"extraction_endpoints": {"rerank_base_url": "http://127.0.0.1:9"},
                "paths": {"access_log_retention_days": 45}}       ← exactly the two saved paths
### A2 · 清回默认（留空 → 显式 null → 键离开文件）
settings.json: {"paths": {"access_log_retention_days": 45}}       ← the rerank key left the file
extraction_endpoints.rerank_base_url → value=None source=default
### A2 · 幂等：同一改动重复保存 = no-op（不写文件、不写审计）
audit lines: 7 → 重复保存结果: 没有改动（只提交本卡修改过的字段）→ audit lines after re-send: 7
```

**A3 — booleans are three-state and 默认 clears the override.**
`serving.web_topical_floor`: select `默认 → 启用` wrote `true` (`source=file`), select
`启用 → 默认` removed the key (`value=None, source=default`). The nested toggle
`collection.enabled.company`: `false` → file `{"collection": {"enabled": {"company": false}}}`;
`默认` → key gone, `value=True source=default`. The switch to a *literal* bool in the
file (not a full-table dump) is visible in every transcript line above.

**A4 — `extraction_endpoints.*` has exactly one entry point.**

```
{"collection":8,"serving":6,"paths":2,"connections":"bocha=0,serper=0,rerank=2,embedding=2,llm=2"}
```

Six endpoint fields, all inside the three model connection cards; cards 1–3 render
none. `tests/test_admin_config_single_channel.py` locks the same rule at the source
level (no endpoint literal in `admin.js`, no second payload builder anywhere).

**A5 — test with unsaved values → save card → restart banner.**

```
"banner=1 项未保存"
连接卡内结果: 失败 · 2 ms · 传输失败（URLError） · 凭据来源 local-key:legacy-file:.sglang_api_key · 运行期未启用 · 本分钟剩余 5 次
未保存值不得落盘 → settings.json: (missing)
卡片 2 结果（同一个未保存值）: 失败 · 0 ms · 传输失败（URLError） …
保存本卡 → "端点/模型已保存 extraction_endpoints.rerank_base_url。systemctl --user restart canonical-v2-backend 后生效
              | banner=已保存的改动需重启生效 | 重启命令可见=true"
```

The probe really called `http://127.0.0.1:9` (transport failure, `called` true, one
minimal call, server-side rate limiter reporting "本分钟剩余 5 次") and the unsaved
value never reached the file. Both probe buttons work: the connection card's button
writes its own result, card 2's `[测试 Rerank 连通性]` writes
`#rerankTestResult` with the same unsaved value.

**A6 — cards 1 and 3 carry their own state, with no standalone status block.**

```
{"card1_freshness_rows":4,"card1_state_rows":3,"card3_storage_rows":6,
 "retention_preview":"保留期预览：保留最近 90 天，访问日志早于 2026-06-20 的部分会被清理",
 "standalone_status_block":0}
```

`#statusTiles / #status-card / #statusRaw` no longer exist; the pack/manifest tiles
stay on `/main` (not duplicated), and card 3's retention preview follows the unsaved
value (`保留最近 30 天 → 2026-08-19` while dirty, back to 90 after clearing).

**Save → restart stays effective end-to-end (no hot reload introduced).**

```
settings.json before restart: {"paths": {"access_log_retention_days": 45}}
restarted on 18296 (pid 1157067)
$ agent-browser eval "…"  →  {"value":"45","disabled":true,
   "title":"被环境变量 CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS 覆盖",
   "meta":"env 覆盖：CANONICAL_V2_ACCESS_LOG_RETENTION_DAYS …","banner":"banner hidden"}
```

After the restart the process adopted the file-owned value through
`apply_managed_runtime_config`, so the field now reports as env-shadowed with the
saved value in effect — the "save → restart" semantics are unchanged, and the page
tells the operator why the field is no longer editable.

**Port hygiene.** `ss -ltnp` at the end of the smoke:

```
LISTEN 127.0.0.1:18296  users:(("python3",pid=1157067,…))   ← scratch server (this slice)
LISTEN 0.0.0.0:18188    users:(("python3",pid=1203385,…))   ← live serving line, untouched
```

The scratch server was stopped at the end of the smoke and the browser session
closed:

```
$ kill 1157067 ; sleep 3 ; ss -ltnp | grep -E "18296|18188"
LISTEN 0 2048  0.0.0.0:18188  users:(("python3",pid=1203385,fd=31))   ← live line only; 18296 gone
✓ Closed session: default
```

## 5. Deviations and follow-ups

1. **`FieldSpec` grew two columns beyond design.md §1's table** (`connection`,
   `test_arg`). Both are catalogue data, not client logic: `connection` places a
   row in its connection card and `test_arg` names the `connections/test` request
   argument a row supplies. Without them the page would have to spell
   `extraction_endpoints.<key>_base_url` itself — exactly the second source of
   truth this slice removes. Design.md's table says "at least" those columns.
1. **The store now persists only operator-written keys** (design.md §2's "diff
   patch writes only the changed keys into the file", spec.md's "the managed file
   contains exactly that one override"). Before this slice every save wrote the
   full defaulted document. Audit records keep the resolved before/after documents;
   `changed` is the diff of the operator-written keys.
1. **Card 1 does not fetch `/jobs`.** design.md §3 mentions "gate/run state (from
   /jobs data, display only)" for card 1; the frozen plan's and task handoff's card
   1 list is collection fields + freshness + collection history, and `/jobs` already
   owns run state. Nothing was added to `/system-status` or the jobs API.
1. The scratch host resolves credential *key files* from ancestor directories (the
   runtime's documented behaviour), so the scratch smoke displayed masks/origins
   from ambient key files. No value was printed and no scratch write escaped
   `/tmp/admin-config-smoke/`.
