# Source Links: prof-quality-status-rework

## Parent and specs

- `openspec/changes/prof-admin-workbench/` — Epic parent contract.
- `docs/Data-Agent-Shared-Spec.md §7.2` — non-ready objects need
  quality reasons persisted to `pipeline_issue`.
- `docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md` —
  quality is separate from lifecycle.

## Code to inspect before implementation

- `apps/miroflow-agent/src/data_agents/professor/quality_gate.py` —
  current transient-profile evaluator.
- `apps/miroflow-agent/src/data_agents/professor/canonical_writer.py`
  — canonical write path missing `quality_status` persistence.
- `apps/miroflow-agent/alembic/versions/V006_init_pipeline_issue.py`
  — base `pipeline_issue` stages and open-issue unique index.
- `apps/miroflow-agent/alembic/versions/V023_extend_pipeline_issue_adapter_missing.py`
  — adds `adapter_missing` stage.
- `apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py`
  — nearest existing quality tests.
- `apps/miroflow-agent/tests/professor/test_canonical_writer.py` —
  canonical writer regression surface.
