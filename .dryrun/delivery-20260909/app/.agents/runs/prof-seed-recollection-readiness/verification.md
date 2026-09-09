# Verification: prof-seed-recollection-readiness

## 2026-05-25 Change Creation

Scope:
- Create the P6 OpenSpec change for Professor seed recollection readiness.
- No runtime, crawler, database schema, cleanup, or recollection execution code
  has been changed in this section.

Commands:

```bash
openspec list --json
openspec list --specs --json
openspec new change prof-seed-recollection-readiness
openspec status --change prof-seed-recollection-readiness --json
openspec instructions proposal --change prof-seed-recollection-readiness --json
openspec instructions design --change prof-seed-recollection-readiness --json
openspec instructions specs --change prof-seed-recollection-readiness --json
openspec instructions tasks --change prof-seed-recollection-readiness --json
```

Result:
- Active change scaffold created at
  `openspec/changes/prof-seed-recollection-readiness/`.
- Proposal, design, spec deltas, tasks, and acceptance skeleton were created.
- P6 has not been implemented yet.

Skipped operations:
- Destructive cleanup: skipped because P6 is a readiness gate.
- Unbounded full recollection: skipped because P6 requires bounded evidence and
  later explicit approval before full execution.
- Real P6 E2E: pending implementation of the readiness planner and bounded
  run matrix.

Pending verification:
- `openspec validate prof-seed-recollection-readiness --strict`
- `openspec instructions apply --change prof-seed-recollection-readiness --json`
- Planner unit tests.
- Coverage guard against `miroflow_real`.
- Bounded preview/sample P6 E2E matrix.

## 2026-05-25 OpenSpec Validation

Commands:

```bash
openspec validate prof-seed-recollection-readiness --strict
openspec instructions apply --change prof-seed-recollection-readiness --json
openspec status --change prof-seed-recollection-readiness
```

Result:
- `openspec validate` returned `Change 'prof-seed-recollection-readiness' is
  valid`.
- `openspec instructions apply` reported 20 total tasks, 0 complete, 20
  remaining, state `ready`.
- `openspec status` reported all 4 artifacts complete:
  `proposal`, `design`, `specs`, and `tasks`.

Remaining:
- P6 implementation has not started.
- No P6 task checkbox has been marked complete yet because no P6 execution
  evidence has been produced.

## 2026-05-25 Baseline Tasks 1.1-1.4

Scope:
- Complete the read-only P6 baseline tasks.
- Do not run crawlers, cleanup, deletion, or unbounded full recollection.

Commands:

```bash
openspec list --json
```

Result:
- One active change: `prof-seed-recollection-readiness`.
- No other active OpenSpec changes block P6 execution.

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/audit_professor_seed_adapter_coverage.py
```

Result:
- Exit code 0.
- Observed 20 seed rows:
  5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 24, 25, 26,
  27, 28.
- All 20 rows were `resolver_covered`.
- Missing coverage rows: 0.

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline latest seed run/issue baseline query>
```

Result:

| seed ids | latest run outcome | latest mode | diagnostic count | written count | issue context |
|---|---|---|---:|---:|---|
| 5 | failed / fetch_blocked | preview | n/a | n/a | current `fetch_blocked` issue `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663` |
| 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 24 | succeeded / success | preview | 3 each | 0 each | seed 8 and 24 retain historical issue references without a current failure class |
| 25, 26, 27, 28 | succeeded / success | preview | 2 each | 0 each | historical P4 `fetch_blocked` issue references retained after P5 success |

Task updates:
- Marked tasks 1.1, 1.2, 1.3, and 1.4 complete in
  `openspec/changes/prof-seed-recollection-readiness/tasks.md`.

## 2026-05-25 Planner TDD And Implementation

RED command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_recollection_readiness.py -q
```

RED result:
- Exit code 1.
- Failure was the expected missing implementation:
  `ModuleNotFoundError: No module named 'src.data_agents.professor.recollection_readiness'`.

Implementation files:
- `src/data_agents/professor/recollection_readiness.py`
- `scripts/plan_professor_seed_recollection.py`
- `tests/data_agents/professor/test_recollection_readiness.py`

GREEN command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_recollection_readiness.py -q
```

GREEN result:
- Exit code 0.
- 6 passed.

## 2026-05-25 P6 Real Matrix And Bounded E2E

Initial planner command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/plan_professor_seed_recollection.py
```

Initial planner result:
- Seed 5: `blocked`, `full_recollection_allowed=False`.
- Seed ids 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21,
  24, 25, 26, 27, 28: `sample`, `full_recollection_allowed=False`.
- No seed was recommended for `full` before sample evidence.

Bounded sample E2E command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline run_single_seed sample limit=3 script>
```

Bounded sample E2E result:

