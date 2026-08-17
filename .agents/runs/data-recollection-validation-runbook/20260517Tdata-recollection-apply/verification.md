# Verification

Change: `data-recollection-validation-runbook`
Run workspace:
`.agents/runs/data-recollection-validation-runbook/20260517Tdata-recollection-apply/`

## Commands

```bash
cd apps/miroflow-agent
uv run pytest tests/scripts/test_run_data_recollection_validation.py
```

Result: failed as expected in RED phase because
`scripts/run_data_recollection_validation.py` did not exist.

```bash
cd apps/miroflow-agent
uv run pytest tests/scripts/test_run_data_recollection_validation.py -n0
```

Result: passed, 11 tests.

```bash
cd apps/miroflow-agent
uv run pytest tests/scripts/test_run_data_recollection_validation.py::test_validation_report_contains_required_sections_and_incomplete_verdict -n0
```

Result: failed after the report test was tightened to require
`admin_actions` / `manual_override_checks`; then passed after report
rendering and snapshot collection were expanded.

```bash
cd apps/miroflow-agent
uv run pytest tests/scripts/test_run_data_recollection_validation.py::test_cli_plan_batch_writes_json -n0
```

Result: failed after the batch-plan test was tightened to require the
patent homepage ingest command; then passed after the plan output was
expanded.

```bash
cd apps/miroflow-agent
uv run pytest tests/scripts/test_run_data_recollection_validation.py::test_default_validation_snapshot_has_milvus_and_retrieval_skip_fields -n0
```

Result: failed while the default snapshot lacked Milvus target/chunk
fields and retrieval skipped-check fields; then passed after those
defaults were added.

```bash
cd apps/miroflow-agent
uv run pytest tests/scripts/test_run_data_recollection_validation.py::test_destructive_cleanup_uses_fk_safe_delete_order -n0
```

Result: failed while the default cleanup order deleted
`pipeline_issue` after professor/link tables; then passed after
`pipeline_issue` was moved to the front of the cleanup scope.

```bash
cd apps/miroflow-agent
uv run ruff check scripts/run_data_recollection_validation.py tests/scripts/test_run_data_recollection_validation.py
```

Result: passed.

```bash
cd apps/miroflow-agent
uv run ruff format --check scripts/run_data_recollection_validation.py tests/scripts/test_run_data_recollection_validation.py
```

Result: initially required formatting for
`scripts/run_data_recollection_validation.py`; after `uv run ruff
format ...`, the check passed.

```bash
cd apps/miroflow-agent
uv run python scripts/run_data_recollection_validation.py init-workspace --run-id 20260517Tdata-recollection-apply
```

Result: created the run workspace.

```bash
cd apps/miroflow-agent
uv run python scripts/run_data_recollection_validation.py plan-batch \
  --workspace /home/longxiang/MiroThinker/.worktrees/paper-pipeline-cleanup/.agents/runs/data-recollection-validation-runbook/20260517Tdata-recollection-apply \
  --seed-id 1 --seed-id 2 --seed-id 3 --sample-limit 3
```

Result: wrote `batch-plan.json` with explicit seed ids and sample limit.
This is only a plan; it did not trigger collection.

```bash
cd apps/miroflow-agent
uv run python scripts/run_data_recollection_validation.py generate-report \
  --workspace /home/longxiang/MiroThinker/.worktrees/paper-pipeline-cleanup/.agents/runs/data-recollection-validation-runbook/20260517Tdata-recollection-apply
```

Result: wrote `validation-report.md` with code-path pass and
data-readiness incomplete evidence. No data collection or Milvus refresh
was executed.

```bash
cd apps/miroflow-agent
uv run python scripts/run_data_recollection_validation.py cleanup-preview \
  --workspace /home/longxiang/MiroThinker/.worktrees/paper-pipeline-cleanup/.agents/runs/data-recollection-validation-runbook/20260517Tdata-recollection-apply
```

Result: blocked because neither `DATABASE_URL` nor `DATABASE_URL_TEST`
was set in this shell. No cleanup ran.

```bash
openspec validate data-recollection-validation-runbook --strict --no-interactive
```

Result: passed.

```bash
git diff --check
```

Result: passed.

## Evidence Files

- `batch-plan.json` records the bounded sample plan.
- `validation-report.md` records report structure and the current
  incomplete-evidence verdict.
- `cleanup-preview.json` remains the placeholder because the DB dry-run
  could not run without an explicit local verification DSN.

## Runtime Steps Not Executed

- No destructive cleanup was run.
- No seed trigger or recollection batch was run.
- No Milvus refresh was run.
- No RAG sanity query was run.
