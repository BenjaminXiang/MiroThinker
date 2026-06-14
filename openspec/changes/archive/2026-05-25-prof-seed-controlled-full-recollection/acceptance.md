# Acceptance: prof-seed-controlled-full-recollection

## Status

| Requirement | Status | Evidence |
|---|---|---|
| P7 candidate selection uses the latest readiness matrix | Verified | Baseline planner selected 19 full-ready rows and excluded seed 5. |
| P7 full execution records row-level E2E evidence | Verified | Final P7 full matrix below records all 19 selected rows with latest full success and item counts. |
| P7 completion updates required artifacts | Verified | `tasks.md`, this `acceptance.md`, and `.agents/runs/prof-seed-controlled-full-recollection/verification.md` were updated with commands and outcomes. |
| P7 does not perform cleanup or publish refresh | Verified | P7 skipped cleanup, deletion, publish refresh, RAG index refresh, and seed 5 full execution. |
| P7 full execution consumes full-ready P6 rows only | Verified | Initial execution selected full-ready rows only; seed 5 remained excluded. |
| P7 full mode remains controlled and auditable | Verified | Each final full row has a `pipeline_run.run_scope` with `trigger_mode='full'`, `failure_class='success'`, and write counts. |

## Scope Boundary

P7 is authorized to run controlled `full` mode only for seeds currently marked
`full_recollection_allowed=true` by the readiness planner. P7 is not authorized
to run seed 5 while it remains blocked, truncate tables, delete canonical rows,
hard-delete seeds, refresh online RAG indexes, or publish downstream search
collections.

## Pending Evidence

- Latest candidate set from `scripts/plan_professor_seed_recollection.py`.
- P7 full-run helper tests.
- Real full-run E2E matrix.
- Post-run readiness planner and coverage guard.
- P8 quality-validation handoff.

## 2026-05-25 Baseline Candidate Evidence

### Active Change State

`openspec list --json` returned one active change:
`prof-seed-controlled-full-recollection`, with 0/20 tasks complete before the
baseline task updates. No other active change blocks P7.

### Latest Readiness Matrix

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/plan_professor_seed_recollection.py
```

Result:
- Full-ready seed ids: 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19,
  20, 21, 24, 25, 26, 27, 28.
- Blocked exclusion: seed 5, `reason=latest_run_fetch_blocked`,
  `evidence=issue:3a2f2a33-7ab9-4f1f-bed7-977cbbd23663`.
- P7 candidate count: 19.

Baseline conclusion:
- P7 may run controlled `full` mode for the 19 full-ready rows only.
- P7 must not run seed 5 in `full` mode.

## 2026-05-25 Controlled Full Runner Evidence

### Runner Implementation

Files:
- `apps/miroflow-agent/src/data_agents/professor/controlled_full_recollection.py`
- `apps/miroflow-agent/scripts/run_professor_seed_full_recollection.py`
- `apps/miroflow-agent/tests/data_agents/professor/test_controlled_full_recollection.py`

RED commands:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_controlled_full_recollection.py -q
uv run --no-sync pytest tests/data_agents/professor/test_controlled_full_recollection.py::test_full_run_plan_can_filter_selected_seed_ids_without_selecting_blocked_rows -q
```

RED results:
- Initial RED failed during collection with
  `ModuleNotFoundError: No module named 'src.data_agents.professor.controlled_full_recollection'`.
- Resume-filter RED failed with
  `TypeError: build_full_run_plan() got an unexpected keyword argument 'selected_seed_ids'`.

GREEN result:
- `uv run --no-sync pytest tests/data_agents/professor/test_controlled_full_recollection.py -q`
  passed with 4 tests.

### Full Execution

Initial full-run command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/run_professor_seed_full_recollection.py
```

Operational note:
- The initial runner printed only at process end. It was terminated after a long
  run window to avoid leaving the session indefinitely blocked.
- Before termination, seeds 6 through 24 had already committed successful full
  runs, and seed 25 had an opened stale `running` full run.
- The stale seed 25 run
  `af0a58a2-92e1-45fe-9881-f5d1e82b4bec` was marked failed with
  `failure_class='pipeline_exception'` and a P7 terminal note.
- Seed 25 was then recovered by an explicit full rerun and succeeded.

Resume command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/run_professor_seed_full_recollection.py \
    --seed-id 25 --seed-id 26 --seed-id 27 --seed-id 28
```

Resume result:
- Seeds 26, 27, and 28 succeeded.
- Seed 25 was excluded by latest readiness after the stale failure, then was
  recovered by direct full rerun:
  `run_single_seed(25, trigger_mode='full', timeout=45.0)`.
- Seed 25 recovery result:
  `run_id=2fb1bfa9-7b98-4478-8d34-b98db6fc0e56`,
  `status=success`, `items_processed=156`, `items_failed=0`.

