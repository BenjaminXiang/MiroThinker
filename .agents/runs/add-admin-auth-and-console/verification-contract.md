# Verification contract: add-admin-auth-and-console

TDD boundary: RED artifacts come from this contract + the two spec deltas; a
unit test alone is not sufficient GREEN evidence for the HTTP/gate surface —
the gate must additionally be demonstrated on a live scratch service and then on
18188 (acceptance.md).

## RED list (write first, watch fail for the right reason)

New tests (fixture source in brackets):

| # | Test file | Locks |
|---|---|---|
| R1 | `tests/test_admin_auth_store.py` | scrypt hash/salt per user, no plaintext, epoch bump, account CRUD, audit append, path override, seeding idempotence + 0600 file [constructed store] |
| R2 | `tests/test_admin_auth_session.py` | sign/verify, tampered payload rejected, expiry (idle + absolute), epoch mismatch rejected, account-missing rejected, Secure-flag logic [constructed key + store] |
| R3 | `tests/test_admin_auth_throttle.py` | 5 fails → 60 s lock, doubling, success clears, audit rows for ok/fail/locked [constructed clock] |
| R4 | `tests/test_admin_auth_http.py` | login/logout/me/password/accounts endpoints over the app; account listing carries no hashes; last-account deletion refused [TestClient] |
| R5 | `tests/test_admin_gate.py` | six pages 302 `/main`; `/api/canonical-v2/*` 401; `/chat` + `/api/chat*` + `/static/*` + `/api/health` public; cross-site write refused; forged `X-Remote-User` ignored for operator [TestClient] |
| R6 | `tests/test_admin_console_shell.py` | `/main` login form vs dashboard markers; nav markers on the six pages [TestClient] |
| R7 | `tests/test_review_removed.py` | `/review` and `/api/review/*` 404; no admin-console module imports the review package [TestClient + import scan] |

Regression guard: the existing admin-console suite's failure set must not grow
(before/after diff recorded in `verification.md`).

## GREEN evidence plan

1. Targeted suites (R1–R7) green in the feature worktree.
2. Admin-console full suite: before/after failure diff, zero new failures.
3. Scratch smoke (own port + scratch auth DB): login → dashboard → account ops →
   gate on a page and an API → forged header rejected → logout; screenshots/log
   excerpt into `verification.md`.
4. Cutover: live tree fast-forward + restart; A1–A7 from acceptance.md executed
   on 18188, plus replay gate 7/7 and zero `milvus` in the boot log.

## Fixture/clock rules

- Tests never touch the real state directory: `CANONICAL_V2_ADMIN_AUTH_DB`,
  `CANONICAL_V2_ADMIN_AUTH_KEY`, `CANONICAL_V2_ADMIN_INITIAL_PASSWORD` point at
  `tmp_path` values.
- Expiry/throttle tests inject a clock; no test sleeps longer than 2 s.
- The live 18188 service is never restarted by tests.
