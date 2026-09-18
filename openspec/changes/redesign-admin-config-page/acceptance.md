# Acceptance: redesign-admin-config-page

Demonstrated on the live 18188 after cutover; evidence in
`.agents/runs/redesign-admin-config-page/verification.md`.

| # | Line | How |
|---|---|---|
| A1 | Adding a catalogue row for a new whitelisted field makes it appear on the page with no client change | add a field + catalogue row in a scratch build; scratch page renders it |
| A2 | Save writes only the dirty keys; untouched keys never enter the file | scratch: change one field → the settings file contains exactly that path; clear it → back to `source=default` |
| A3 | Booleans are three-state: 默认 / 启用 / 停用, and 默认 clears an override | scratch UI + file inspection |
| A4 | `extraction_endpoints.*` has exactly one entry point (the connection cards); the settings form no longer renders them | page inspection + grep of `admin.js` |
| A5 | Per-card flow: 测试（未保存值）→ 保存本卡 → banner "需重启生效" with the copyable restart command | scratch smoke transcript |
| A6 | Cards 1/3 show their own state (freshness table in card 1; storage counts + retention preview in card 3) with no separate status block and no duplication with `/main` | live page check |
| A7 | Rollback drill: revert the slice commit + restart returns the previous `/admin` behaviour | live drill |

Regression guards: the admin-auth gate behaviour (302/401) is untouched; the
existing config API contracts (`/config`, `/secrets`, `connections/test`) keep
their request/response shapes for anything unchanged; full-suite failure diff
shows zero new failures.
