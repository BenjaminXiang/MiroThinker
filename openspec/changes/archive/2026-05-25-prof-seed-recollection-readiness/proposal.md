## Why

P5 removed the largest known blocked-seed ambiguity, but the project still
does not have a release gate that says the current 20 Professor seeds are safe
to use for recollection. P6 is needed before any broad recollection or publish
run so operators can distinguish runnable seeds, intentionally blocked seeds,
bounded sample candidates, and full-run candidates with row-level evidence.

## What Changes

- Add a P6 recollection-readiness gate for the current Professor seed inventory.
- Require a deterministic readiness matrix for every current
  `miroflow_real.professor_seed` row, including resolver result, latest
  terminal status, blocked classification, recommended next trigger mode, and
  whether the seed is allowed to proceed to full recollection.
- Require bounded E2E verification before any seed is recommended for full
  recollection.
- Preserve P4/P5 safety semantics: approved blocked seeds remain visible debt,
  and a blocked seed cannot be counted as successful recollection coverage.
- Keep destructive cleanup, data deletion, and unbounded bulk recollection out
  of scope for P6 unless a later explicit OpenSpec change and operator approval
  authorize them.

## Capabilities

### New Capabilities
- `professor-seed-recollection-readiness`: Defines the P6 readiness gate,
  row-level recollection decision matrix, bounded E2E evidence, and operator
  handoff requirements for the current Professor seed inventory.

### Modified Capabilities
- `professor-seed-adapter-coverage`: Extends the existing P4/P5 evidence
  contract so post-P5 recollection readiness cannot be marked complete without
  a row-level P6 matrix and bounded E2E evidence for every current seed.
- `professor-seed-ops-hardening`: Extends safe trigger-mode requirements with
  P6-specific rules for recommending `preview`, `sample`, or `full` execution.

## Impact

- Affected runtime and scripts:
  - `apps/miroflow-agent/scripts/audit_professor_seed_adapter_coverage.py`
  - `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`
  - any new P6 readiness script or report generator added under
    `apps/miroflow-agent/scripts/`
- Affected tests:
  - `apps/miroflow-agent/tests/scripts/`
  - `apps/miroflow-agent/tests/postgres/test_run_single_seed.py`
- Affected OpenSpec/run evidence:
  - `openspec/changes/prof-seed-recollection-readiness/tasks.md`
  - `openspec/changes/prof-seed-recollection-readiness/acceptance.md`
  - `.agents/runs/prof-seed-recollection-readiness/verification.md`
- No public API, schema, dependency, or destructive data-operation change is
  introduced by this proposal.
