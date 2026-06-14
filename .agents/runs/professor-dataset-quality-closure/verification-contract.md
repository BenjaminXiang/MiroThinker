# Verification Contract: professor-dataset-quality-closure

## Scope

This run implements the OpenSpec change
`professor-dataset-quality-closure`. Current implemented slices cover the
read-only bucketed audit, dry-run evidence gates, write-mode batch
orchestration, default evidence-driven writers, post-write verification
callbacks, and Professor-domain boundary regression coverage.

This run must not claim final dataset closure until the real `miroflow_real`
blockers are cleared by verified writes or converted into durable residual-risk
records. This run did not execute write-mode remediation against
`miroflow_real`, refresh indexes, or change runtime multi-source recall
behavior. It may file `pipeline_issue` residual-risk rows because those are the
durable unresolved records required by the final closure requirement.

## RED Evidence

- Unit tests fail until the audit model can represent bucket rows with stable
  identifiers, blocker type, remediation lane, automatic eligibility, skip
  reason, and source evidence fields.
- CLI tests fail until
  `run_professor_core_profile_paper_quality_audit.py --include-buckets`
  returns bucketed audit data while preserving the legacy report by default.
- Real database baseline remains blocked until the four dataset blocker classes
  are cleared or classified:
  - `ready_summary_lt_200`
  - `missing_research_overview_zh`
  - `missing_professor_paper_summary`
  - `duplicate_verified_paper_title_year_groups`

## GREEN Evidence For This Run

- The CLI emits a read-only bucketed JSON report with:
  - aggregate baseline metrics;
  - `closure_buckets.summary` counts for each blocker class;
  - row-level or group-level bucket samples for each blocker class;
  - stable ids and remediation lane fields;
  - truncation metadata when sample output is bounded.
- The default CLI output remains backward compatible when
  `--include-buckets` is not supplied.
- Dry-run lane reports include input, eligible, proposed write, skipped,
  validation/provider failure, affected-id, and selection-hash evidence.
- Write mode refuses without matching dry-run evidence and a real run id.
- Write-mode batch orchestration records changed ids, lane counts, row-level
  issues, and rollback evidence.
- Post-write verification callbacks re-evaluate changed Professors, audit
  affected ids, sample Professor/Paper detail shapes, and select refresh ids.
- Domain-boundary tests prove hidden company roles and provider-only
  author-name paper discovery are outside Professor core closure.
- Residual-risk filing persists open `pipeline_issue` rows with blocker type,
  reason, confidence impact, and next action, and coverage verification proves
  no targeted bucket row remains unclassified.
- Targeted unit/script tests pass.
- The real `miroflow_real` baseline and final bucket commands run and their
  blocked outputs are recorded in
  `.agents/runs/professor-dataset-quality-closure/verification.md`.
- `openspec validate "professor-dataset-quality-closure" --strict` passes.

## Required Commands

```bash
uv run pytest \
  apps/miroflow-agent/tests/data_agents/professor/test_core_profile_paper_quality_audit.py \
  apps/miroflow-agent/tests/scripts/test_run_professor_core_profile_paper_quality_audit.py \
  -q -n0 --no-cov

DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python apps/miroflow-agent/scripts/run_professor_core_profile_paper_quality_audit.py \
  --include-buckets --bucket-limit 5

openspec validate "professor-dataset-quality-closure" --strict
```

For the write-mode orchestration and post-write callback slices, also run:

```bash
uv run pytest \
  apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py \
  apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py \
  -q -n0 --no-cov

uv run ruff check \
  apps/miroflow-agent/src/data_agents/professor/dataset_quality_closure.py \
  apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py \
  apps/miroflow-agent/tests/data_agents/professor/test_dataset_quality_closure.py \
  apps/miroflow-agent/tests/scripts/test_run_professor_dataset_quality_closure.py
```

For the final evidence pass, also run:

```bash
uv run pytest \
  apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_returns_seven_sections \
  apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_prefers_persisted_chinese_research_overview \
  apps/admin-console/tests/test_admin_professor_api.py::test_admin_professor_detail_returns_canonical_paper_link_fields \
  apps/admin-console/tests/test_data_api_paper_v011.py::test_paper_detail_includes_full_text_metadata \
  apps/admin-console/tests/test_data_api_paper_v011.py::test_domains_paper_detail_returns_summary_zh_column_value \
  -q -n0 --no-cov

cd apps/admin-console/frontend
npm run test -- RecordDetail.test.tsx ProfessorWorkbench.test.tsx

DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python apps/miroflow-agent/scripts/run_professor_dataset_quality_closure.py \
  --mode residual-risk-coverage --bucket-limit 6000
```

## Write Restrictions

- No write-mode remediation command may be executed against `miroflow_real` in
  this implementation slice.
- Unit tests may use fake connections and injected writers to verify write
  orchestration behavior.
- Real writer code must require a non-sentinel run id and matching dry-run
  evidence before it can call `UPDATE`, `INSERT`, merge alias writes, or profile
  section writes.
- Any command requiring real database access in this slice must be read-only or
  explicitly documented as skipped.

## Skipped Work In This Run

- Real write-mode profile-summary, research-overview, Professor paper-summary,
  and duplicate-merge batches against `miroflow_real`.
- Full blocker clearance for the remaining dataset population.
- Real post-write quality re-evaluation/API sampling against changed
  `miroflow_real` rows, because no real rows changed in this run.
- Index/vector refresh, because no real rows changed in this run.
