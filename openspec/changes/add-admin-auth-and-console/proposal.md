# Proposal: add-admin-auth-and-console

## Why

The serving system (single-machine, port 18188) exposes its whole admin surface —
configuration, secrets, data browse, access logs, jobs, uploads, seeds — with **no
application-level authentication**. Today the only gate is the deployment-specific
dbg21 nginx `auth_basic` on a subset of paths plus an iptables allowlist; the
customer-site deployment (甲方, single machine, no nginx) would ship an open admin
console. The user ruling (2026-09-17 interview) is: the system must carry its own
login, one dedicated admin console entry (`/main`), admin-managed accounts seeded
in a database, while `/chat` stays public.

In the same review the `/review` human-review workspace was ruled **over-designed**
(no readers: never mounted on the serving entry, no deployment running, 250 KB of
code, and human review is infeasible at tens-of-thousands-of-records scale). The
"data content page" requirement is instead met by the existing `/browse`
(browse + any-field substring search + facets + export).

## What Changes

1. **New capability `admin-auth`** (standard work, design.md):
   - credential store `admin-auth.sqlite3` (scrypt salted hashes, `role` column
     reserved, `password_epoch` for instant revocation);
   - first-boot seeding of one `admin` account with a random password — printed
     once and written to a 0600 file (env-overridable for tests);
   - HMAC-signed session cookie (HttpOnly, SameSite=Lax, Secure only on HTTPS)
     carrying username/issued/expiry/epoch; absolute 12 h, idle 1 h; account
     deletion or password change invalidates immediately;
   - login/logout/self-password/account-management endpoints;
   - per username+IP login throttling (5 failures → 1 min lock, exponential
     backoff; audit records for success and failure).
2. **New capability `admin-console-shell`**:
   - `/main` = login form (unauthenticated) and dashboard (authenticated); the
     dashboard carries the system-status card, quick links, account area;
   - the six admin pages (`/admin` `/logs` `/browse` `/jobs` `/upload` `/seeds`)
     and every `/api/canonical-v2/*` admin API become gated (pages 302 → `/main`,
     APIs 401); shared nav gains current user + logout;
   - gated-route identity = the logged-in username; the client-supplied
     `X-Remote-User` header is ignored for identity and audit everywhere;
   - `/chat`, `/api/chat*`, `/static/*` stay public and unchanged;
   - CSRF baseline: write methods on gated routes require same-origin
     (`Origin`/`Sec-Fetch-Site` check), no CSRF tokens.
3. **Retire `/review`** on the admin-console side (page, API, service, static
   assets, tests, `include_review` wiring, 18189 command references). The
   build-side `human_review_resolutions` validator/trigger family is **out of
   scope** here and goes to the over-design elimination list as its own schema
   slice (it moves the frozen live-schema pin).
4. **Delivery**: `deploy/install.sh` / delivery docs gain the first-boot seeding
   note; HTTPS-termination advice documented (no in-app TLS).

## Out of scope

- Cross-domain unified search for `/browse` (recorded candidate).
- Tokenized/ranked search in `/browse` (R13 work, separate).
- Wiring the D1-a quality report into the `/main` dashboard.
- In-app TLS termination.
- Build-side human-review validator/trigger/table removal (separate slice).
- Any change to the public `/chat` surface or chat APIs.

## Rollback

Single-command rollback: switch `serve-18188-command.sh` back to the previous
command file and restart the service; code roll back by reverting the branch
fast-forward. The credential database (`admin-auth.sqlite3`), its signing key and
audit records live in the serving state directory and are **not** deleted by a
rollback (re-rollout reuses the same accounts).
