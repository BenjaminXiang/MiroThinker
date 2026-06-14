# Verification: prof-seed-adapter-coverage

Status: verified. Coverage guard, adapter implementation, blocked-outcome
classification, targeted tests, and the final real-seed E2E matrix are complete.

## 2026-05-24 Change Creation

Commands:

```bash
openspec new change prof-seed-adapter-coverage
openspec status --change prof-seed-adapter-coverage --json
openspec instructions proposal --change prof-seed-adapter-coverage --json
openspec instructions design --change prof-seed-adapter-coverage --json
openspec instructions specs --change prof-seed-adapter-coverage --json
openspec instructions tasks --change prof-seed-adapter-coverage --json
```

Result:

- Change scaffold created at `openspec/changes/prof-seed-adapter-coverage/`.
- Proposal, design, specs, tasks, and acceptance skeleton were created.

## Required Implementation Verification

The following checks were required before P4 could be complete and are recorded
as executed in later sections of this file:

```bash
openspec validate prof-seed-adapter-coverage --strict
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python apps/miroflow-agent/scripts/audit_professor_seed_adapter_coverage.py
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/<dedicated-test-db> \
  uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q
uv run --no-sync pytest tests/data_agents/professor/test_school_adapters.py \
  tests/data_agents/professor/test_roster_validation.py -q
uv run --no-sync ruff check src/data_agents/professor \
  tests/postgres/test_run_single_seed.py \
  tests/data_agents/professor/test_school_adapters.py \
  tests/data_agents/professor/test_roster_validation.py
```

No implementation E2E has run yet.

## 2026-05-24 Coverage Guard Implementation

Changed files:

- `apps/miroflow-agent/scripts/audit_professor_seed_adapter_coverage.py`
- `apps/miroflow-agent/tests/scripts/test_audit_professor_seed_adapter_coverage.py`
- `openspec/changes/prof-seed-adapter-coverage/tasks.md`
- `openspec/changes/prof-seed-adapter-coverage/acceptance.md`
- `.agents/runs/prof-seed-adapter-coverage/verification.md`

Red command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/scripts/test_audit_professor_seed_adapter_coverage.py -q
```

Red result:

- Exit code: 1.
- Expected failure: both tests failed with `FileNotFoundError` because
  `scripts/audit_professor_seed_adapter_coverage.py` did not exist.

Green command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/scripts/test_audit_professor_seed_adapter_coverage.py -q
```

Green result:

- Exit code: 0.
- Result: `2 passed in 9.47s`.
- Notes: pytest ran with xdist; inline-snapshot reported disabled under xdist.
  Coverage emitted repeated `No data was collected` warnings, but the targeted
  tests passed.

Implemented behavior:

- The guard loads all `professor_seed` rows and emits a tab-separated matrix
  with `seed_id`, `school`, `department`, `seed_url`, `last_run_status`,
  `resolver_result`, `coverage_state`, `diagnostic_status`, and
  `issue_id_or_reason`.
- A seed is `resolver_covered` when `resolve_seed_adapter_name()` returns a
  named path.
- A seed is `approved_blocked` when a latest runner `pipeline_issue` records
  `failure_class='fetch_blocked'` for that seed id.
- A seed is `missing` when neither condition is true, and the guard exits
  non-zero if any missing row exists.

Interim checks:

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check scripts/audit_professor_seed_adapter_coverage.py tests/scripts/test_audit_professor_seed_adapter_coverage.py
```

Result: exit code 0, `All checks passed!`.

```bash
openspec validate prof-seed-adapter-coverage --strict
```

Result: exit code 0, `Change 'prof-seed-adapter-coverage' is valid`.

## 2026-05-24 SUIT/SZIIT Adapter Implementation

Changed files:

- `apps/miroflow-agent/src/data_agents/professor/roster.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_adapter_resolution.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py`
- `openspec/changes/prof-seed-adapter-coverage/tasks.md`
- `openspec/changes/prof-seed-adapter-coverage/acceptance.md`
- `.agents/runs/prof-seed-adapter-coverage/verification.md`

Red command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_adapter_resolution.py tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_uses_suit_sziit_adapter_for_teacher_list -q
```

