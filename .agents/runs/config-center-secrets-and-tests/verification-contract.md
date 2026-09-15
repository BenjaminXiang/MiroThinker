# Verification Contract — config-center-secrets-and-tests (P13)

Slice: P13 / requirement R16 (revised 2026-09-15). Baseline: `codex/canonical-v2-s12a-ready` @ `2fe4c16c`.
Worktree: `.worktrees/config-center-secrets`. Runtime scope: scratch config dir + scratch port **18297**.
No production config/key file is written; no service is restarted.

## 0. RED assertions (must fail before the implementation lands)

| # | RED assertion | Falsified by | Test file |
|---|---|---|---|
| R1 | A secret value written through the admin API is **never** returned by any response body; the read endpoint returns only `configured` + a mask whose tail is ≤ 4 characters and whose head is ≤ 3 characters | response contains the sentinel in any casing/encoding | `tests/test_canonical_v2_admin_secrets_api.py::test_read_endpoint_never_returns_plaintext` |
| R2 | The managed secrets file is created mode **0600** and replaced atomically (no temp file left, inode replaced) | `stat().st_mode & 0o777 != 0o600`, or `os.replace` not used | `tests/test_managed_secrets_store.py::test_atomic_write_is_0600_and_leaves_no_temp_files` |
| R3 | No plaintext secret reaches the audit log, the response of a connectivity test, or the service log records produced by the request path | audit line contains the sentinel | `tests/test_managed_secrets_store.py::test_audit_records_never_contain_plaintext` |
| R4 | Connectivity test accepts **unsaved** values from the request body (test-before-save) and performs exactly **one** minimal outbound call per invocation | transport call count != 1, or stored value used when a body value is supplied | `tests/test_canonical_v2_connection_tests.py::test_presave_value_is_used_and_one_call_only` |
| R5 | Rate limiting rejects the (N+1)-th test for one connection inside the window with HTTP 429 + `retry_after_seconds`, without calling the transport again | second immediate call returns 200, or transport called twice | `tests/test_canonical_v2_admin_secrets_api.py::test_connection_test_is_rate_limited` |
| R6 | Setting a key is a **startup** read, not a hot read: the running process does not pick the value up until the bootstrap runs; the API response carries an explicit restart requirement | POST /secrets then immediate in-process resolution returns the new value | `tests/test_canonical_v2_admin_secrets_api.py::test_set_requires_restart_and_is_not_hot_read` |
| R7 | Overwrite and clear paths both work: clear removes the value (mask becomes null, `configured=false`), overwrite changes the mask tail | clear leaves old material, or overwrite keeps the old mask | `tests/test_canonical_v2_admin_secrets_api.py::test_clear_and_overwrite_paths` |
| R8 | Startup bootstrap applies file-owned secrets/flags to the process environment **only when the env var is unset** (env stays the winner) and returns a receipt with counts only | env var overwritten, or receipt contains a value | `tests/test_managed_runtime_bootstrap.py::test_bootstrap_never_overrides_existing_env` |
| R9 | A connection test failure is reported as `ok=false` + error class + latency, and the response never carries a response body or credential | detail contains the sentinel or an upstream body | `tests/test_canonical_v2_connection_tests.py::test_failure_reports_status_without_body` |

## 1. Scope of verification

- **Unit** — masking, file mode/atomicity, no-plaintext (responses, audit, logs), rate limiting,
  connectivity test with a mock transport (success / HTTP error / transport error / timeout),
  test-before-save, clear + overwrite, restart-not-hot-reload, bootstrap precedence.
- **HTTP surface** — the three new admin routes on the existing V2 shell via `TestClient`.
- **E2E (scratch)** — scratch config dir + scratch port 18297, real HTTP: set fake key → masked echo →
  connectivity test (mock or ≤1 real call per connection) → clear → set again; W1 features (`/admin`,
  `/config`, `/system-status`) unchanged.
- **Exit check vs R9 baseline** — this slice does not touch retrieval: no replay/probe rerun is required;
  the evidence is "existing admin-console suite failure set unchanged + new tests green".

## 2. Explicit non-goals (guard rails)

- No hot reload of secrets or flags; no service restart performed by the page or by this slice.
- No write to a production key file (`.bocha_api_key`, `.serper_api_key`, `.deepseek_api_key`, …) —
  read-only there; the managed file is a new, separate path.
- Real-endpoint calls from automated tests: **0**. Any real call is manual, counted, and recorded.
- Secrets never enter a test fixture: every test value is a locally generated fake.

## 3. Evidence to produce

- `verification.md` — layered report (new tests / pre-existing suites / E2E).
- `e2e-scratch-18297.md` — verbatim curl transcript + counts.
- `full-suite-before.txt` / `full-suite-after.txt` — admin-console suite failure-set comparison.
