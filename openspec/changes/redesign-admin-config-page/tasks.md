# Tasks: redesign-admin-config-page

## A · Contract (server)

- [ ] A1 `FIELD_CATALOG` in `managed_config.py`: label/kind/group/order/bounds/
      consumer/default for every whitelisted path; fail-closed coverage test in
      both directions.
- [ ] A2 `EffectiveField.as_dict()` carries the catalogue columns; `/config`
      payload documented; no file-format change.
- [ ] A3 Lock the save semantics with tests: explicit `null` clears an override
      (bool and text), a diff patch writes only changed keys, unchanged patch
      stays a no-write/no-audit no-op.
- [ ] A4 Endpoint single-channel check: `/config` remains the only writer of
      `extraction_endpoints.*` (no other module writes them).

## B · Page

- [ ] B1 Extract `admin.js` + `admin.css`; `admin.html` keeps only the shell
      (banner, four card containers, snapshot `<details>`).
- [ ] B2 Card 1 采集与构建: collection fields from `fields` + freshness table +
      collection history; no local whitelist.
- [ ] B3 Card 2 检索与回答: serving fields + source badges + rerank runtime badge
      + [测试 Rerank 连通性] using current unsaved values.
- [ ] B4 Card 3 存储与保留: paths fields + storage counts/sizes + disk + retention
      preview.
- [ ] B5 Card 4 连接与密钥: five cards (runtime badge, key origin + mask, key
      write/clear, endpoint+model for the three endpoint connections), one
      [测试连通性] and one 保存本卡 per card (merged result).
- [ ] B6 Dirty tracking + banner (unsaved count / restart-required with copyable
      `systemctl --user restart canonical-v2-backend`); per-card diff save.
- [ ] B7 Removals: client `FIELD_SPECS`, dump-all `collectPatch`, provider table,
      global health button, duplicated endpoint inputs, raw JSON inside cards.
- [ ] B8 Page-marker tests updated (any test asserting the old layout markers).

## C · Verification

- [ ] C1 Targeted suites (admin-console + the managed-config tests) green;
      before/after full-suite failure diff recorded (zero new failures).
- [ ] C2 Scratch-port smoke (own port + scratch settings file): every acceptance
      line in acceptance.md demonstrated, transcript recorded.
- [ ] C3 Live cutover 18188 (fast-forward + restart) + the acceptance lines on the
      live page; rollback drill (revert commit + restart).