Red result:

- Exit code: 1.
- Expected failures: SUIT resolver returned `None` for both seed URL variants,
  and the roster extraction path fell through to the generic fallback.

Green command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_adapter_resolution.py tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_uses_suit_sziit_adapter_for_teacher_list -q
```

Green result:

- Exit code: 0.
- Result: `3 passed in 9.34s`.

Interim coverage guard command:

```bash
cd apps/miroflow-agent
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python scripts/audit_professor_seed_adapter_coverage.py
```

Interim coverage guard result:

- Exit code: 1.
- Matrix rows: 20.
- Seed 24 result: `suit-sziit-teacher-family`, `resolver_covered`.
- Remaining missing rows: seeds 25, 26, 27, 28 UESTC/SIAS.

Seed 24 preview E2E command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python - <<'PY'
import json
from dataclasses import asdict
from src.data_agents.professor.seed_runner import run_single_seed
from src.data_agents.storage.postgres.connection import connect

result = run_single_seed(24, trigger_mode="preview", limit=3, timeout=30.0)
print("result=" + json.dumps(asdict(result), ensure_ascii=False, default=str, sort_keys=True))
with connect() as conn:
    run_row = conn.execute(
        """
        SELECT run_id::text AS run_id, status, items_processed, items_failed,
               run_scope, error_summary
          FROM pipeline_run
         WHERE run_id = %s
        """,
        (result.run_id,),
    ).fetchone()
    seed_row = conn.execute(
        """
        SELECT id, last_run_status, last_run_at
          FROM professor_seed
         WHERE id = 24
        """
    ).fetchone()
    issue_rows = conn.execute(
        """
        SELECT issue_id::text AS issue_id, stage, description, evidence_snapshot
          FROM pipeline_issue
         WHERE evidence_snapshot->>'seed_id' = '24'
         ORDER BY reported_at DESC
         LIMIT 3
        """
    ).fetchall()
print("seed=" + json.dumps(seed_row, ensure_ascii=False, default=str, sort_keys=True))
print("run=" + json.dumps(run_row, ensure_ascii=False, default=str, sort_keys=True))
print("issues=" + json.dumps(issue_rows, ensure_ascii=False, default=str, sort_keys=True))
PY
```

Seed 24 preview E2E result:

- Exit code: 0.
- Result: `status=success`, `failure_class=success`,
  `adapter_name=suit-sziit-teacher-family`, `items_processed=0`,
  `items_failed=0`, `run_id=4c7a850d-734e-499a-ac80-e28e70782396`.
- Seed row: `last_run_status=success`.
- Pipeline run: `status=succeeded`, `items_processed=0`, `items_failed=0`,
  `run_scope.diagnostic_profile_count=3`, `run_scope.written_profile_count=0`,
  `trigger_mode=preview`, `limit=3`.
- Issue outcome: no new seed-24 failure issue from the successful preview.
  Existing stale `adapter_missing` issue remains visible from an earlier run.

Rejected evidence:

- A prior seed 24 preview command exited 1 after the run returned because it
  attempted to print a slots dataclass through `result.__dict__`. That command
  is not counted as passing evidence; the `asdict()` command above is the
  passing evidence.

## 2026-05-24 UESTC/SIAS Fetch-Blocked Implementation

Changed files:

- `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`
- `apps/miroflow-agent/tests/postgres/test_run_single_seed.py`
- `openspec/changes/prof-seed-adapter-coverage/tasks.md`
- `openspec/changes/prof-seed-adapter-coverage/acceptance.md`
- `.agents/runs/prof-seed-adapter-coverage/verification.md`

Red command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test \
  uv run --no-sync pytest \
  tests/postgres/test_run_single_seed.py::test_sias_tokenized_202_page_builds_fetch_blocked_evidence \
  tests/postgres/test_run_single_seed.py::test_run_single_seed_persists_fetch_blocked_for_uestc_sias_challenge -q
```

Red result:

- Exit code: 1.
- Expected failure: seed runner had no SIAS response-shape helper and no known
  blocked-seed detector.

Green command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test \
  uv run --no-sync pytest \
  tests/postgres/test_run_single_seed.py::test_sias_tokenized_202_page_builds_fetch_blocked_evidence \
  tests/postgres/test_run_single_seed.py::test_run_single_seed_persists_fetch_blocked_for_uestc_sias_challenge -q
```

