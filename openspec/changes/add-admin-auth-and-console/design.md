# Design: add-admin-auth-and-console

Grounded in the 2026-09-17 interview (14 rulings recorded in
`docs/plans/2026-09-17-admin-auth-and-console.md` §共识清单). Target environment:
customer-site single machine, no nginx, plain HTTP on a LAN unless the customer
fronts it with TLS termination.

## 1. Credential store

- One SQLite file `admin-auth.sqlite3` in the serving state directory
  (`CANONICAL_V2_ADMIN_AUTH_DB` overrides; default next to
  `access-logs.sqlite3` / `corrections.sqlite3`), mode 0600.
- Schema `canonical-v2-admin-auth-v1`:

  | table | columns |
  |---|---|
  | `accounts` | `username TEXT PRIMARY KEY`, `password_hash TEXT`, `password_salt TEXT`, `password_epoch INTEGER NOT NULL DEFAULT 1`, `role TEXT NOT NULL DEFAULT 'admin'`, `created_at TEXT`, `updated_at TEXT` |
  | `audit` | `id INTEGER PRIMARY KEY AUTOINCREMENT`, `at TEXT`, `actor TEXT`, `action TEXT`, `target TEXT`, `source_ip TEXT`, `result TEXT`, `detail TEXT` |
  | `meta` | `key TEXT PRIMARY KEY`, `value TEXT` (holds `schema_version`) |

- Passwords: `hashlib.scrypt` (n=2**14, r=8, p=1, dklen=32, 16-byte random salt
  per user), constant-time compare (`hmac.compare_digest`). Plaintext never
  stored, never logged.
- Single role `admin` for every account; `role` is reserved for a future
  read-only role and is not interpreted in this slice.

## 2. Signing key and session codec

- HMAC-SHA256 key, 32 random bytes, persisted in a 0600 file `admin-auth.key`
  next to the database (generated on first use; `CANONICAL_V2_ADMIN_AUTH_KEY`
  overrides for tests). Sessions survive restarts.
- Cookie `cv2_admin_session` = `base64url(payload).base64url(hmac)` with payload
  `{"u": username, "iat": iso8601, "exp": iso8601, "ep": password_epoch}`.
- Validation per request: signature → `exp > now` → account exists → epoch
  matches. Failure sets no identity (treated as unauthenticated).
- Idle/absolute policy: `exp = min(now + 1h, iat + 12h)` refreshed on every
  authenticated request (sliding idle window, hard 12 h absolute). No
  "remember me"; no server-side session table.
- Cookie attributes: `HttpOnly`, `SameSite=Lax`, `Path=/`, and `Secure` only
  when the request reached us over HTTPS (`X-Forwarded-Proto=https` or `https`).

## 3. Login throttling

- In-process limiter keyed `login:{username}:{client_ip}`: 5 failures lock for
  60 s; further failures double the lock (cap 30 min); success and expiry clear
  the counter. Reuses the existing `_TEST_LIMITER`-style decision object.
- Every attempt (success, failure, locked-out) appends an `audit` row
  (`action=login`, `result=ok|fail|locked`).

## 4. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` | public | credentials → session cookie |
| POST | `/api/auth/logout` | session | clear cookie, audit |
| GET | `/api/auth/me` | session | `{username, role, expires_at}` for the shell |
| POST | `/api/auth/password` | session | change own password (bumps epoch) |
| GET | `/api/auth/accounts` | session | account list (username/role/created; never hashes) |
| POST | `/api/auth/accounts` | session | create account (username + generated-or-given password) |
| DELETE | `/api/auth/accounts/{username}` | session | delete account (bumps nothing; sessions die via missing account) |
| POST | `/api/auth/accounts/{username}/password` | session | reset another account's password (bumps epoch) |

- Self-deletion guard: the last remaining account cannot be deleted.
- Writes on `/api/auth/*` and gated admin APIs require the same-origin check.

## 5. Gate (admin-console shell)

- One ASGI middleware in the serving shell app:
  - **Gated page paths**: exactly `/admin`, `/logs`, `/browse`, `/jobs`,
    `/upload`, `/seeds` → unauthenticated: `302 Location: /main`.
  - **Gated API prefixes**: `/api/canonical-v2/` (the whole admin surface) and
    the session-required `/api/auth/*` endpoints (login excluded) →
    unauthenticated: `401 {"detail":"authentication_required"}`.
  - **Public**: `/main` (shell), `/chat`, `/api/chat*`, `/static/*`,
    `/api/health`, `/api/auth/login`.
- Write methods (POST/PATCH/PUT/DELETE) on gated routes require same-origin:
  reject when `Origin` is present and differs from the request host, or when
  `Sec-Fetch-Site` is `cross-site`/`same-site`. Absent both headers (CLI
  clients) is allowed.
- The authenticated username is stashed on `request.state.admin_user`; the
  existing `_operator()` helper returns that identity for gated routes and
  `"anonymous"` otherwise — the `X-Remote-User` header is no longer read for
  identity anywhere (it stays untouched on the public chat path for
  backwards-compatible log fields, which resolve to empty).

## 6. First-boot seeding

- At shell startup (idempotent): if `accounts` is empty → create `admin` with a
  random 16-char password (`CANONICAL_V2_ADMIN_INITIAL_PASSWORD` overrides for
  tests), write the password once to `<state>/admin-initial-password.txt` (0600),
  print one line to stdout (`journalctl` visible). No forced change; the shell
  shows a hint until the password file is removed.

## 7. `/main` shell page

- One static `main.html` (+ `main.js`/`main.css`): unauthenticated → login form;
  authenticated → dashboard with (1) system-status card (reuse
  `/api/canonical-v2/admin/system-status`), (2) quick links to the six pages and
  `/chat`, (3) account area (self password change; admin list/create/delete/
  reset), (4) top-right current user + logout.
- All six admin pages' shared nav gains `首页`(`/main`), current user and
  `退出登录`.

## 8. `/review` retirement (admin-console side)

- Delete `api/canonical_v2_review.py`, `services/canonical_v2_review.py`,
  `static/review.html|review.js|review.css|review_mutation_coordinator.js|
  review_presentation.js`, the two review test files, the `include_review`
  wiring in `main.py`, and 18189 command/script references.
- The build-side `human_review_resolutions` validators/triggers and the review
  tables in the frozen build schema are **not touched** (separate slice; they
  move the frozen live-schema pin).

## 9. Rollout

- Feature branch `feat/admin-auth-console` off the serving line tip; targeted
  tests; scratch-port smoke (own port + scratch DB, never 18188); then
  fast-forward the live worktree, copy the (unchanged) command file family and
  restart. Rollback = switch command file back + restart; the auth database,
  key and audit survive.
