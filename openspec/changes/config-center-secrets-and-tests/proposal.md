# Proposal: config-center-secrets-and-tests

## Why

The admin config center (change `add-admin-config-center`, W1, live) made the serving line's
**non-sensitive** configuration editable from `/admin` and showed provider credentials read-only. The
2026-09-15 requirement revision (**R16**) closes the remaining half of the user's ask — *"核心就是把配置
做成 Web UI，让管理员方便配置"*:

1. **Keys must be settable from the page**, not only visible. They are written to a managed key file
   (mode 0600); the page only ever echoes a mask plus "configured / not configured".
2. **One uniform mechanism: read at service startup.** No special hot-read path for keys, no hot reload
   for anything (the 2026-09-15 correction: key rotation is not a high-frequency operation; a restart is
   acceptable). The page says so and never restarts the service for the operator.
3. **Every connection gets a connectivity test button** that answers before saving (*先测后存*): the
   server performs one minimal call with the values currently typed on the page and returns
   success/failure + latency. Rate-limited per connection so the button cannot be turned into a billing
   incident; results record status and latency only, never the credential.
4. **Recently added switches join the managed list** (`CANONICAL_V2_WEB_TOPICAL_FLOOR`, rerank
   base-url/model/timeout/max-documents, serving receipt path, turn-debug dir, full-verify), each judged
   individually for whether it belongs on an operator page (gap G28).

The W1 dry run and log show the file-edit + env-overrides-file mechanism already works and is
inspectable; this slice extends that same carrier instead of inventing a second one.

## What Changes

Behaviour-affecting: new managed data contract for credentials, three new admin HTTP routes, a new
bootstrap step at service startup, additions to the managed settings whitelist, and page extension. No
retrieval/answer behaviour changes.

1. **Managed secrets store** — `config/managed/secrets.json` (path override
   `CANONICAL_V2_MANAGED_SECRETS`): a whitelist of connection credentials, atomic write, **mode 0600**,
   append-only audit carrying field names and 4-character tails only. A missing/unreadable file resolves
   to "not configured", never to an error.
2. **Startup bootstrap** — `apply_managed_runtime_config()` projects file-owned values into the process
   environment at service startup (`env` always wins; only values explicitly present in the file are
   projected, never defaults) and returns a value-free receipt. Called from the serving pack open path
   and from the V2 shell's startup event. No hot path reads the file.
3. **Admin API** — `GET/PATCH /api/canonical-v2/admin/secrets`,
   `POST /api/canonical-v2/admin/connections/test`. Responses carry masks, origins and a
   `restart_required` flag; credentials are never echoed.
4. **Connection tests** — one minimal call per connection for Bocha, Serper, rerank, embedding and LLM
   (chat), with an injectable transport, a bounded timeout, a sanitized failure reason, and an in-process
   rate limiter (per connection + client) returning HTTP 429 + `retry_after_seconds`.
5. **Managed settings whitelist** — new `serving` section + per-field page editability policy
   (debug-only switches are displayed read-only with a reason: they are boot-cost/forensics switches that
   must stay pinned by the service unit).
6. **`/admin` page** — a credentials + connectivity card: mask/status/origin per connection, a
   write-only input, save/clear buttons, a test button that uses the typed value, latency and rate
   feedback, and the restart-after-change notice.

## Capabilities

### Added Capabilities
- `admin-config-center-secrets` — managed credential file contract, startup bootstrap, connection-test
  endpoints and the page surface that consumes them.

### Modified Capabilities
- `admin-config-center` — the managed settings whitelist gains a `serving` section and a read-only
  editability policy; `GET /config` reporting is unchanged in shape apart from the additive field.

## Impact

- `apps/miroflow-agent/src/data_agents/canonical_v2/managed_secrets.py` (new).
- `apps/miroflow-agent/src/data_agents/canonical_v2/managed_runtime.py` (new).
- `apps/miroflow-agent/src/data_agents/canonical_v2/managed_config.py` (`serving` section + env map +
  read-only policy).
- `apps/miroflow-agent/src/data_agents/canonical_v2/serving_pack_loader.py` (bootstrap call at pack open).
- `apps/admin-console/backend/services/canonical_v2_connection_tests.py` (new).
- `apps/admin-console/backend/api/canonical_v2_admin_config.py` (new routes).
- `apps/admin-console/backend/main.py` (startup bootstrap).
- `apps/admin-console/backend/static/admin.html` (credentials card).
- `apps/miroflow-agent/scripts/settings_status.py` (managed-secret origin in `--check-keys`).
- `config/managed/secrets.example.json` (committed template), `.gitignore`.

## Security

- Plaintext exists only in: the request body of an explicit operator action, the managed file (0600), and
  the process environment after startup. It never reaches a response body, a log line, an audit record, a
  fixture, or git.
- Rate limiting is the only thing standing between the test button and a provider bill; it is enforced
  server-side, per connection and per client, and counted in the response.

## Out of Scope

Hot reload, key rotation workflows, secret distribution beyond the serving host, the W2/W4/W6 job and
schedule surfaces, and any change to retrieval, fusion, rerank or answer behaviour.

## Status

Proposed 2026-09-15. Implementation + verification in the same slice; evidence in
`.agents/runs/config-center-secrets-and-tests/`.

## Human doc cross-link

- Log (Chinese, append-only): `docs/plans/2026-09-15-config-center-secrets-log.md`
- Requirement rows: `docs/plans/2026-09-15-requirements-gap-plan.md` §1 R16, §2 G28, §3.2 P13.
- Previous slice: `docs/plans/2026-09-14-admin-config-center-log.md` (W1, live).