Green result:

- Exit code: 0.
- Result: `2 passed in 3.84s`.

Escaped-defect regression:

- Real seed 25-28 preview initially wrote a `fetch_blocked` issue only for seed
  25 because `pipeline_issue` uniqueness deduped identical descriptions across
  same-school rows.
- Pattern repair invariant: every seed-level terminal failure needs issue
  identity scoped by seed id.

Regression red command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test \
  uv run --no-sync pytest \
  tests/postgres/test_run_single_seed.py::test_sias_fetch_blocked_issue_is_persisted_per_seed -q
```

Regression red result:

- Exit code: 1.
- Expected failure: second same-school SIAS seed had zero issue rows.

Regression green command:

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test \
  uv run --no-sync pytest \
  tests/postgres/test_run_single_seed.py::test_sias_fetch_blocked_issue_is_persisted_per_seed \
  tests/postgres/test_run_single_seed.py::test_run_single_seed_deduplicates_repeated_open_adapter_missing_issue \
  tests/postgres/test_run_single_seed.py::test_run_single_seed_persists_fetch_blocked_for_uestc_sias_challenge -q
```

Regression green result:

- Exit code: 0.
- Result: `3 passed in 3.82s`.

Pattern-fix report:

- Reported case fixed: yes.
- Defect class: L6 Evidence / Provenance Violation + C1 Test-Matrix Gap.
- Invariant enforced: seed-runner issue descriptions are seed-scoped while
  evidence keeps explicit seed identity.
- Sibling search: scoped to professor seed runner and pipeline_issue uniqueness;
  no schema change made.

Real seed 25-28 preview E2E command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python - <<'PY'
import json
from dataclasses import asdict
from src.data_agents.professor.seed_runner import run_single_seed
from src.data_agents.storage.postgres.connection import connect

seed_ids = [25, 26, 27, 28]
results = []
for seed_id in seed_ids:
    result = run_single_seed(seed_id, trigger_mode="preview", limit=3, timeout=30.0)
    with connect() as conn:
        issue_row = conn.execute(
            """
            SELECT issue_id::text AS issue_id, stage, description, evidence_snapshot
              FROM pipeline_issue
             WHERE evidence_snapshot->>'seed_id' = %s
               AND evidence_snapshot->>'failure_class' = 'fetch_blocked'
             ORDER BY reported_at DESC
             LIMIT 1
            """,
            (str(seed_id),),
        ).fetchone()
        run_row = conn.execute(
            """
            SELECT run_id::text AS run_id, status, items_processed, items_failed,
                   run_scope, error_summary
              FROM pipeline_run
             WHERE run_id = %s
            """,
            (result.run_id,),
        ).fetchone()
    results.append({"result": asdict(result), "run": run_row, "issue": issue_row})
print(json.dumps(results, ensure_ascii=False, default=str, indent=2, sort_keys=True))
PY
```

Real seed 25-28 preview E2E result:

| seed_id | run_id | terminal status | pipeline_run | issue_id | response_char_count |
|---|---|---|---|---|---|
| 25 | `b08b96ac-c4fa-4a40-8dc0-32bc3b7b3bca` | `failure` / `fetch_blocked` | `failed` | `878d0341-1de6-4b0a-aa68-3a90e032022e` | 2528 |
| 26 | `d675f799-fd17-4c77-b926-04430682125c` | `failure` / `fetch_blocked` | `failed` | `588f35d0-2756-471a-a414-c1462b5e96a1` | 2419 |
| 27 | `d66ed224-5901-4137-9435-15d1cb6e6250` | `failure` / `fetch_blocked` | `failed` | `399136c7-4a77-4b53-9896-a7b9351be8db` | 2432 |
| 28 | `08065132-d1d9-436a-981f-7b158f3b205f` | `failure` / `fetch_blocked` | `failed` | `9efd935b-4ed7-4cbe-a720-70471dd2ac2b` | 2578 |

All four issue rows include:

```text
failure_class=fetch_blocked, fetch_method=direct_no_env, http_status=202,
response_anchor_count=0, response_chinese_char_count=0,
response_shape=tokenized_202_challenge, trigger_mode=preview, limit=3,
seed_id, school, department, seed_url, run_id
```

## 2026-05-24 Current Coverage Matrix

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python scripts/audit_professor_seed_adapter_coverage.py
```

