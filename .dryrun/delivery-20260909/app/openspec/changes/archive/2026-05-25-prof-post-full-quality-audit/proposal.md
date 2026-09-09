## Why

P7 completed controlled full recollection for 19 Professor seeds, which wrote
canonical Professor data at real scale. P8 is needed before publish/index work
so the project can audit the post-full dataset for quality, traceability,
duplicate risk, open issues, and blocked-source carryover.

## What Changes

- Add a P8 post-full Professor quality audit stage.
- Provide a deterministic audit report over the real Postgres dataset after P7
  full runs.
- Validate the P7 run matrix against canonical Professor rows and
  `pipeline_run` traceability.
- Report quality-status distribution, official-source coverage, source-page
  linkage, duplicate identity risk, open pipeline issues, and blocked seed 5
  carryover.
- Track known profile-field contamination defects found during spot checks,
  including the CUHK(SZ) SDS BRESAR, Miha page where the title field must be
  repaired and regression-tested before P8 can hand off to publish/index work.
- Require P8 E2E evidence before later publish/index/RAG refresh stages.
- Keep P8 read-only by default; quality re-evaluation writes require explicit
  task evidence and must be separated from the read-only audit.

## Capabilities

### New Capabilities
- `professor-post-full-quality-audit`: Defines the P8 post-full audit contract,
  report fields, E2E evidence requirements, and P9 handoff rules.

### Modified Capabilities
- `professor-seed-controlled-full-recollection`: Extends the P7 handoff with
  the P8 requirement that all full-success rows must be audited before publish
  or index refresh.

## Impact

- Affected runtime/scripts:
  - a new or existing audit script under `apps/miroflow-agent/scripts/`
  - `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`
  - `apps/miroflow-agent/scripts/run_professor_quality_re_eval.py`
- Affected tests:
  - `apps/miroflow-agent/tests/scripts/`
  - `apps/miroflow-agent/tests/data_agents/professor/`
- Affected OpenSpec/run evidence:
  - `openspec/changes/prof-post-full-quality-audit/tasks.md`
  - `openspec/changes/prof-post-full-quality-audit/acceptance.md`
  - `.agents/runs/prof-post-full-quality-audit/verification.md`
- P8 does not introduce schema migrations, public API changes, publish refresh,
  RAG index refresh, cleanup, or data deletion.
