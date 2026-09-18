# Tasks: redesign-admin-config-page

## A · Contract (server)

- \[x\] A1 `FIELD_CATALOG` in `managed_config.py`: label/kind/group/order/bounds/
  consumer/default for every whitelisted path; fail-closed coverage test in
  both directions.
- \[x\] A2 `EffectiveField.as_dict()` carries the catalogue columns; `/config`
  payload documented; no file-format change.
- \[x\] A3 Lock the save semantics with tests: explicit `null` clears an override
  (bool and text), a diff patch writes only changed keys, unchanged patch
  stays a no-write/no-audit no-op.
- \[x\] A4 Endpoint single-channel check: `/config` remains the only writer of
  `extraction_endpoints.*` (no other module writes them).

## B · Page

- \[x\] B1 Extract `admin.js` + `admin.css`; `admin.html` keeps only the shell
  (banner, four card containers, snapshot `<details>`).
- \[x\] B2 Card 1 采集与构建: collection fields from `fields` + freshness table +
  collection history; no local whitelist.
- \[x\] B3 Card 2 检索与回答: serving fields + source badges + rerank runtime badge
  \+ \[测试 Rerank 连通性\] using current unsaved values.
- \[x\] B4 Card 3 存储与保留: paths fields + storage counts/sizes + disk + retention
  preview.
- \[x\] B5 Card 4 连接与密钥: five cards (runtime badge, key origin + mask, key
  write/clear, endpoint+model for the three endpoint connections), one
  \[测试连通性\] and one 保存本卡 per card (merged result).
- \[x\] B6 Dirty tracking + banner (unsaved count / restart-required with copyable
  `systemctl --user restart canonical-v2-backend`); per-card diff save.
- \[x\] B7 Removals: client `FIELD_SPECS`, dump-all `collectPatch`, provider table,
  global health button, duplicated endpoint inputs, raw JSON inside cards.
- \[x\] B8 Page-marker tests updated (any test asserting the old layout markers).

## C · Verification

- \[x\] C1 Targeted suites (admin-console + the managed-config tests) green;
  before/after full-suite failure diff recorded (zero new failures).
- \[x\] C2 Scratch-port smoke (own port + scratch settings file): every acceptance
  line in acceptance.md demonstrated, transcript recorded.
- \[ \] C3 Live cutover 18188 (fast-forward + restart) + the acceptance lines on the
  live page; rollback drill (revert commit + restart). — parent session.

## Deviation notes

- `FieldSpec` carries two columns beyond design.md §1's table: `connection` (which
  connection card owns the row) and `test_arg` (which `connections/test` request
  argument the row supplies). Both keep the page free of endpoint field-name
  knowledge; design.md's table is a "at least" list.
- The managed-settings store now persists only operator-written keys (design §2 /
  spec delta: "the managed file contains exactly that one override"). Audit records
  keep the resolved before/after documents.
- Card 1 shows collection fields + freshness + collection history from
  `/system-status`; run/gate state stays on `/jobs` (no `/jobs` fetch added).
