# Acceptance: prof-seed-recollection-readiness

## Status

| Requirement | Status | Evidence |
|---|---|---|
| P6 readiness matrix covers the current Professor seed inventory | Verified | Final P6 matrix below includes all 20 observed seed ids. |
| P6 recommendations use bounded safety rules | Verified | Seed 5 is `blocked`; 19 seeds moved from `sample` to `full` only after successful bounded sample runs. |
| P6 completion requires bounded E2E evidence and artifact updates | Verified | Bounded sample E2E matrix, test commands, lint, and verification updates are recorded below and in `.agents/runs/prof-seed-recollection-readiness/verification.md`. |
| P6 does not perform destructive cleanup or unbounded bulk recollection | Verified | P6 skipped cleanup, deletion, and full recollection. Only bounded `sample` runs with `limit=3` were executed for sample candidates. |
| P6 readiness evidence extends the seed coverage matrix | Verified | Coverage guard remained 20/20 resolver-covered; final P6 matrix separates coverage from full-readiness recommendation. |
| P6 trigger recommendations respect bounded modes | Verified | Initial planner recommended bounded `sample` for 19 rows and `blocked` for seed 5; final planner recommends `full` only after sample evidence and does not execute full. |

## Initial Scope Boundary

P6 is a readiness gate. It is not authorized to truncate data, delete
canonical Professor rows, hard-delete seeds, or run all eligible seeds in
unbounded `full` mode.

## Pending Evidence

- Current `miroflow_real.professor_seed` observed seed ids.
- Current coverage guard output.
- Current latest run/issue evidence per seed.
- P6 readiness planner output.
- Bounded preview/sample E2E output.
- Final row-level matrix and P7 handoff list.

## 2026-05-25 Baseline Evidence

### Active Change State

`openspec list --json` returned one active change:
`prof-seed-recollection-readiness`, with 0/20 tasks complete before the
baseline task updates. No other active OpenSpec change blocks P6 execution.

### Coverage Guard

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/audit_professor_seed_adapter_coverage.py
```

Result:
- Exit code: 0.
- Observed seed rows: 20.
- Missing coverage rows: 0.
- Coverage state: all 20 rows were `resolver_covered`.
- Seed ids observed: 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19,
  20, 21, 24, 25, 26, 27, 28.

### Latest Run And Issue Baseline

All latest recorded seed-run executions were `preview` mode. Seed 5 most
recently ended `failed` with `failure_class=fetch_blocked`. The other 19 rows
most recently ended `succeeded` with `failure_class=success`.

| seed ids | latest run outcome | latest mode | diagnostic count | written count | latest issue context |
|---|---|---|---:|---:|---|
| 5 | failed / fetch_blocked | preview | n/a | n/a | current `fetch_blocked` issue `3a2f2a33-7ab9-4f1f-bed7-977cbbd23663` |
| 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 24 | succeeded / success | preview | 3 each | 0 each | seed 8 and 24 retain historical issue references without a current failure class |
| 25, 26, 27, 28 | succeeded / success | preview | 2 each | 0 each | historical P4 `fetch_blocked` issue references retained after P5 success |

Baseline conclusion:
- P6 can start from a fully resolver-covered inventory.
- P6 cannot treat preview success as full recollection readiness.
- Seed 5 remains the only current latest-run blocked row and must remain
  in the P6 matrix as `blocked` unless a later official replacement succeeds.

## 2026-05-25 Planner And E2E Evidence

### Planner Implementation

Files:
- `apps/miroflow-agent/src/data_agents/professor/recollection_readiness.py`
- `apps/miroflow-agent/scripts/plan_professor_seed_recollection.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_recollection_readiness.py`

RED command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_recollection_readiness.py -q
```

RED result:
- Failed during collection with
  `ModuleNotFoundError: No module named 'src.data_agents.professor.recollection_readiness'`.

GREEN result:
- The same command passed after implementation: 6 passed.

### Initial P6 Matrix

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/plan_professor_seed_recollection.py
```

Initial result:
- Seed 5: `blocked`, `full_recollection_allowed=False`.
- Seed ids 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21,
  24, 25, 26, 27, 28: `sample`, `full_recollection_allowed=False`.
- No seed was recommended for `full` before bounded sample evidence.

### Bounded Sample E2E

Command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline run_single_seed sample limit=3 script>
```

