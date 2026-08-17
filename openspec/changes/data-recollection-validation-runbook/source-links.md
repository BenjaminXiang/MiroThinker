# Source Links: data-recollection-validation-runbook

## Archived prerequisite specs

- `openspec/specs/professor-seed-management/spec.md`
- `openspec/specs/professor-quality-status/spec.md`
- `openspec/specs/professor-fact-extraction/spec.md`
- `openspec/specs/professor-admin-workbench/spec.md`
- `openspec/specs/professor-admin-workbench-ui/spec.md`
- `openspec/specs/paper-pipeline-cleanup/spec.md`
- `openspec/specs/paper-homepage-enrichment-completion/spec.md`
- `openspec/specs/paper-patent-from-prof-page/spec.md`

## Expected implementation touchpoints

- `apps/miroflow-agent/scripts/`
- `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`
- `apps/miroflow-agent/src/data_agents/paper/homepage_ingest.py`
- `apps/miroflow-agent/src/data_agents/patent/homepage_ingest.py`
- `apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py`
- `apps/miroflow-agent/scripts/run_milvus_backfill.py`
- `.agents/runs/data-recollection-validation-runbook/`

## Safety constraints

- Do not mutate source backfills or archived OpenSpec evidence.
- Do not run destructive cleanup without a dry-run preview and explicit
  target confirmation.
- Treat current legacy verification rows as disposable data, not as
  authoritative readiness evidence.
