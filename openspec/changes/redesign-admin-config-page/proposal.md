# Proposal: redesign-admin-config-page

## Why

The operator configuration surface (`/admin`) grew across four slices (W1 config
centre, W2/W3 consoles, the `add-admin-auth-and-console` shell) without one
information-architecture pass. A full read of `admin.html` (1093 lines: 215 CSS +
132 markup + **735 inline JS**) found four structural defects, each with code
evidence:

1. **Two channels for one field.** `extraction_endpoints.*` is editable both in
   the managed-config form (`FIELD_SPECS`) and again as per-connection endpoint
   inputs whose save path hardcodes `connectionKey === "embedding" ? …` and
   PATCHes `/config` from inside a `/secrets` save (`saveSecret`→`saveEndpoints`).
2. **Three copies of schema knowledge.** Server pydantic model → server
   `EffectiveField` (no label/kind/bounds) → a hand-copied client `FIELD_SPECS`
   that silently drops server-added fields (`if (!field) return;`).
3. **Save-all instead of diff.** `collectPatch` submits every field on every
   save, freezing defaults as explicit overrides; booleans can never return to
   "default"; empty int skips, empty text clears, bool always writes — three
   semantics for one gesture.
4. **Four concerns on one page, duplicated elsewhere.** Status tables vs `/main`,
   the provider-key table vs the connection rows, two connectivity mechanisms.

User ruling (2026-09-18): **configuration, verification and display belong
together** — one card per configuration domain carrying its own current state,
its edit controls, and its verification action, instead of hopping between pages.

## What Changes

1. **Contract (slice A).** One server-side field catalogue
   (`FIELD_CATALOG` in `managed_config.py`) becomes the single source for label,
   kind, group, order, bounds, consumer note and default; `EffectiveField`
   carries it into `/config`'s `fields` so the page renders a pure function of
   the payload. Diff saves become expressible: explicit `null` clears an
   override (three-state booleans), and the page submits dirty fields only.
2. **Page (slice B).** `admin.html` is rebuilt as four cards —
   采集与构建 / 检索与回答 / 存储与保留 / 连接与密钥 — each with its display
   strip, its fields, and its verification; plus a save/restart banner and a
   collapsed read-only snapshot. JS and CSS move to `admin.js` / `admin.css`.
   Removed: the client `FIELD_SPECS`, the provider-key table (folded into the
   connection cards), the global health-check button (folded or dropped), and
   the duplicated endpoint inputs in the config form.

## Out of scope

- Hot reload of managed settings (the "save → restart" semantics stay).
- New dry-run probes (cards 1/3 verify by *showing* state, not by inventing
  probes).
- A front-end framework (the console stays dependency-free static files).
- `/main` (dashboard) layout beyond not duplicating the config page.

## Rollback

Single-command rollback: fast-forward the live tree back to the pre-slice commit
and restart; the managed settings/secrets files and the admin-auth store are
untouched by the page rewrite (the contract change is additive: richer `fields`
payload, no schema or file-format change).