### Final P7 Full Matrix

| seed_id | status | failure_class | items processed/failed | written | diagnostic | p8_ready | run_id |
|---:|---|---|---:|---:|---:|---|---|
| 6 | succeeded | success | 37/0 | 37 | 37 | true | `b56b5070-a672-4470-9954-ecded72b9ebd` |
| 7 | succeeded | success | 98/0 | 98 | 98 | true | `2b8861c3-fdb8-4091-8532-c32dd848c8be` |
| 8 | succeeded | success | 250/0 | 250 | 250 | true | `76c78def-a6f2-4207-b5ff-a292d6298cbf` |
| 9 | succeeded | success | 988/0 | 988 | 988 | true | `8d864004-bb73-4030-ae03-461eec125c5c` |
| 10 | succeeded | success | 101/0 | 101 | 101 | true | `15abe6c2-4cef-4fe3-a931-1963ffdbcf18` |
| 11 | succeeded | success | 36/0 | 36 | 36 | true | `81f7606d-e8a6-4823-a2fb-bb5af192b6bb` |
| 12 | succeeded | success | 57/0 | 57 | 57 | true | `e3f50408-32a0-429c-a9b6-ca3a032e936e` |
| 13 | succeeded | success | 15/0 | 15 | 15 | true | `11e1df05-4f4f-42e0-9313-ebb600543cde` |
| 14 | succeeded | success | 123/0 | 123 | 123 | true | `f8c1f948-c142-466e-8962-ab72d01d6b41` |
| 15 | succeeded | success | 102/0 | 102 | 102 | true | `526f1843-6eef-43a6-b5c3-7f034cb05c8b` |
| 18 | succeeded | success | 40/0 | 40 | 40 | true | `026a9c57-a529-46ff-93dc-8b2058b78a32` |
| 19 | succeeded | success | 96/0 | 96 | 96 | true | `59be1764-006c-4542-9973-073ee2db5b71` |
| 20 | succeeded | success | 30/0 | 30 | 30 | true | `a76f6d46-4a27-433d-b830-b8b3940fcd22` |
| 21 | succeeded | success | 9/0 | 9 | 9 | true | `f58776e6-8ce6-4afa-86e3-021157619dde` |
| 24 | succeeded | success | 10/0 | 10 | 10 | true | `eb08f1b4-ef43-4a00-9dbf-a9150f9067ab` |
| 25 | succeeded | success | 156/0 | 156 | 156 | true | `2fb1bfa9-7b98-4478-8d34-b98db6fc0e56` |
| 26 | succeeded | success | 44/0 | 44 | 44 | true | `8e84661f-35c1-4473-b632-b5c5c43bfd62` |
| 27 | succeeded | success | 7/0 | 7 | 7 | true | `17f3b8e8-4e60-43c4-a087-ea40b2ee6637` |
| 28 | succeeded | success | 11/0 | 11 | 11 | true | `cd689a95-43d0-48d3-bf18-17606e42dbca` |

Excluded from full execution:
- Seed 5 remained blocked with
  `evidence=issue:3a2f2a33-7ab9-4f1f-bed7-977cbbd23663`.

### Post-Run Checks

Commands:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/plan_professor_seed_recollection.py
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/audit_professor_seed_adapter_coverage.py
```

Results:
- Readiness planner observed latest full success for seeds 6-28 except seed 5,
  which remained blocked.
- Coverage guard exited 0 with 20/20 resolver-covered rows.

### Verification Commands

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_controlled_full_recollection.py tests/data_agents/professor/test_recollection_readiness.py tests/scripts/test_audit_professor_seed_adapter_coverage.py -q
DATABASE_URL_TEST='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
  uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0 --no-cov
uv run --no-sync ruff check src/data_agents/professor/controlled_full_recollection.py scripts/run_professor_seed_full_recollection.py tests/data_agents/professor/test_controlled_full_recollection.py
```

Results:
- P7/P6 planner and coverage tests: 12 passed.
- Seed runner contract tests: first run hit a pytest-cov sqlite internal error
  after reporting 16 passed; rerun with `--no-cov` exited 0 with 16 passed.
- Ruff: all checks passed.

Skipped in P7:
- Cleanup and deletion.
- Publish refresh.
- RAG index refresh.
- Full execution for seed 5.

## P8 Handoff

Rows ready for P8 post-full quality audit:
- Seed ids 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21,
  24, 25, 26, 27, 28.

Rows requiring remediation outside P8 quality audit:
- Seed 5 remains blocked on the current SZU CSSE source.

P8 should validate canonical Professor data quality after the P7 full writes:
deduplication, evidence/source traceability, quality-status distribution,
pipeline issues, and publish readiness.