Result:

- Exit code: 0.
- Rows: 20.
- Resolver-covered rows: 16.
- Approved-blocked rows: 4.
- Missing rows: 0.

Current row classification:

| seed_id | coverage_state | diagnostic_status | issue_id_or_reason |
|---|---|---|---|
| 5 | `resolver_covered` | `adapter:szu-teacher-family` | `resolver:szu-teacher-family` |
| 6 | `resolver_covered` | `adapter:cuhk_teacher_search` | `resolver:cuhk_teacher_search` |
| 7 | `resolver_covered` | `adapter:cuhk_teacher_search` | `resolver:cuhk_teacher_search` |
| 8 | `resolver_covered` | `adapter:sigs_teacher_api` | `resolver:sigs_teacher_api` |
| 9 | `resolver_covered` | `adapter:sustech-roster` | `resolver:sustech-roster` |
| 10 | `resolver_covered` | `adapter:szu-teacher-family` | `resolver:szu-teacher-family` |
| 11 | `resolver_covered` | `adapter:szu-teacher-family` | `resolver:szu-teacher-family` |
| 12 | `resolver_covered` | `adapter:szu-teacher-family` | `resolver:szu-teacher-family` |
| 13 | `resolver_covered` | `adapter:szu-teacher-family` | `resolver:szu-teacher-family` |
| 14 | `resolver_covered` | `adapter:szu-teacher-family` | `resolver:szu-teacher-family` |
| 15 | `resolver_covered` | `adapter:szu-teacher-family` | `resolver:szu-teacher-family` |
| 18 | `resolver_covered` | `adapter:szu-teacher-family` | `resolver:szu-teacher-family` |
| 19 | `resolver_covered` | `adapter:hitsz-college-teacher-family` | `resolver:hitsz-college-teacher-family` |
| 20 | `resolver_covered` | `adapter:hitsz-college-teacher-family` | `resolver:hitsz-college-teacher-family` |
| 21 | `resolver_covered` | `adapter:szu-teacher-family` | `resolver:szu-teacher-family` |
| 24 | `resolver_covered` | `adapter:suit-sziit-teacher-family` | `resolver:suit-sziit-teacher-family` |
| 25 | `approved_blocked` | `fetch_blocked` | `878d0341-1de6-4b0a-aa68-3a90e032022e` |
| 26 | `approved_blocked` | `fetch_blocked` | `588f35d0-2756-471a-a414-c1462b5e96a1` |
| 27 | `approved_blocked` | `fetch_blocked` | `399136c7-4a77-4b53-9896-a7b9351be8db` |
| 28 | `approved_blocked` | `fetch_blocked` | `9efd935b-4ed7-4cbe-a720-70471dd2ac2b` |

## 2026-05-24 Current-Seed E2E Repair: SZU CSSE Seed 5

Root cause:

- Seed 5 resolved to `szu-teacher-family`, but preview E2E returned
  `parser_low_quality`.
- Fetch diagnostics showed the default fetch path returned cached reader
  diagnostics as usable HTML:
  `Warning: Target URL returned error 412: Precondition Failed`.
- After that cache was rejected, browser fallback returned an empty DOM
  (`<html><head></head><body></body></html>`) and the old logic also treated
  that as usable parser input.

Red commands:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_ignores_reader_error_cached_html \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_reader_does_not_return_reader_error_cache -q
```

Result: exit code 1. Both tests failed because bad reader cache was returned as
`fetch_method=cache`.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_skips_empty_browser_dom_after_blocked_direct -q
```

Result: exit code 1. The test failed because empty browser DOM was returned as
`fetch_method=browser`.

