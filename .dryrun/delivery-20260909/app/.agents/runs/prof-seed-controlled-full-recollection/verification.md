# Verification: prof-seed-controlled-full-recollection

## 2026-05-25 Change Creation

Scope:
- Create the P7 OpenSpec change for controlled Professor seed full
  recollection.
- No full recollection, cleanup, deletion, schema change, or publish refresh has
  been executed in this section.

Commands:

```bash
openspec new change prof-seed-controlled-full-recollection
openspec status --change prof-seed-controlled-full-recollection --json
openspec instructions proposal --change prof-seed-controlled-full-recollection --json
openspec instructions design --change prof-seed-controlled-full-recollection --json
openspec instructions specs --change prof-seed-controlled-full-recollection --json
openspec instructions tasks --change prof-seed-controlled-full-recollection --json
```

Result:
- Active change scaffold created at
  `openspec/changes/prof-seed-controlled-full-recollection/`.
- Proposal, design, specs, tasks, and acceptance skeleton were created.

Pending verification:
- OpenSpec strict validation.
- Candidate baseline from the latest readiness planner.
- P7 controlled full-run helper tests.
- Real controlled full-run E2E matrix.

## 2026-05-25 OpenSpec Initial Validation

Commands:

```bash
openspec validate prof-seed-controlled-full-recollection --strict
openspec instructions apply --change prof-seed-controlled-full-recollection --json
```

Result:
- `openspec validate` returned `Change 'prof-seed-controlled-full-recollection'
  is valid`.
- `openspec instructions apply` reported 20 total tasks, 0 complete, state
  `ready`.

## 2026-05-25 Baseline Tasks 1.1-1.4

Commands:

```bash
openspec list --json
```

Result:
- One active change: `prof-seed-controlled-full-recollection`.
- No other active change blocks P7.

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/plan_professor_seed_recollection.py
```

Result:
- Full-ready seed ids: 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 18, 19,
  20, 21, 24, 25, 26, 27, 28.
- Excluded seed id 5: `blocked`, `full_recollection_allowed=False`,
  `reason=latest_run_fetch_blocked`,
  `evidence=issue:3a2f2a33-7ab9-4f1f-bed7-977cbbd23663`.

Task updates:
- Marked tasks 1.1, 1.2, 1.3, and 1.4 complete.

## 2026-05-25 Runner TDD And Implementation

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

Implementation files:
- `src/data_agents/professor/controlled_full_recollection.py`
- `scripts/run_professor_seed_full_recollection.py`
- `tests/data_agents/professor/test_controlled_full_recollection.py`

GREEN command:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_controlled_full_recollection.py -q
```

GREEN result:
- Exit code 0.
- 4 passed.

## 2026-05-25 Real Full E2E

Initial full-run command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/run_professor_seed_full_recollection.py
```

Operational note:
- The initial helper printed only at process end. It was terminated after a long
  window to prevent the session from being indefinitely blocked.
- Database evidence showed seeds 6-24 had committed full success before
  termination.
- A stale seed 25 full run
  `af0a58a2-92e1-45fe-9881-f5d1e82b4bec` was left `running`; it was marked
  failed with `failure_class='pipeline_exception'` and
  `p7_terminal_note='stale_running_run_after_terminated_runner'`.

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
- Seed 25 was excluded because the stale failed run became latest readiness
  evidence.

Recovery command:

```bash
cd apps/miroflow-agent
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline run_single_seed(25, trigger_mode='full')>
```

Recovery result:
- Seed 25 succeeded:
  `run_id=2fb1bfa9-7b98-4478-8d34-b98db6fc0e56`,
  `items_processed=156`, `items_failed=0`,
  `adapter_name=uestc-yjsjy-mentor-roster`.

Final P7 matrix query:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python <inline latest full-run matrix query>
```

Final P7 matrix:

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

Post-run commands:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/plan_professor_seed_recollection.py
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run --no-sync python scripts/audit_professor_seed_adapter_coverage.py
```

Post-run results:
- Readiness planner observed latest full success for the 19 P7 rows and seed 5
  still blocked.
- Coverage guard exited 0 with 20/20 resolver-covered rows.

Skipped operations:
- Cleanup and deletion.
- Publish refresh.
- RAG index refresh.
- Full execution for seed 5.

## 2026-05-25 Targeted Verification

Commands:

```bash
cd apps/miroflow-agent
uv run --no-sync pytest tests/data_agents/professor/test_controlled_full_recollection.py tests/data_agents/professor/test_recollection_readiness.py tests/scripts/test_audit_professor_seed_adapter_coverage.py -q
DATABASE_URL_TEST='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
  uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0
DATABASE_URL_TEST='postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock' \
  uv run --no-sync pytest tests/postgres/test_run_single_seed.py -q -n0 --no-cov
uv run --no-sync ruff check src/data_agents/professor/controlled_full_recollection.py scripts/run_professor_seed_full_recollection.py tests/data_agents/professor/test_controlled_full_recollection.py
```

Results:
- P7/P6 planner and coverage tests: 12 passed.
- Seed runner contract first run: 16 passed, but pytest-cov raised
  `coverage.exceptions.DataError` and exited 3.
- Seed runner contract rerun with `--no-cov`: 16 passed, exit 0.
- Ruff: `All checks passed!`.

Task updates:
- Marked tasks 2.1-2.4, 3.1-3.4, 4.1-4.5, 5.1, and 5.2 complete.
- Left task 4.6 pending until final OpenSpec validation after these artifact
  updates.

## 2026-05-25 OpenSpec Final Validation

Commands:

```bash
openspec validate prof-seed-controlled-full-recollection --strict
openspec instructions apply --change prof-seed-controlled-full-recollection --json
```

Result:
- `openspec validate` returned `Change 'prof-seed-controlled-full-recollection'
  is valid`.
- `openspec instructions apply` reported 19/20 complete before marking task
  4.6, with only the final validation task pending.

Task updates:
- Marked task 4.6 complete after recording the validation result.

Post-update validation:

```bash
openspec instructions apply --change prof-seed-controlled-full-recollection --json
openspec validate prof-seed-controlled-full-recollection --strict
```

Result:
- `openspec instructions apply` reported 20/20 complete, 0 remaining, state
  `all_done`.
- `openspec validate` returned `Change 'prof-seed-controlled-full-recollection'
  is valid`.
