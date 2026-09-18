# Verification contract: redesign-admin-config-page

TDD boundary: RED first from this list; page-level claims additionally require a
scratch-port smoke (TestClient alone is not sufficient), and the live acceptance
in `acceptance.md` is the closing evidence.

| # | RED | Locks |
|---|---|---|
| R1 | catalogue coverage tests (`managed_config`): every whitelisted path has a row; no orphan rows; every row carries label/kind/group/order/consumer/default | single source of truth |
| R2 | `EffectiveField.as_dict()` carries the catalogue columns; `/config` `fields` include them | render-ready payload |
| R3 | null-clearing: patch `{path: null}` removes the override; `source` returns to `default`; bool and text both | three-state semantics |
| R4 | diff-write: a patch with two changed paths writes exactly those keys; re-sending the same patch is a no-write/no-audit no-op | minimal file, restore-to-default |
| R5 | endpoint single-channel: grep-level test that no module other than the config store writes `extraction_endpoints.*`, and the page JS contains no second endpoint writer | one entry point |
| R6 | page shell markers: `admin.html` loads `admin.js`/`admin.css`; the four card containers exist; no `FIELD_SPECS`/provider-table/global-health-button markers remain | rebuild shape |
| R7 | banner semantics: unsaved-count and restart-required markers present in the page JS | save/restart contract |

Fixture rules: tests use `tmp_path` settings/secrets files and the app's
`TestClient`; no test touches the live state directory or port 18188; no secret
value is printed.

GREEN evidence plan:

1. targeted suites green in the feature worktree;
2. admin-console + miroflow-agent `managed_config` suites: before/after failure
   diff, zero new failures;
3. scratch-port smoke (own port, scratch settings file): the seven acceptance
   lines with a transcript, service stopped afterwards;
4. live cutover + the acceptance lines on 18188 + rollback drill.