Green command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_skips_empty_browser_dom_after_blocked_direct \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_ignores_reader_error_cached_html \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_reader_does_not_return_reader_error_cache -q
```

Result: exit code 0, `3 passed in 9.11s`.

Seed 5 preview E2E command:

```bash
cd apps/miroflow-agent
timeout 120s env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python - <<'PY'
from dataclasses import asdict
from src.data_agents.professor.seed_runner import run_single_seed

print(asdict(run_single_seed(5, trigger_mode="preview", limit=3, timeout=30.0)))
PY
```

Result:

- Exit code: 0.
- Run id: `8e9eb13b-f3b7-49c6-b0fd-213227a93268`.
- Terminal status: `failure`, `failure_class=fetch_blocked`.
- Pipeline run status: `failed`, `items_processed=0`, `items_failed=1`.
- Issue: `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663`.
- Issue evidence includes `failed_fetch_urls` with seed 5 URL and source status
  `fetch_failed`.

## 2026-05-24 Current-Seed E2E Repair: HITSZ Seeds 19-20

Root cause:

- Seed 19 roster discovery was fast and parsed 96 candidates from cached
  `http://cs.hitsz.edu.cn/szll1.htm` HTML.
- The first HITSZ profile links used `http://faculty.hitsz.edu.cn/...`.
- Direct curl evidence showed port 80 timed out for
  `http://faculty.hitsz.edu.cn/chenkehai`, while
  `https://faculty.hitsz.edu.cn/dengxiang` returned a usable profile page
  quickly.
- The HITSZ college adapter now normalizes `faculty.hitsz.edu.cn` profile links
  from HTTP to HTTPS.

Rejected evidence:

- `timeout 120s ... run_single_seed(19, preview, limit=3)` exited 124 before
  the HTTPS normalization fix and left run
  `c5dcc128-b98b-4920-872e-1f52219527ad` as `running`; that run was manually
  closed as failed with `operator_interrupted_after_outer_e2e_timeout`.
- A profile-level diagnostic command also exited 124 and produced a Playwright
  driver `EPIPE` after timeout; it is not counted as passing evidence.

Red command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_supports_hitsz_college_faculty_links -q
```

Red result:

- Exit code: 1.
- Expected failure: the test expected HTTPS normalization but the adapter still
  returned `http://faculty.hitsz.edu.cn/wanjia`.

Green command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_supports_hitsz_college_faculty_links -q
```

Green result: exit code 0, `1 passed in 9.26s`.

Seed 19 preview E2E command:

```bash
cd apps/miroflow-agent
timeout 120s env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python - <<'PY'
from dataclasses import asdict
from src.data_agents.professor.seed_runner import run_single_seed

print(asdict(run_single_seed(19, trigger_mode="preview", limit=3, timeout=15.0)))
PY
```

Result:

- Exit code: 0.
- Resolver: `hitsz-college-teacher-family`.
- Run id: `1e8464b4-4a4b-4de4-ac69-3dc11f84e7e5`.
- Terminal status: `success`, `failure_class=success`.
- Pipeline run status: `succeeded`, `diagnostic_profile_count=3`,
  `items_processed=0`, `items_failed=0`.

Seed 20-21 preview E2E command:

```bash
cd apps/miroflow-agent
timeout 120s env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python - <<'PY'
from dataclasses import asdict
from src.data_agents.professor.seed_runner import run_single_seed

print([asdict(run_single_seed(seed_id, trigger_mode="preview", limit=3, timeout=15.0)) for seed_id in (20, 21)])
PY
```

Result:

| seed_id | resolver | run_id | terminal status | pipeline_run |
|---:|---|---|---|---|
| 20 | `hitsz-college-teacher-family` | `b39c0453-2821-4ce7-ae18-662d82fb36a4` | `success` | `succeeded`, `diagnostic_profile_count=3` |
| 21 | `szu-teacher-family` | `dd1574da-5f06-45fc-acac-d3387b95fc36` | `success` | `succeeded`, `diagnostic_profile_count=3` |

## 2026-05-24 Current-Seed E2E Matrix Completion

Covered-seed preview E2E batch command:

```bash
cd apps/miroflow-agent
timeout 300s env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python - <<'PY'
from dataclasses import asdict
from src.data_agents.professor.seed_runner import run_single_seed

