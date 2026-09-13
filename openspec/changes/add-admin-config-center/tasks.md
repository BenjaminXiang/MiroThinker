# Tasks: add-admin-config-center

Status legend: `[ ]` pending, `[~]` in progress, `[x]` done with evidence.

## 1. Setup (behavior-affecting ⇒ verification contract first)

- [x] 1.1 Create `openspec/changes/add-admin-config-center/` (proposal, design, spec deltas, tasks, acceptance).
- [x] 1.2 Create `.agents/runs/admin-config-center-w1/verification-contract.md` before any production-code edit.
- [x] 1.3 Dry run: execute the read-only inventory probe; persist `.agents/runs/admin-config-center-w1/dry-run-inventory.json`.

## 2. Managed configuration (shared module)

- [x] 2.1 `managed_config.py`: whitelist Pydantic schema, `extra="forbid"`, no secret fields.
- [x] 2.2 Defaults for a missing file / missing keys; never raise on a missing file.
- [x] 2.3 Atomic write (temp file in the target dir + `os.replace`), restrictive file mode.
- [x] 2.4 Audit append (`audit.jsonl`, flock, before/after/changed/operator) — never rewritten.
- [x] 2.5 Env-over-file precedence map + `source` reporting (`env|file|default`).
- [x] 2.6 Committed template `config/managed/settings.example.json`; `.gitignore` keeps the template visible and the runtime file ignored.

## 3. Admin APIs

- [x] 3.1 `GET /api/canonical-v2/admin/config` (schema + effective values + per-field source).
- [x] 3.2 `PATCH /api/canonical-v2/admin/config` (422 on non-whitelisted/secret/ill-typed input; audit on success).
- [x] 3.3 `GET /api/canonical-v2/admin/system-status` with independently degradable blocks.
- [x] 3.4 `POST /api/canonical-v2/admin/providers/health-check` (presence + suffix only, bounded probe).
- [x] 3.5 Repair `GET /api/canonical-v2/admin/status`: degrade `gap_summary` when the operations object has no `list_for_admin`; keep the existing payload when it does.
- [x] 3.6 Mount the router and serve `/admin` from the V2 shell.

## 4. Page

- [x] 4.1 `backend/static/admin.html`: status panel, schema-driven config form, provider key area with health-check button, shared nav.
- [x] 4.2 Add the `/admin` link to the existing `logs.html` navigation.

## 5. Consumer

- [x] 5.1 `apps/miroflow-agent/scripts/settings_status.py` reads the same loader; reports `env|file|default`.
- [x] 5.2 Document that the serving process is deliberately not re-wired (env wins by construction).

## 6. Verification

- [x] 6.1 New: `tests/test_managed_settings_store.py` (schema/whitelist/secret/atomic/audit/precedence).
- [x] 6.2 New: `tests/test_canonical_v2_admin_config_api.py` (round trip, 4xx, status, health check).
- [x] 6.3 New: `tests/test_canonical_v2_admin_status_repair.py` (the reported 500 defect).
- [x] 6.4 Full `apps/admin-console` pytest; record baseline-vs-after honestly (pre-existing reds named).
- [x] 6.5 Scratch-port smoke on **18288** + scratch config dir: page 200, round trip, 4xx, no plaintext.
- [x] 6.6 `settings_status.py` run against the repo default path and a scratch config dir.
- [x] 6.7 `.agents/runs/admin-config-center-w1/verification.md` with layered evidence.

## 7. Documentation

- [x] 7.1 `docs/plans/2026-09-14-admin-config-center-dry-run.md` (Chinese, dry-run findings).
- [x] 7.2 `docs/plans/2026-09-14-admin-config-center-log.md` (Chinese, append-only log entry).
- [x] 7.3 `docs/plans/index.md` — append one line only.
- [x] 7.4 `openspec/change-ledger.md` — append the change row.

## 8. Commit

- [x] 8.1 Commit on `feat/admin-config-center` (no push).
