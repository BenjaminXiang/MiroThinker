# Acceptance: config-center-secrets-and-tests

## A. Contract-level (from R16, 2026-09-15 revised)

| # | Acceptance criterion | Evidence |
|---|---|---|
| A1 | A key can be **set from the page** and lands in the managed key file | E2E `PATCH /secrets` → file exists, mode 0600, value present (read only by the test, never echoed) |
| A2 | The page/API only ever shows a **mask + configured flag** | `test_read_endpoint_never_returns_plaintext`, E2E transcript |
| A3 | Overwrite and clear both work | `test_clear_and_overwrite_paths`, E2E |
| A4 | The value is picked up **at service startup**, not hot | `test_set_requires_restart_and_is_not_hot_read`, bootstrap test, restart hint in the page |
| A5 | Each connection has a **connectivity test** that works **before saving** | `test_presave_value_is_used_and_one_call_only`, E2E |
| A6 | Tests are **rate-limited** server-side | `test_connection_test_is_rate_limited` (429 + retry_after, transport not called) |
| A7 | Test results record **status + latency only** | `test_failure_reports_status_without_body`, response schema |
| A8 | New switches are in the managed list with a documented page-suitability judgement | `serving` section + design §6 table + config API test |
| A9 | No plaintext in responses, audit, logs | R1/R3 tests + E2E grep evidence |
| A10 | No regression of the W1 surfaces or the existing suite | before/after failure-set diff = ∅ |

## B. Non-functional

| # | Criterion | Evidence |
|---|---|---|
| B1 | Secret file mode is exactly 0600 | `stat` assertion in store test + E2E |
| B2 | Atomic write: no temp residue, atomic replace | store test |
| B3 | Bootstrap never overwrites an existing env var | bootstrap test |
| B4 | Bootstrap is fail-open (missing/corrupt file = no-op) | bootstrap test |
| B5 | The live 18188 service is untouched (no restart, no env change) | E2E runs on scratch port 18297; run note |

## C. Out of scope (not acceptance blockers)

- Real Bocha/Serper/rerank/embedding/LLM calls in automated tests.
- Hot reload, rotation scheduling, multi-host secret distribution.
- Deploying the slice to the live service (needs replay gate + user go-ahead; recorded as a gap).

## D. Exit comparison against the R9 baseline

This slice changes no retrieval, fusion, rerank, planner or answer path; `apply_managed_runtime_config`
projects values only when the operator has explicitly written them into the managed file. The baseline
exit evidence (`baseline-20260915`: replay 7/7 + two verbatim probes + TTFT) therefore is not re-run
here; the required evidence is "no regression + new behaviour verified", produced by the admin-console
suite diff and the scratch E2E.