seed_ids = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 24]
print([asdict(run_single_seed(seed_id, trigger_mode="preview", limit=3, timeout=15.0)) for seed_id in seed_ids])
PY
```

Result:

- Exit code: 0.
- Seeds 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, and 24 all returned
  `status=success`, `failure_class=success`, pipeline run `succeeded`,
  `diagnostic_profile_count=3`, `items_processed=0`, `items_failed=0`.
- Run ids:
  - 6: `42dc9f0e-2f93-4b44-b1b6-c7aa01f987b5`
  - 7: `1e1de657-be7f-4066-9dc9-66231175bd56`
  - 8: `e3958265-c176-4330-8014-f8a28618b1ae`
  - 9: `41084ece-4359-4b95-b2b8-3b8f1a288257`
  - 10: `7ef1b094-a166-49f6-ad2c-2087a64383c8`
  - 11: `2a1f7eb7-63b8-4c9e-a772-bd7595a8c411`
  - 12: `0a5104a9-b9eb-4f56-bdf9-ce2f0d646396`
  - 13: `8d3d0662-d8c2-4f94-82d8-1e994375d40b`
  - 14: `4f07dd9c-a506-4f6d-bf5a-6993a710afed`
  - 15: `fd18d72b-673b-46b9-848e-e6a5a6746811`
  - 18: `6e5ceee9-bad0-4da7-8b3c-f309081180b7`
  - 24: `d428dfb1-3ed7-4bc1-a72c-79e621176725`

Final coverage guard command:

```bash
cd apps/miroflow-agent
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run --no-sync python scripts/audit_professor_seed_adapter_coverage.py
```

Final coverage guard result:

- Exit code: 0.
- Rows: 20.
- Missing rows: 0.
- Resolver-covered rows: seeds 5-15, 18-21, and 24.
- Approved-blocked rows: seeds 25-28.

Final E2E matrix:

| seed_id | resolver_result | trigger_mode | run_id | terminal_status | items processed/failed | pipeline_run_status | issue outcome |
|---:|---|---|---|---|---:|---|---|
| 5 | `szu-teacher-family` | `preview` | `8e9eb13b-f3b7-49c6-b0fd-213227a93268` | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663` |
| 6 | `cuhk_teacher_search` | `preview` | `42dc9f0e-2f93-4b44-b1b6-c7aa01f987b5` | `success` | 0 / 0 | `succeeded` | none |
| 7 | `cuhk_teacher_search` | `preview` | `1e1de657-be7f-4066-9dc9-66231175bd56` | `success` | 0 / 0 | `succeeded` | none |
| 8 | `sigs_teacher_api` | `preview` | `e3958265-c176-4330-8014-f8a28618b1ae` | `success` | 0 / 0 | `succeeded` | none |
| 9 | `sustech-roster` | `preview` | `41084ece-4359-4b95-b2b8-3b8f1a288257` | `success` | 0 / 0 | `succeeded` | none |
| 10 | `szu-teacher-family` | `preview` | `7ef1b094-a166-49f6-ad2c-2087a64383c8` | `success` | 0 / 0 | `succeeded` | none |
| 11 | `szu-teacher-family` | `preview` | `2a1f7eb7-63b8-4c9e-a772-bd7595a8c411` | `success` | 0 / 0 | `succeeded` | none |
| 12 | `szu-teacher-family` | `preview` | `0a5104a9-b9eb-4f56-bdf9-ce2f0d646396` | `success` | 0 / 0 | `succeeded` | none |
| 13 | `szu-teacher-family` | `preview` | `8d3d0662-d8c2-4f94-82d8-1e994375d40b` | `success` | 0 / 0 | `succeeded` | none |
| 14 | `szu-teacher-family` | `preview` | `4f07dd9c-a506-4f6d-bf5a-6993a710afed` | `success` | 0 / 0 | `succeeded` | none |
| 15 | `szu-teacher-family` | `preview` | `fd18d72b-673b-46b9-848e-e6a5a6746811` | `success` | 0 / 0 | `succeeded` | none |
| 18 | `szu-teacher-family` | `preview` | `6e5ceee9-bad0-4da7-8b3c-f309081180b7` | `success` | 0 / 0 | `succeeded` | none |
| 19 | `hitsz-college-teacher-family` | `preview` | `1e8464b4-4a4b-4de4-ac69-3dc11f84e7e5` | `success` | 0 / 0 | `succeeded` | none |
| 20 | `hitsz-college-teacher-family` | `preview` | `b39c0453-2821-4ce7-ae18-662d82fb36a4` | `success` | 0 / 0 | `succeeded` | none |
| 21 | `szu-teacher-family` | `preview` | `dd1574da-5f06-45fc-acac-d3387b95fc36` | `success` | 0 / 0 | `succeeded` | none |
| 24 | `suit-sziit-teacher-family` | `preview` | `d428dfb1-3ed7-4bc1-a72c-79e621176725` | `success` | 0 / 0 | `succeeded` | none |
| 25 | none | `preview` | `b08b96ac-c4fa-4a40-8dc0-32bc3b7b3bca` | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `878d0341-1de6-4b0a-aa68-3a90e032022e` |
| 26 | none | `preview` | `d675f799-fd17-4c77-b926-04430682125c` | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `588f35d0-2756-471a-a414-c1462b5e96a1` |
| 27 | none | `preview` | `d66ed224-5901-4137-9435-15d1cb6e6250` | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `399136c7-4a77-4b53-9896-a7b9351be8db` |
| 28 | none | `preview` | `08065132-d1d9-436a-981f-7b158f3b205f` | `failure` / `fetch_blocked` | 0 / 1 | `failed` | `9efd935b-4ed7-4cbe-a720-70471dd2ac2b` |