Result:

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

No row was recommended as `preview`, so no preview E2E command was required in
P6 after the initial planner run.

### Final P6 Matrix

| seed_id | resolver | latest mode | latest status | recommendation | full allowed | evidence |
|---:|---|---|---|---|---|---|
| 5 | `szu-teacher-family` | preview | failed / fetch_blocked | blocked | false | `issue:3a2f2a33-7ab9-4f1f-bed7-977cbbd23663` |
| 6 | `cuhk_teacher_search` | sample | succeeded / success | full | true | `run:934545c4-2c2c-46e3-bddf-5ca093c80141` |
| 7 | `cuhk_teacher_search` | sample | succeeded / success | full | true | `run:30e6a506-a6e3-4291-84cf-02ad551aded3` |
| 8 | `sigs_teacher_api` | sample | succeeded / success | full | true | `run:eafd3642-b75f-49df-9ac7-03cdeb6284e4` |
| 9 | `sustech-roster` | sample | succeeded / success | full | true | `run:bb100db7-02fc-46c0-aee5-8875a8105baf` |
| 10 | `szu-teacher-family` | sample | succeeded / success | full | true | `run:4974baf7-ac1f-45e1-931c-6324440ad49a` |
| 11 | `szu-teacher-family` | sample | succeeded / success | full | true | `run:de92431b-5aab-4c17-9f22-04a18230fca1` |
| 12 | `szu-teacher-family` | sample | succeeded / success | full | true | `run:6806d592-a738-4c04-bf08-4e18ae6c3bde` |
| 13 | `szu-teacher-family` | sample | succeeded / success | full | true | `run:9c993f2d-5d12-44c4-aed9-ba619a79848b` |
| 14 | `szu-teacher-family` | sample | succeeded / success | full | true | `run:7bc7a52a-4fbd-46cc-a64c-33772c78ecc7` |
| 15 | `szu-teacher-family` | sample | succeeded / success | full | true | `run:ff9844b7-ccc6-4175-bbc1-dddf63f64395` |
| 18 | `szu-teacher-family` | sample | succeeded / success | full | true | `run:8bcc113c-6e26-4981-ba6c-9fa3bf6fbd10` |
| 19 | `hitsz-college-teacher-family` | sample | succeeded / success | full | true | `run:5f6238dd-6521-40d1-b9d0-925199363771` |
| 20 | `hitsz-college-teacher-family` | sample | succeeded / success | full | true | `run:566f2094-d1b2-4a99-b289-55fc55af8b5a` |
| 21 | `szu-teacher-family` | sample | succeeded / success | full | true | `run:44d73bff-f586-4edb-aa90-1e7ceeef61a3` |
| 24 | `suit-sziit-teacher-family` | sample | succeeded / success | full | true | `run:a260e3c0-d78e-49f8-8a8d-7ff1b3e73921` |
| 25 | `uestc-yjsjy-mentor-roster` | sample | succeeded / success | full | true | `run:ebf9437f-a41f-41ab-8316-3bde1ff66b3c` |
| 26 | `uestc-yjsjy-mentor-roster` | sample | succeeded / success | full | true | `run:4eaa320d-4201-4857-9f36-9000f1662bc5` |
| 27 | `uestc-yjsjy-mentor-roster` | sample | succeeded / success | full | true | `run:ae2babf5-3a35-4374-808d-4e7424b35d82` |
| 28 | `uestc-yjsjy-mentor-roster` | sample | succeeded / success | full | true | `run:3749aed5-94cf-4eb1-8a91-cbb7c895271f` |

### Verification Commands

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
- Ruff: all checks passed.
- Coverage guard: exit code 0, 20/20 resolver-covered rows.

## P7 Handoff

P7 full-confirmation candidates:
- Seed ids 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21,
  24, 25, 26, 27, 28.

P7/P8 blocked/remediation candidate:
- Seed id 5 remains blocked on current CSSE official-source access. It should
  not be full-run until an official replacement source is accepted or the
  current official source becomes reachable.

Skipped in P6:
- Destructive cleanup.
- Data deletion.
- Unbounded full recollection.
- Bulk full execution for all eligible seeds.
