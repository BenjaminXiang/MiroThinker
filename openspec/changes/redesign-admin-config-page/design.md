# Design: redesign-admin-config-page

Ruling to satisfy (2026-09-18): **every configuration card carries its own
display, edit and verification** — the operator never leaves the card to learn
the state of what they are changing.

## 1. The single field catalogue (server)

`managed_config.py` gains `FIELD_CATALOG: dict[str, FieldSpec]` — the only place
that knows how a setting is presented:

| attribute | example | used by |
|---|---|---|
| `label` | `访问日志保留天数` | card rendering |
| `kind` | `bool` / `int` / `float` / `text` / `url` | widget choice |
| `group` | `collection` / `serving` / `paths` | which card |
| `order` | int within a group | ordering |
| `min` / `max` / `step` | `1..3650` | input bounds |
| `consumer` | `采集与构建调度` / `服务启动` | the "what does this affect" note |
| `default` | from `ManagedSettings()` | "默认值：90" hint + reset |
| `env_var` | existing map | env badge (already present) |

A fail-closed test asserts **catalogue coverage**: every whitelisted path has a
row, and every row has a whitelisted path (mirrors `PAGE_READONLY_FIELDS`
coverage). `EffectiveField.as_dict()` grows these columns; `/config`'s `fields`
thus becomes render-ready and the page stops holding its own list.

## 2. Save semantics

- The page tracks dirt per field and PATCHes **only dirty paths**.
- Three-state value handling, uniform across kinds:
  - `default` (clear override) → explicit `null` in the patch;
  - a concrete value → as typed (bools become `true`/`false` only when chosen);
  - untouched fields are never sent.
- The store already supports null-clearing through `_deep_merge` and treats
  "nothing changed" as a no-write/no-audit no-op; tests lock: (a) clearing a bool
  override returns the field to `source=default`, (b) a diff patch writes only
  the changed keys into the file.
- Per-card 保存 (the card owns its dirty set); the page-level banner aggregates
  ("N 项未保存" / "已保存，重启生效") with the restart command to copy.

## 3. Page layout (`admin.html` + `admin.js` + `admin.css`)

```
[banner: unsaved / restart-required, with the systemctl command to copy]
Card 1 采集与构建   collection.* | freshness table (pack build vs投影时点, per domain),
                                 collection history, gate/run state (from /jobs data,
                                 display only)
Card 2 检索与回答   serving.*    | per-field source badge + runtime-enabled badge (rerank),
                                 [测试 Rerank 连通性] (POST connections/test with current
                                 unsaved values)
Card 3 存储与保留   paths.*      | access_log / corrections / lookup counts + sizes,
                                 disk headroom, retention preview ("保留至 <date>")
Card 4 连接与密钥   5 connection cards | runtime badge (enabled/disabled + reason),
                                 key origin (env / managed file / legacy file) + mask,
                                 key write/clear, endpoint+model edit (endpoint
                                 connections only), [测试连通性] with unsaved values,
                                 保存本卡 (secrets PATCH then config PATCH, one merged
                                 result message)
[collapsed] 只读快照: raw /config JSON + env override list + /secrets mask view
```

Rules enforced in the rebuild:

- **One field, one entry point**: `extraction_endpoints.*` appears only inside the
  connection cards; the config form never renders them again.
- **No client-side whitelist**: everything rendered comes from `fields`
  (card 1–3) or `connections` (card 4).
- **Verification is honest**: only connections have an active probe
  (`connections/test`); cards 1 and 3 show state, they do not grow fake tests.
- **Runtime truth stays server-derived**: badges reuse the existing
  `runtime`/`source` payloads; the page computes no effective values itself.

## 4. Removals

- `FIELD_SPECS` (client), `collectPatch` (dump-all), the provider-key table, the
  global health-check button/endpoint usage (connection cards carry the tests;
  `/api/.../providers/health-check` stays available for CLI use and may be wired
  later as "全部测试" — not removed from the API), the duplicated endpoint
  inputs inside the settings form, the raw-JSON block inside the status card
  (moves to the snapshot).

## 5. Files

| file | change |
|---|---|
| `apps/miroflow-agent/src/data_agents/canonical_v2/managed_config.py` | `FIELD_CATALOG`, richer `as_dict()`, coverage test hook |
| `apps/admin-console/backend/static/admin.html` | rebuilt shell (cards + banner + snapshot) |
| `apps/admin-console/backend/static/admin.js` (new) | rendering, dirty tracking, per-card save/test |
| `apps/admin-console/backend/static/admin.css` (new) | card layout |
| `apps/admin-console/tests/*` | catalogue coverage, null-clearing, diff-write, page markers |
