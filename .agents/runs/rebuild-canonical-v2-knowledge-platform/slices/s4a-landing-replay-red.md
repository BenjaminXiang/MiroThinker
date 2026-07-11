# Slice Contract: s4a-landing-replay-red

## Status

Accepted at `2026-07-11T18:33:37Z` under the user's objective-verification self-approval
authorization. This is a test-only strict RED slice; it does not authorize task 4.2 implementation
or any landing/source/database/index write.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `4.1`
- Depends on: Accepted S3/task 3.5 at commit `607e558`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s4-landing-red-plan.md`

## Goal

Define independently executable behavior scenarios that force the future immutable evidence landing
to preserve byte/copy identity, retain parser-version replay history, quarantine partial/corrupt
records with readable fields and typed errors, and create no placeholder fact or canonical side
effect.

## Non-goals

- Implement `EvidenceLanding`, a parser, source adapter, repository, or composition root.
- Create or alter an Alembic revision/table/constraint.
- Read or replay actual recovery, historical, Milvus, workbook, cache, or provider bytes.
- Cover the full Task 4.4 representative source matrix or accept S4.
- Expose physical table names, repository calls, parser call counts/order, or storage layout as
  public behavior.

## Allowed scope

- New focused tests under `apps/miroflow-agent/tests/canonical_v2/`.
- This slice/plan, OpenSpec task/change log, and verification contract/evidence.
- Deterministic synthetic bytes and expected typed outcomes embedded in tests.

## Forbidden changes

- Any file under `apps/miroflow-agent/src/` or `canonical_v2_alembic/`.
- Any database, original/recovery source, Milvus client/file, provider, dependency, runtime, domain,
  chat, retrieval, admin, or benchmark mutation.
- A normal failing suite. Intentional RED must use strict `xfail` limited to the missing future
  module and must be separately demonstrated with `--runxfail`.
- A fake local subclass that returns expected receipts/records without exercising the future
  concrete landing core.

## Expected unchanged behavior

- S1-S3 acceptance, C2_0003 candidate state, S2 corpus/threshold/backup evidence, legacy runtime,
  and original source invariants remain unchanged.
- Task 3.1 remains exactly five strict xfails for the broader deep-module seams.

## Required checks

- Focused normal Task 4.1 run: exactly four strict xfails and zero failures/errors/XPASS.
- Focused forced RED: exactly four failures, all caused by absent
  `src.data_agents.canonical_v2.evidence_landing` and no other error class.
- Existing Canonical V2 no-DB/shared/interface contracts, S1 target safety, S2/S2B, Ruff, Pyright,
  strict OpenSpec, and diff checks pass.
- Final read-only formal gate, original pause/volume/hash, recovery isolation, and candidate
  revision/table/row checks match.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- A scenario requires an interface or product choice not traceable to approved OpenSpec.
- The test can pass when only local fake outputs/types exist and no concrete landing behavior runs.
- The RED failure is anything other than the absent future module.
- Runtime/schema/source/provider work becomes necessary.

## Done means

- Four scenarios express all Task 4.1 effects through `ingest/stream` and shared records.
- Normal/forced RED shapes are exact, regressions/static/safety checks pass, and evidence is current.
- Task 4.1 is Accepted and committed alone; task 4.2 has not started in the same commit.

## Acceptance checkpoint

- Four tests cover exact byte/copy lineage plus pre-stream hash rejection; replay with retained v1/v2
  parse-run outputs; partial/corrupt readable-field and typed-error preservation; and zero invented
  identity/parent/canonical effects.
- Tests target a future concrete ephemeral composition through `ingest/stream`; they do not use a
  local success-faking subclass or expose storage internals.
- Normal focused pytest reported exactly `4 xfailed`; forced RED reported exactly `4 failed`, all
  `ModuleNotFoundError` for the absent `evidence_landing` module.
- Canonical V2 no-DB regression was `23 passed, 24 skipped, 9 xfailed`; the nine are the existing
  five Task 3.1 seams plus these four Task 4.1 scenarios. S1 was `10 passed, 5 explicit skips` and
  S2/S2B was `32 passed`; Ruff and Pyright were clean.
- Strict OpenSpec, diff checks, formal S2B admission, original source invariants, and the read-only
  C2_0003 candidate state passed. No production/schema/database/source/index/provider change or
  write occurred.
