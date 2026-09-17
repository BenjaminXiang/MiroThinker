# Tasks: add-admin-auth-and-console

Status legend: `[ ]` todo · `[x]` done · slice owner is the single active writer.

## 1. Foundations (RED → GREEN)

- [ ] 1.1 `apps/admin-console/backend/services/admin_auth.py`: store open/create,
      schema v1, scrypt hash/verify, account CRUD, epoch bump, audit append,
      seeding (idempotent + env overrides).
- [ ] 1.2 Session codec: sign/verify, expiry + idle refresh, epoch check,
      key file management.
- [ ] 1.3 Login throttler (username+IP, 5 fails → 60 s, doubling, audit).
- [ ] 1.4 Tests: `tests/test_admin_auth_store.py`,
      `tests/test_admin_auth_session.py`, `tests/test_admin_auth_throttle.py`
      (RED first, then GREEN).

## 2. HTTP surface

- [ ] 2.1 `apps/admin-console/backend/api/admin_auth.py` with the eight
      endpoints from design §4; `GET /api/auth/me`; account list never returns
      hashes.
- [ ] 2.2 Gate middleware in `main.py` per design §5 (page 302 / API 401 /
      same-origin on writes); `request.state.admin_user`; `_operator()` rewrite.
- [ ] 2.3 Tests: `tests/test_admin_auth_http.py` (login/logout/me/password/
      accounts), `tests/test_admin_gate.py` (page vs API, public surface, CSRF
      origin check, forged `X-Remote-User` ignored).

## 3. Console shell

- [ ] 3.1 `static/main.html` + `main.js` + `main.css`: login form / dashboard
      (status card, quick links, account area, user + logout).
- [ ] 3.2 Shared nav on the six pages gains `首页` + current user + logout.
- [ ] 3.3 Tests: `tests/test_admin_console_shell.py` (page served, gate
      redirect, nav markers present).

## 4. `/review` retirement

- [ ] 4.1 Delete review page/API/service/static/tests; drop `include_review`
      wiring; remove 18189 references.
- [ ] 4.2 Tests: route absence (`/review`, `/api/review/*` → 404) and no imports
      of the deleted modules remain.

## 5. Delivery & docs

- [ ] 5.1 `deploy/` seeding note + HTTPS advice line; `install.sh` prints the
      first-boot password location.
- [ ] 5.2 OpenSpec change-ledger row; acceptance.md evidence filled.
- [ ] 5.3 Human plan/log/index updates (both repo trees).

## 6. Verification

- [ ] 6.1 Targeted suites green; before/after failure diff on the admin-console
      suite recorded in `.agents/runs/add-admin-auth-and-console/`.
- [ ] 6.2 Scratch-port smoke: login → dashboard → account ops → gate on page +
      API → forged header rejected → logout; stop scratch service.
- [ ] 6.3 Cutover 18188 (live tree fast-forward + restart) + the seven
      acceptance lines from acceptance.md, including rollback drill.
