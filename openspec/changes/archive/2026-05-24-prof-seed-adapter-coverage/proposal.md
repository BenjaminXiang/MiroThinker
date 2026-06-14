## Why

The professor seed pipeline currently treats five real `miroflow_real.professor_seed`
rows as unrunnable because no registered adapter or API path matches their URL
families. P4 cannot be completed until the current seed inventory is covered by
named school-specific crawler paths, or explicitly classified as blocked with
actionable evidence.

## What Changes

- Add a row-level seed adapter coverage contract for every current
  `professor_seed` row.
- Add a deterministic coverage guard that reports each seed id, school,
  department, URL, current status, resolver result, and coverage outcome.
- Register a named SUIT/SZIIT adapter path for
  `https://zd.suit-sz.edu.cn/jyjx/jsfc.htm` and verify it with real-seed E2E.
- Investigate and handle UESTC/SIAS seed URLs under
  `https://sias.uestc.edu.cn/rcpy/dsjs1/...` with either a durable fetch/parser
  path or an approved `fetch_blocked` outcome with structured `pipeline_issue`
  evidence.
- Require row-level preview/sample E2E evidence for all 20 current real seeds
  before P4 can be marked complete.
- Preserve the existing `adapter_missing` guard: a seed without a registered
  runnable path MUST NOT silently enter the parser or full pipeline.

## Capabilities

### New Capabilities

- `professor-seed-adapter-coverage`: Defines row-level adapter coverage,
  coverage guard output, real-seed E2E evidence, and approved blocked outcomes
  for the professor seed inventory.

### Modified Capabilities

- `professor-seed-management`: Tightens adapter-missing handling so a later
  registered school adapter can unblock a seed only with named resolver
  coverage and row-level evidence.
- `professor-seed-ops-hardening`: Tightens failure-class evidence requirements
  for fetch-blocked seeds discovered during preview/sample runs.

## Impact

- Runtime code:
  - `apps/miroflow-agent/src/data_agents/professor/adapter_resolution.py`
  - `apps/miroflow-agent/src/data_agents/professor/roster.py`
  - `apps/miroflow-agent/src/data_agents/professor/school_adapters.py`
  - `apps/miroflow-agent/src/data_agents/professor/discovery.py` if UESTC/SIAS
    requires a fetch-policy change.
  - `apps/miroflow-agent/src/data_agents/professor/seed_runner.py`
  - `apps/admin-console/backend/api/seeds.py`
- New or updated tests:
  - `apps/miroflow-agent/tests/data_agents/professor/test_school_adapters.py`
  - `apps/miroflow-agent/tests/data_agents/professor/test_roster_validation.py`
  - `apps/miroflow-agent/tests/postgres/test_run_single_seed.py`
  - `apps/admin-console/tests/test_seeds_api.py`
- New operational evidence:
  - `.agents/runs/prof-seed-adapter-coverage/verification.md`
  - `openspec/changes/prof-seed-adapter-coverage/acceptance.md`