| seed_id | adapter | status | failure_class | items processed/failed | run_id |
|---:|---|---|---|---:|---|
| 6 | `cuhk_teacher_search` | success | success | 3/0 | `934545c4-2c2c-46e3-bddf-5ca093c80141` |
| 7 | `cuhk_teacher_search` | success | success | 3/0 | `30e6a506-a6e3-4291-84cf-02ad551aded3` |
| 8 | `sigs_teacher_api` | success | success | 3/0 | `eafd3642-b75f-49df-9ac7-03cdeb6284e4` |
| 9 | `sustech-roster` | success | success | 3/0 | `bb100db7-02fc-46c0-aee5-8875a8105baf` |
| 10 | `szu-teacher-family` | success | success | 3/0 | `4974baf7-ac1f-45e1-931c-6324440ad49a` |
| 11 | `szu-teacher-family` | success | success | 3/0 | `de92431b-5aab-4c17-9f22-04a18230fca1` |
| 12 | `szu-teacher-family` | success | success | 3/0 | `6806d592-a738-4c04-bf08-4e18ae6c3bde` |
| 13 | `szu-teacher-family` | success | success | 3/0 | `9c993f2d-5d12-44c4-aed9-ba619a79848b` |
| 14 | `szu-teacher-family` | success | success | 3/0 | `7bc7a52a-4fbd-46cc-a64c-33772c78ecc7` |
| 15 | `szu-teacher-family` | success | success | 3/0 | `ff9844b7-ccc6-4175-bbc1-dddf63f64395` |
| 18 | `szu-teacher-family` | success | success | 3/0 | `8bcc113c-6e26-4981-ba6c-9fa3bf6fbd10` |
| 19 | `hitsz-college-teacher-family` | success | success | 3/0 | `5f6238dd-6521-40d1-b9d0-925199363771` |
| 20 | `hitsz-college-teacher-family` | success | success | 3/0 | `566f2094-d1b2-4a99-b289-55fc55af8b5a` |
| 21 | `szu-teacher-family` | success | success | 3/0 | `44d73bff-f586-4edb-aa90-1e7ceeef61a3` |
| 24 | `suit-sziit-teacher-family` | success | success | 3/0 | `a260e3c0-d78e-49f8-8a8d-7ff1b3e73921` |
| 25 | `uestc-yjsjy-mentor-roster` | success | success | 3/0 | `ebf9437f-a41f-41ab-8316-3bde1ff66b3c` |
| 26 | `uestc-yjsjy-mentor-roster` | success | success | 3/0 | `4eaa320d-4201-4857-9f36-9000f1662bc5` |
| 27 | `uestc-yjsjy-mentor-roster` | success | success | 3/0 | `ae2babf5-3a35-4374-808d-4e7424b35d82` |
| 28 | `uestc-yjsjy-mentor-roster` | success | success | 3/0 | `3749aed5-94cf-4eb1-8a91-cbb7c895271f` |

Final planner command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/plan_professor_seed_recollection.py
```

Final planner result:
- Seed 5 remained `blocked`, `full_recollection_allowed=False`.
- The 19 bounded-sample-success rows were recommended as `full`,
  `full_recollection_allowed=True`.
- P6 did not execute any full run.

## 2026-05-25 Targeted Verification

Commands:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_recollection_readiness.py tests/scripts/test_audit_professor_seed_adapter_coverage.py -q
DATABASE_URL_TEST='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
  uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0
uv run --no-sync ruff check src/data_agents/professor/recollection_readiness.py scripts/plan_professor_seed_recollection.py tests/data_agents/professor/test_recollection_readiness.py
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/audit_professor_seed_adapter_coverage.py
```

Results:
- Planner and coverage tests: 8 passed.
- Seed runner contract tests: 16 passed.
- Ruff: `All checks passed!`.
- Coverage guard: exit code 0, 20/20 resolver-covered rows.

Skipped operations:
- Bounded preview E2E: no final initial-planner row was recommended as
  `preview`, so no preview-only row existed to run.
- Destructive cleanup: skipped, out of P6 scope.
- Data deletion: skipped, out of P6 scope.
- Unbounded full recollection: skipped, deferred to P7/P8 approval and
  execution planning.

Task updates:
- Marked tasks 2.1-2.4, 3.1-3.4, 4.1-4.5, 5.1, and 5.2 complete.
- Left task 4.6 pending until the final OpenSpec validate/apply commands run
  after these artifact updates.

## 2026-05-25 OpenSpec Final Validation

Commands:

```bash
openspec validate prof-seed-recollection-readiness --strict
openspec instructions apply --change prof-seed-recollection-readiness --json
```

Result:
- `openspec validate` returned `Change 'prof-seed-recollection-readiness' is
  valid`.
- `openspec instructions apply` reported 19/20 complete before marking task
  4.6, with only the final validation task pending.

Task updates:
- Marked task 4.6 complete after recording the validation result.

Post-update validation:

```bash
openspec instructions apply --change prof-seed-recollection-readiness --json
openspec validate prof-seed-recollection-readiness --strict
```

Result:
- `openspec instructions apply` reported 20/20 complete, 0 remaining, state
  `all_done`.
- `openspec validate` returned `Change 'prof-seed-recollection-readiness' is
  valid`.
