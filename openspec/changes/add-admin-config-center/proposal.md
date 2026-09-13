# Proposal: add-admin-config-center

## Why

The serving line (canonical-v2, V2 shell `apps/admin-console/backend/main.py`) has no web entry
point for configuration or operational state. Operators must log into the machine to see whether a
provider key is configured, what serving pack is live, or how fresh each data domain is. The
authoritative product plan (`docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md`
§3, slice **W1**) scopes the first slice of that gap; the 2026-09-13 user decision re-targeted the
config carrier from a serving-side SQLite settings table to a **managed configuration file** (web
edits the file, services/scripts read it at startup) and required a **dry run first, page second**.

Two live facts drive the shape of this slice:

1. `GET /api/canonical-v2/admin/status` returns HTTP 500 on the live 18188 service. The traceback
   (`AttributeError: '_EphemeralKnowledgeGapFeedback' object has no attribute 'list_for_admin'`,
   captured 2026-09-13) is reproduced below in *Impact*. The pack-mode composition passes the
   ephemeral in-process gap feedback (which only implements `record` / `apply_remediation`) where
   the admin runtime expects a `list_for_admin`-capable operations object.
2. The dry-run inventory (`.agents/runs/admin-config-center-w1/dry-run-inventory.json`, design.md
   §2) shows most serving knobs are environment- or manifest-owned and already work; the missing
   capability is *visibility*, not a new source of truth.

## What Changes

Behavior-affecting (new public API surface, new managed-configuration data contract, new web page,
one repaired endpoint contract).

1. **Managed configuration file** (`config/managed/settings.json`): a whitelist-validated,
   non-sensitive Pydantic schema, atomic writes (tmp + `os.replace`), append-only audit
   (`config/managed/audit.jsonl`), and environment-overrides-file precedence for every field in
   which an env variable already exists.
2. **Admin APIs** under the existing `/api/canonical-v2/admin` prefix:
   `GET/PATCH /api/canonical-v2/admin/config`,
   `GET /api/canonical-v2/admin/system-status`,
   `POST /api/canonical-v2/admin/providers/health-check`.
3. **Status repair**: `GET /api/canonical-v2/admin/status` stops returning 500; the gap summary
   degrades to a typed `unavailable` marker when the composed operations object has no
   `list_for_admin` capability. No serving/retrieval logic changes.
4. **`admin.html`** static page (same family as `/browse`, `/logs`; no new front-end stack) with a
   read-only system-status panel, a schema-driven configuration form, a provider-key status area
   with an on-demand health check, and a shared navigation bar.
5. **One real consumer**: `apps/miroflow-agent/scripts/settings_status.py`, an operator CLI that
   reads the same managed file through the same loader and reports effective values with
   `source: env|file|default` annotations. The serving process itself is *not* re-wired — the
   inventory shows no serving behavior needs a new input, and re-wiring would invalidate the
   frozen replay evidence.

## Capabilities
### Added Capabilities
- `admin-config-center` — managed settings file contract, admin config/status/provider APIs,
  `admin.html`, and the operator CLI consumer.

### Modified Capabilities
- `rebuild-canonical-v2-knowledge-platform` (serving shell surface): the previously 500-ing
  `GET /api/canonical-v2/admin/status` becomes a 200 with a typed `gap_summary` state, and three
  new admin routes join the isolated surface. No retrieval/fusion/rerank/answer behavior changes.

## Impact

- `apps/miroflow-agent/src/data_agents/canonical_v2/managed_config.py` (new, shared schema/store).
- `apps/admin-console/backend/services/canonical_v2_managed_config.py` (new, admin adapter).
- `apps/admin-console/backend/api/canonical_v2_admin_config.py` (new router).
- `apps/admin-console/backend/main.py` (mount router, serve `/admin`).
- `apps/admin-console/backend/services/canonical_v2_admin.py` (`status()` gap-summary degradation).
- `apps/admin-console/backend/static/admin.html` (new), `logs.html` / `browse.html` (nav link only).
- `apps/miroflow-agent/scripts/settings_status.py` (new CLI consumer).
- `config/managed/` (new runtime dir, ignored), `.gitignore` (keep the template/schema visible).
- Live 500 evidence (verbatim journalctl, 2026-09-13):
  `AttributeError: '_EphemeralKnowledgeGapFeedback' object has no attribute 'list_for_admin'`
  raised from `canonical_v2_admin.py:631` via `canonical_v2_consumers.py:123`.
- No database migration, no serving-pack change, no `release/customer-test` hot update.

## Out of Scope

Jobs/uploads/seeds surfaces (W2/W3), session-audit enrichment (W5), periodic collection wiring
(W6), release pipeline (W7), and any change to chat/retrieval/serving-pack logic.

## Status

Proposed 2026-09-14. Implementation + verification land in the same slice; evidence in
`.agents/runs/admin-config-center-w1/`.

## Human doc cross-link

- Dry-run inventory (Chinese): `docs/plans/2026-09-14-admin-config-center-dry-run.md`
- Execution log (Chinese, append-only): `docs/plans/2026-09-14-admin-config-center-log.md`
- Plan entry: `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md` §3 / §6 (W1 row)
