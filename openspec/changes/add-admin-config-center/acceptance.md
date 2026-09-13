# Acceptance: add-admin-config-center (W1)

Source of the acceptance line: `docs/plans/2026-09-07-system-wrapup-config-center-and-periodic-refresh.md`
§6 (W1 row), re-scoped by the 2026-09-13 user decision (managed configuration file; dry run first).

## AC1 — Packaging and isolation

- Work happens in a dedicated worktree/branch; the live 18188 service, the live data assets
  (`/var/tmp/mirothinker-data-v2/index-v1`, `serving-pack-run14-sealed`) and the `.worktrees/data-rebuild`
  worktree are untouched.
- No new front-end framework, no new runtime dependency.

## AC2 — Status endpoint no longer 500

- `GET /api/canonical-v2/admin/status` answers **200** against a runtime whose composed gap
  operations object has no `list_for_admin`, with `gap_summary.state == "unavailable"` and a reason.
- The same endpoint still returns the full `gap_summary` page payload when the operations object
  provides `list_for_admin`.
- Verified by a test that constructs the exact live failure shape
  (`AttributeError: '_EphemeralKnowledgeGapFeedback' object has no attribute 'list_for_admin'`),
  plus a live read-only probe of the 18188 endpoint recorded as before/after evidence.

## AC3 — Managed configuration file

- `config/managed/settings.json` is the carrier; missing file / missing keys resolve to defaults
  without error.
- Only whitelisted, non-sensitive fields can be written. A request carrying an unknown key, a
  non-whitelisted path, or any secret-shaped key is rejected with 4xx and leaves the file unchanged.
- Writes are atomic (temp file in the same directory + `os.replace`; no partial file, no residue).
- A successful write produces exactly one audit record with operator (`X-Remote-User`, else
  `anonymous`), timestamp, before, after, and the changed key paths.
- The file survives a service restart: a `PATCH` followed by a fresh store construction returns the
  patched value (`GET → PATCH → GET` round trip, and a second read from disk).

## AC4 — No second source of truth

- Every whitelist field that duplicates an environment variable resolves `env > file > default`,
  and the API reports the winning `source` per field.
- No chat / retrieval / serving-pack logic is changed by this slice; the serving process is not
  re-wired.

## AC5 — Secrets never exposed

- No API response body contains key material, only `configured` plus a 4-character suffix.
- No test fixture, log line, audit record, or committed file contains real credential material.
- The inventory probe redacts every secret-shaped name.

## AC6 — System status content

`GET /api/canonical-v2/admin/system-status` returns at least:

- serving pack: version/release id, generation time, build time, per-domain record counts,
  manifest hash and marker-hash verification result;
- data freshness: pack build time plus the artifact-derived per-domain view, with the
  build-time-`pipeline_run` view explicitly marked `unavailable` and the reason given when that
  source is not reachable (it is not reachable on the serving host — see design §2.6);
- storage: `lookup.sqlite3` and `milvus.db` health + row/size overview;
- corrections and manual-recall counts;
- disk headroom.

Every block degrades independently: one unreachable source must not 5xx the endpoint.

## AC7 — Provider key visibility with health check

- `POST /api/canonical-v2/admin/providers/health-check` returns, per provider, `configured`,
  `suffix4`, `reachable`, and a bounded detail string; responses contain no plaintext key.
- An unconfigured provider reports `configured: false` without raising.

## AC8 — Page

- `GET /admin` returns 200 and renders: the read-only system-status panel, a configuration form
  that only contains schema-allowed fields, the provider key status area with a health-check
  button, and the shared navigation bar linking `/chat`, `/browse`, `/logs`, `/admin`.
- The page uses no new front-end stack (plain HTML/CSS/JS in the existing static-page family).

## AC9 — Real consumer

- `apps/miroflow-agent/scripts/settings_status.py` reads the managed file through the shared loader
  and prints effective values with `source = env|file|default`; run against the default path and
  against a scratch path, with output captured as evidence.

## AC10 — Layered verification recorded

- `.agents/runs/admin-config-center-w1/verification.md` records: ① new tests (count + what each
  locks + fixture source), ② the pre-existing `apps/admin-console` suite result **before and after**
  (pre-existing failures named, not hidden), ③ the scratch-port 18288 smoke transcript, ④ the
  18188 read-only before/after status probe.
- `.agents/runs/admin-config-center-w1/dry-run-inventory.json` is the machine-checkable dry-run
  artifact.

## Non-goals

Jobs/uploads/seeds (W2/W3), session-audit enrichment (W5), collection scheduling (W6), release
pipeline (W7); any change to chat/retrieval/serving-pack behavior; any secret value moving into the
repository or into an API response.
