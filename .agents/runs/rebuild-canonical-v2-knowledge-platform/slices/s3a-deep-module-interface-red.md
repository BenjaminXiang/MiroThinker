# Slice Contract: s3a-deep-module-interface-red

## Status

Accepted at `2026-07-11T16:31:48Z` under the user's objective-verification self-approval
authorization. This is a test-only RED contract; it does not implement shared types and does not
authorize any task 3.2 database write without that task's own Ready slice and target proof.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `3.1`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s3-interface-contract-plan.md`

## Goal

Define independently executable public-interface contract tests for `EvidenceLanding`,
`KnowledgeBuild`, `KnowledgeRead`, `KnowledgeAnswer`, and `ReleasePublication`. The tests must express
typed request/result shapes and observable outcomes while remaining independent of future storage,
provider, orchestration, and adapter implementations.

## Non-goals

- Create Canonical V2 schemas, migrations, tables, or database targets.
- Implement shared production types or any of the five modules.
- Choose internal Postgres, Milvus, Web, LLM, parser, identity, or publication algorithms.
- Make later behavior scenarios GREEN or weaken their OpenSpec requirements.

## Allowed scope

- `apps/miroflow-agent/tests/canonical_v2/test_*_interface.py`.
- This slice contract, its implementation plan, OpenSpec task/change-log state, and verification
  evidence.
- Local recording adapters inside tests solely to prove that the public interface can express the
  required observable outcomes.

## Forbidden changes

- Any file under `apps/miroflow-agent/src/`.
- Alembic/history, Postgres, Milvus, provider, retrieval, chat, admin, or source data changes.
- Imports or assertions that expose internal table names, collection names, helper calls, execution
  order, or mock call counts as public behavior.
- A normal test-suite failure: intentional RED must be isolated with strict `xfail` and separately
  demonstrated with `--runxfail`.

## Expected unchanged behavior

- Current application/runtime behavior, public payloads, S2 corpus/thresholds, S2B manifests, and
  original-source invariants remain unchanged.
- No database or provider is accessed by the interface contract tests.

## Required checks

- Normal focused run exits `0` with exactly five strict xfails.
- The same focused run with `--runxfail` exits nonzero with exactly five expected missing-interface
  RED failures.
- Ruff and Pyright pass for the five tests.
- Strict OpenSpec validation and `git diff --check` pass.
- Repository/source safety state remains unchanged; no DB/Milvus/provider command is required.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/change-log.md`

## Stop conditions

- A test requires behavior or a field not traceable to the approved OpenSpec design/specs.
- The desired interface exposes an implementation seam only to make a test convenient.
- Normal pytest cannot isolate the intentional RED without hiding unexpected failures.
- Any implementation, database, index, provider, or source mutation becomes necessary.

## Done means

- Five focused tests define the named methods and typed observable results at the public seam.
- Normal execution reports five strict xfails; forced RED reports five failures for the absent
  Canonical V2 modules rather than test syntax/setup errors.
- Task 3.1 and verification evidence are updated, scope is clean, and one task-level commit exists.

## Acceptance checkpoint

- Normal focused pytest: exit `0`, exactly `5 xfailed`, zero failures/errors/XPASS.
- Forced RED with `--runxfail`: exit `1`, exactly `5 failed`, each caused by the absent future
  `src.data_agents.canonical_v2` seam and no collection/syntax/setup error.
- Ruff passed; Pyright reported zero errors/warnings/information.
- Existing S2/S2B suite remained `32 passed`; formal S2B gate remained `state=accepted` for 50
  sources; strict OpenSpec validation and source invariants passed.
- No `apps/miroflow-agent/src/` file, database, Milvus file, provider, or source artifact changed.
