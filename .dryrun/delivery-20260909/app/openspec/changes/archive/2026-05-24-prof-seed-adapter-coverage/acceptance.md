# Acceptance Evidence: prof-seed-adapter-coverage

Status: verified. Coverage guard, named adapter additions, blocked-outcome
classification, targeted tests, and the current 20-row real-seed E2E matrix are
complete for this change.

P4 completion evidence is now present: every requirement below has
current-session evidence, and the 20-row real-seed E2E matrix is recorded.

## Requirements

| Requirement | Evidence status | Evidence |
|---|---|---|
| Real seed coverage guard | Verified | `apps/miroflow-agent/scripts/audit_professor_seed_adapter_coverage.py` added. `cd apps/miroflow-agent && uv run --no-sync pytest tests/scripts/test_audit_professor_seed_adapter_coverage.py ... -q` passed in the 11-test targeted suite. `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/audit_professor_seed_adapter_coverage.py` exited 0 and emitted all 20 rows with 0 missing. |
| Current seed inventory coverage | Verified | Final `miroflow_real` matrix: seeds 6-15, 18-21, and 24 preview-success with `diagnostic_profile_count=3`; seed 5 preview-failed as `fetch_blocked` with issue `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663`; seeds 25-28 preview-failed as approved `fetch_blocked` with per-seed issues. No seed remains unclassified. |
| SUIT/SZIIT named adapter coverage | Verified | `suit-sziit-teacher-family` registered for `suit-sz.edu.cn` / `zd.suit-sz.edu.cn` `/jyjx/jsfc...` pages. `uv run --no-sync pytest tests/data_agents/professor/test_adapter_resolution.py tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_uses_suit_sziit_adapter_for_teacher_list -q` passed with 3 tests. Real seed 24 preview E2E passed: adapter `suit-sziit-teacher-family`, `diagnostic_profile_count=3`, terminal `success`, pipeline_run `succeeded`, no new issue outcome. |
| UESTC/SIAS approved outcome | Verified | `run_single_seed` now detects SIAS `/rcpy/dsjs1/` tokenized 202 challenge pages before `adapter_missing` and persists `fetch_blocked` evidence. Real seed preview runs for 25-28 all ended `failure_class=fetch_blocked`, `last_run_status=failure`, pipeline run `failed`, and each row has an independent `pipeline_issue` with `http_status=202`, `response_shape=tokenized_202_challenge`, `response_chinese_char_count=0`, `response_anchor_count=0`, `fetch_method=direct_no_env`, and seed identity. |
| P4 E2E evidence matrix | Verified | The row-level matrix below includes all 20 current `professor_seed` rows with resolver result, trigger mode, terminal status, item counts, pipeline status, and issue outcome. |
| Adapter availability is row-level and named | Verified | Coverage guard evaluates each seed row through `resolve_seed_adapter_name()` and treats generic parser success without a resolver result as missing. SUIT seed 24 now resolves by name. `cd apps/admin-console && DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test uv run --no-sync pytest tests/test_seeds_api.py -q` passed 27 tests, including adapter-missing trigger behavior. |
| Fetch-blocked evidence includes response shape | Verified for SIAS | Tests and real seed runs show `pipeline_issue.evidence_snapshot` includes seed id, school, department, seed URL, trigger mode, limit, fetch method, HTTP status, response char count, Chinese char count, anchor count, response shape, and `failure_class`. Browser diagnostic is included by helper when available; real direct-no-env SIAS runs did not use a browser diagnostic. |

## Required Matrix Columns

Each final evidence row MUST include:

```text
seed_id, school, department, seed_url, resolver_result, trigger_mode, command,
terminal_status, items_processed, items_failed, pipeline_run_status,
pipeline_issue_outcome
```

## Final 20-Row E2E Matrix

All rows used `trigger_mode=preview`, `limit=3`, and the command family recorded
in `.agents/runs/prof-seed-adapter-coverage/verification.md`.

| seed_id | resolver_result | command_ref | terminal_status | items processed/failed | pipeline_run_status | pipeline_issue_outcome |
|---:|---|---|---|---:|---|---|
| 5 | `szu-teacher-family` | seed 5 single preview command | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663` |
| 6 | `cuhk_teacher_search` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 7 | `cuhk_teacher_search` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 8 | `sigs_teacher_api` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 9 | `sustech-roster` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 10 | `szu-teacher-family` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 11 | `szu-teacher-family` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 12 | `szu-teacher-family` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 13 | `szu-teacher-family` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 14 | `szu-teacher-family` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 15 | `szu-teacher-family` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 18 | `szu-teacher-family` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 19 | `hitsz-college-teacher-family` | seed 19 single preview command | `success` | 0 / 0 | `succeeded` | none |
| 20 | `hitsz-college-teacher-family` | seed 20-21 preview command | `success` | 0 / 0 | `succeeded` | none |
| 21 | `szu-teacher-family` | seed 20-21 preview command | `success` | 0 / 0 | `succeeded` | none |
| 24 | `suit-sziit-teacher-family` | covered-seed preview batch | `success` | 0 / 0 | `succeeded` | none |
| 25 | none | SIAS preview batch | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `878d0341-1de6-4b0a-aa68-3a90e032022e` |
| 26 | none | SIAS preview batch | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `588f35d0-2756-471a-a414-c1462b5e96a1` |
| 27 | none | SIAS preview batch | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `399136c7-4a77-4b53-9896-a7b9351be8db` |
| 28 | none | SIAS preview batch | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `9efd935b-4ed7-4cbe-a720-70471dd2ac2b` |