## 2026-05-24 Final Verification

Commands:

```bash
openspec validate prof-seed-adapter-coverage --strict
```

Result: exit code 0, `Change 'prof-seed-adapter-coverage' is valid`.

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/scripts/test_audit_professor_seed_adapter_coverage.py \
  tests/data_agents/professor/test_adapter_resolution.py \
  tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_uses_suit_sziit_adapter_for_teacher_list \
  tests/data_agents/professor/test_roster_validation.py::test_extract_roster_entries_supports_hitsz_college_faculty_links \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_treats_tokenized_empty_200_as_anti_scraping \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_ignores_blocked_cached_html \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_ignores_reader_error_cached_html \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_reader_does_not_return_reader_error_cache \
  tests/data_agents/professor/test_roster_validation.py::test_fetch_html_with_fallback_skips_empty_browser_dom_after_blocked_direct -q
```

Result: exit code 0, `11 passed in 9.52s`.

```bash
cd apps/miroflow-agent
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test \
  uv run --no-sync pytest --no-cov \
  tests/postgres/test_run_single_seed.py::test_sias_tokenized_202_page_builds_fetch_blocked_evidence \
  tests/postgres/test_run_single_seed.py::test_run_single_seed_persists_fetch_blocked_for_uestc_sias_challenge \
  tests/postgres/test_run_single_seed.py::test_sias_fetch_blocked_issue_is_persisted_per_seed \
  tests/postgres/test_run_single_seed.py::test_run_single_seed_deduplicates_repeated_open_adapter_missing_issue -q
```

Result: exit code 0, `4 passed in 0.69s`.

Note: the same seed-runner command without `--no-cov` had already completed all
four tests, but pytest-cov raised a coverage SQLite internal error
(`no such table: file`) while concurrent pytest commands were also running. That
exit code 3 run is rejected as clean verification evidence.

```bash
cd apps/admin-console
DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test \
  uv run --no-sync pytest tests/test_seeds_api.py -q
```

Result: exit code 0, `27 passed, 6 warnings in 5.69s`.

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check \
  scripts/audit_professor_seed_adapter_coverage.py \
  src/data_agents/professor/discovery.py \
  src/data_agents/professor/roster.py \
  src/data_agents/professor/seed_runner.py \
  tests/scripts/test_audit_professor_seed_adapter_coverage.py \
  tests/data_agents/professor/test_adapter_resolution.py \
  tests/data_agents/professor/test_roster_validation.py \
  tests/postgres/test_run_single_seed.py
```

Result: exit code 0, `All checks passed!`.
