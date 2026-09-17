# Verification: add-admin-auth-and-console

Slice: tasks 1.1–4.2, 5.1, 6.1, 6.2 (6.3 cutover is the parent session's step).
Branch `feat/admin-auth-console` off `8fc0fa7f`. All commands below were run in
`/home/longxiang/MiroThinker/.worktrees/admin-auth-console/apps/admin-console`
unless a path says otherwise. No test, script, or command in this slice touched
port 18188 or the live serving state directory.

## 1. RED (before implementation)

```
$ uv run pytest -q -p no:randomly -p no:cacheprovider --tb=line \
    tests/test_admin_auth_store.py tests/test_admin_auth_session.py tests/test_admin_auth_throttle.py \
    tests/test_admin_auth_http.py tests/test_admin_gate.py tests/test_admin_console_shell.py \
    tests/test_review_removed.py
ERROR collecting tests/test_admin_auth_store.py     ModuleNotFoundError: No module named 'backend.services.admin_auth'
ERROR collecting tests/test_admin_auth_session.py   ModuleNotFoundError: No module named 'backend.services.admin_auth'
ERROR collecting tests/test_admin_auth_throttle.py  ModuleNotFoundError: No module named 'backend.services.admin_auth'
ERROR collecting tests/test_admin_auth_http.py      ModuleNotFoundError: No module named 'backend.services.admin_auth'
ERROR collecting tests/test_admin_gate.py           ModuleNotFoundError: No module named 'backend.services.admin_auth'
ERROR collecting tests/test_admin_console_shell.py  ModuleNotFoundError: No module named 'backend.services.admin_auth'
6 errors in 0.35s   (R1–R6 fail for the missing feature: the auth package does not exist yet)

$ uv run pytest -q -p no:randomly -p no:cacheprovider --tb=line tests/test_review_removed.py
14 failed, 2 passed in 0.08s
  - 12 × test_retired_review_files_are_deleted[...]      (review modules/static/script/tests still on disk)
  -     test_retired_review_modules_are_not_importable   (did not raise ModuleNotFoundError)
  -     test_no_production_module_mentions_a_retired_review_token (17 offender lines)
  - 2 passed: the two route-table assertions (the shell never mounted /review)
```

Missing functionality = the only reason for every RED failure (contract R1–R7).

## 2. GREEN — targeted suites (contract R1–R7)

```
$ uv run pytest -q -p no:randomly -p no:cacheprovider \
    tests/test_admin_auth_store.py tests/test_admin_auth_session.py tests/test_admin_auth_throttle.py \
    tests/test_admin_auth_http.py tests/test_admin_gate.py tests/test_admin_console_shell.py \
    tests/test_review_removed.py
84 passed in 4.48s
```

| RED | file | tests | locks |
|---|---|---|---|
| R1 | tests/test_admin_auth_store.py | 13 | scrypt hash+salt per account, no plaintext, epoch bump on password change, CRUD + last-account guard, audit append/order, env path override (never the default state dir), seeding idempotence + 0600 password file [constructed store] |
| R2 | tests/test_admin_auth_session.py | 8 | sign/verify round trip, tampered payload *and* signature rejected, idle window expiry + sliding refresh, absolute 12 h cap over repeated refreshes, epoch/account-missing rejection, 0600 key file reused across reloads, Secure only on HTTPS, `X-Forwarded-Proto` [constructed key + store, injected clock] |
| R3 | tests/test_admin_auth_throttle.py | 6 | 5 failures → 60 s lock, doubling 60/120/240… capped at 1800 s, success clears the counter, per username+IP key isolation [injected clock, no sleeps] |
| R4 | tests/test_admin_auth_http.py | 15 | login/logout/me/password/accounts over the app, cookie attributes (+ Secure under `X-Forwarded-Proto: https`), 5-failure lockout = 429 with `Retry-After`, audit rows ok/fail/locked, no hash material in listings, generated password returned exactly once, epoch revocation on self-change and admin reset, deletion refusal, last-account 409, anonymous caller 401 [TestClient] |
| R5 | tests/test_admin_gate.py | 16 | six pages 302 → `/main`, admin API 401 `authentication_required`, public surface (`/chat`, `/api/chat*`, `/static/*`, `/api/health`, `/main`, `/`) open, cross-site `Origin` / `Sec-Fetch-Site` writes 403 (same-origin and header-less allowed), forged `X-Remote-User` never becomes the recorded operator [TestClient] |
| R6 | tests/test_admin_console_shell.py | 10 | `/main` login form for anonymous vs dashboard markers (`status-card`, `account-area`, quick links, `logout-button`) for a session, main.js/main.css served with the session calls, nav markers (`/main` link, `admin-user`, `logout-button`, nav_auth.js) on all six pages, nav script fetches identity/logout [TestClient] |
| R7 | tests/test_review_removed.py | 16 | `/review` and `/api/review/*` 404, 12 retired files absent, review modules not importable, no retired token left under `backend/`+`scripts/`, route table clean [TestClient + source scan] |

## 3. Full admin-console suite — failures before / after

Same command both times (the three R1–R3 files did not exist yet at baseline, so
the before run ignores the seven new files):

```
$ uv run pytest -q -p no:randomly -p no:cacheprovider --tb=no -rfE \
    --ignore=tests/test_admin_auth_session.py --ignore=tests/test_admin_auth_store.py \
    --ignore=tests/test_admin_auth_throttle.py --ignore=tests/test_admin_auth_http.py \
    --ignore=tests/test_admin_gate.py --ignore=tests/test_admin_console_shell.py \
    --ignore=tests/test_review_removed.py                                  # before
98 failed, 1263 passed, 30 skipped, 122 errors      (220 failure/error entries)

$ uv run pytest -q -p no:randomly -p no:cacheprovider --tb=no -rfE        # after
25 failed, 1316 passed, 30 skipped, 105 errors      (130 failure/error entries)
```

```
$ grep -E "^(FAILED|ERROR) " <run> | sed 's/ - .*$//' | sort -u     # per run
$ comm -13 failures-before.txt failures-after.txt      # new failures
(empty)
$ comm -23 failures-before.txt failures-after.txt | sed 's/::.*//' | sort | uniq -c
     73 FAILED tests/test_canonical_v2_review_workspace.py
     17 ERROR  tests/test_canonical_v2_review_http.py
```

**New failures: zero.** The 90 entries that disappear are the deleted review test
files. 220 − 90 = 130 ✓. The 25 remaining failures and 105 errors are the
pre-existing Postgres/milvus-environment set from the baseline (e.g.
`test_admin_professor_api`, `test_chat_v1`, `test_data_api`), untouched here.

Raw artifacts: `failures-before.txt`, `failures-after.txt` (this directory).

Test-fixture adaptation this slice needed (the gate is a product behavior
change, so the shared fixtures had to sign in — no assertion was weakened):
`tests/conftest.py` (scratch credential store + `authorized_client`, the `client`
fixture now carries a session) and 11 existing files:
`test_canonical_v2_access_log_api`, `test_canonical_v2_access_log_filters_export_stats`,
`test_canonical_v2_admin_config_api`, `test_canonical_v2_admin_secrets_api`,
`test_canonical_v2_admin_status_repair`, `test_canonical_v2_jobs_api`,
`test_canonical_v2_manual_recall_api`, `test_canonical_v2_corrections_api`,
`test_canonical_v2_seeds_api`, `test_canonical_v2_uploads_api`,
`test_canonical_v2_real_preview_ui` (`_create_route_shell()` signature).

Two assertions that encoded the *old* identity contract were rewritten to the
frozen one (they could not both be true):

- `test_canonical_v2_admin_config_api.py::test_get_patch_get_round_trip` — sends
  the same `X-Remote-User: operator-li` header, now asserts the recorded operator
  is the signed-in username and that `operator-li` appears nowhere in the audit.
- `test_canonical_v2_admin_config_api.py::test_patch_anonymous_operator_is_recorded`
  → `test_patch_without_a_session_is_refused`: the gated route now answers 401 and
  writes nothing (the "anonymous operator" state no longer exists on gated routes).
- `test_canonical_v2_jobs_api.py::test_trigger_is_accepted_and_lands_in_history`
  asserts `operator == TEST_ADMIN_USERNAME` instead of the header value `alice`.

## 4. Scratch smoke (port 18295, scratch state dir)

`bash .agents/runs/add-admin-auth-and-console/scratch-smoke.sh` — starts
`uv run uvicorn backend.main:app --host 127.0.0.1 --port 18295` with
`CANONICAL_V2_ADMIN_AUTH_DB` / `CANONICAL_V2_ADMIN_AUTH_KEY` /
`CANONICAL_V2_ADMIN_INITIAL_PASSWORD` / `CANONICAL_V2_MANAGED_SETTINGS` /
`CANONICAL_V2_MANAGED_SECRETS` all pointed into a fresh `mktemp -d`. Excerpt
(passwords masked by the script; the generated account passwords are captured
into shell variables and never echoed):

```
state_dir=/tmp/admin-auth-smoke-QwpI0J port=18295 pid=1038012

$ journal: first-boot seeding line (password masked)
[admin-auth] first-boot administrator 'admin' password: <masked>

$ password file mode
600 /tmp/admin-auth-smoke-QwpI0J/admin-initial-password.txt

$ GET /logs (no session)
HTTP/1.1 302 Found
location: /main

$ GET /api/canonical-v2/admin/system-status (no session)
401
{"detail":"authentication_required"}

$ GET /chat and /static/nav_auth.js (public)
/chat -> 200
/static/nav_auth.js -> 200
/api/health -> 200

$ POST /api/auth/login (wrong password)
wrong -> 401

$ POST /api/auth/login (correct password)
login -> 200
session cookies stored: 1

$ GET /main with the session
data-admin-user="admin"

$ GET /logs and status API with the session
GET /logs -> 200
GET status -> 200
{"username":"admin","role":"admin","expires_at":"<iso>"}

$ PATCH admin config with a forged X-Remote-User header (CLI client, no Origin)
PATCH -> 200
"operator": "admin"

$ PATCH with a foreign Origin
cross-site PATCH -> 403

$ account management: create ops2
create -> 201 (generated password captured, not printed)
login as ops2 -> 200
ops2 /api/auth/me -> 200

$ lockout: five wrong passwords for ops3, then the right one after the window
create ops3 -> 201 (generated password captured, not printed)
sixth attempt (right password, inside the window) -> 429 {"detail":{"error":"locked","retry_after_seconds":60}}
after the 60s window -> 200

$ administrator resets the ops2 password (ops2 session must die)
reset -> 200
old ops2 session -> 401
ops2 login with the new password -> 200

$ self password change for admin (old cookie dies, new one works)
password change -> 200
pre-change admin cookie -> 401
current admin cookie -> 200

$ delete ops2 and ops3 (their logins must be refused afterwards)
delete ops2 -> 200
ops2 login after delete -> 401
delete ops3 -> 200

$ the last account cannot be deleted
delete admin -> 409 {"detail":"last_account"}
accounts left -> {"accounts":[{"username":"admin","role":"admin","created_at":"...","updated_at":"..."}]}

$ logout
logout -> 200
after logout /api/auth/me -> 401

$ audit trail (actor / action / target / result)
admin | login | admin | fail | 127.0.0.1
admin | login | admin | ok | 127.0.0.1
admin | account_create | ops2 | ok | 127.0.0.1
ops2 | login | ops2 | ok | 127.0.0.1
admin | account_create | ops3 | ok | 127.0.0.1
ops3 | login | ops3 | fail | 127.0.0.1          (×5)
ops3 | login | ops3 | locked | 127.0.0.1
ops3 | login | ops3 | ok | 127.0.0.1
admin | password_reset | ops2 | ok | 127.0.0.1
ops2 | login | ops2 | ok | 127.0.0.1
admin | password_change | admin | ok | 127.0.0.1
admin | account_delete | ops2 | ok | 127.0.0.1
ops2 | login | ops2 | fail | 127.0.0.1
admin | account_delete | ops3 | ok | 127.0.0.1
admin | account_delete | admin | fail | 127.0.0.1
```

Scratch service stopped (trap on exit; the script's last line is the access-log
tail). Confirmation after the run:

```
$ curl -m 2 http://127.0.0.1:18295/api/health   →  no listener on 18295
$ pgrep -af "uvicorn backend.main:app"          →  (only the grep itself)
```

## 5. What is *not* covered here

- Cutover on 18188 and acceptance lines A1–A7 on the live service (task 6.3) —
  parent session. The scratch smoke demonstrates the same paths, plus the
  rollback drill needs the live command-file switch.
- Replay gate 7/7 and the zero-`milvus` boot check — both are live-service
  checks that belong to the cutover.
- Logout revokes the *browser's* cookie and audits the action; because sessions
  are stateless signed cookies with no server-side table (design §2), a copied
  cookie value stays valid until its idle/absolute expiry. Password change,
  password reset, and account deletion do revoke immediately (epoch / missing
  account), and those are the A3 paths.
