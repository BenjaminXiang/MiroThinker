## Why

P6 proved that 19 current Professor seeds have post-P5 bounded sample success
and are eligible for later full confirmation, while seed 5 remains blocked.
P7 is needed to execute the first controlled full recollection for those
eligible seeds with row-level E2E evidence and without hiding the blocked row.

## What Changes

- Add a P7 controlled full recollection stage for Professor seeds.
- Require the full-run candidate set to be derived from the latest P6 readiness
  matrix, not from a hardcoded manual list alone.
- Execute `full` mode only for seeds whose latest readiness row has
  `full_recollection_allowed=true`.
- Explicitly exclude seed 5 and any other non-ready seed from full execution.
- Record a row-level P7 E2E matrix with run id, terminal status, item counts,
  failure class, and issue outcome.
- Preserve destructive-cleanup safety: P7 does not truncate tables, delete
  canonical rows, or hard-delete seeds.

## Capabilities

### New Capabilities
- `professor-seed-controlled-full-recollection`: Defines the P7 controlled
  full-recollection execution gate, candidate selection rules, row-level E2E
  matrix, and handoff to post-run quality validation.

### Modified Capabilities
- `professor-seed-recollection-readiness`: Extends P6 readiness semantics with
  the P7 rule that only rows with `full_recollection_allowed=true` can enter
  controlled full recollection.
- `professor-seed-ops-hardening`: Extends safe trigger-mode requirements with
  P7 full-run execution evidence and explicit cleanup exclusion.

## Impact

- Affected runtime/scripts:
  - `apps/miroflow-agent/src/data_agents/professor/recollection_readiness.py`
  - a new or existing script under `apps/miroflow-agent/scripts/` for P7
    controlled full execution
  - `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`
- Affected tests:
  - `apps/miroflow-agent/tests/data_agents/professor/`
  - `apps/miroflow-agent/tests/scripts/`
  - `apps/miroflow-agent/tests/postgres/test_run_single_seed.py`
- Affected OpenSpec/run evidence:
  - `openspec/changes/prof-seed-controlled-full-recollection/tasks.md`
  - `openspec/changes/prof-seed-controlled-full-recollection/acceptance.md`
  - `.agents/runs/prof-seed-controlled-full-recollection/verification.md`
- No schema migration, public API change, dependency addition, cleanup, or data
  deletion is introduced by this change.
