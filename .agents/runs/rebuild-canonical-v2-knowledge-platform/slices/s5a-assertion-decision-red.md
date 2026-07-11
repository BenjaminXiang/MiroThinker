# Slice Contract: s5a-assertion-decision-red

## Status

Accepted at `2026-07-11T22:58:11Z` under the approved OpenSpec and the user's
objective-verification self-approval authorization. This is a test-only strict RED slice; it does
not authorize Task 5.2 implementation or any canonical/database/source/index write.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `5.1`
- Depends on: Accepted S4/task 4.5 at commit `cf9691d`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s5-assertion-decision-red-plan.md`

## Goal

Define independently executable behavior scenarios that force future canonical decision logic to
retain competing field and relationship assertions, apply deterministic candidate constraints
before structured LLM adjudication, preserve unresolved conflicts, and derive only evidence-backed
generic current selections.

## Non-goals

- Implement the decision module, repository, PostgreSQL adapter, migration, or shared types.
- Resolve, merge, split, reverse, or publish canonical identities.
- Define full validity/history policy, human-review queues, or reversal acceptance.
- Build typed Professor/Company/Paper/Patent projections or the relationship catalog.
- Implement `KnowledgeBuild`, candidate manifests, publication, Milvus, retrieval, or answers.
- Assert Professor–Paper attribution effects on Paper identity.

## Allowed scope

- One focused test under `apps/miroflow-agent/tests/canonical_v2/`.
- This slice/plan, OpenSpec task/change log, and verification contract/evidence.
- Deterministic synthetic assertions/identities and a recorded structured-LLM adapter contract.

## Forbidden changes

- Any file under `apps/miroflow-agent/src/` or `canonical_v2_alembic/`.
- Any database, accepted checkpoint, original/recovery source, Milvus client/file, live provider,
  dependency, runtime, domain, chat, retrieval, admin, or benchmark mutation.
- Direct SQL/table/repository assertions or mock call-count/order assertions.
- A local fake decision engine that fabricates the expected result.
- A normal failing suite. Intentional RED must use strict `xfail` limited to the missing future
  `canonical_decision_engine` module and must be separately demonstrated with `--runxfail`.

## Expected unchanged behavior

- S1–S4 acceptance, S2 corpus/threshold/backup evidence, S4 external checkpoint, legacy runtime, and
  original source invariants remain unchanged.
- Candidate stays C2_0004 with the exact accepted bounded landing state and zero canonical/domain/
  release/index rows.
- The four existing Task 3.1 strict xfails remain for KnowledgeBuild, KnowledgeRead,
  KnowledgeAnswer, and ReleasePublication.

## Task 5.2 GREEN handoff

- Reconcile shared `CanonicalDecision` release scope with the existing release-scoped database key.
- Reconcile shared relationship assertion/decision type versions with existing database columns.
- Retain canonical raw output bytes or equivalent artifact identity, verify their SHA-256, and bind
  the schema-validated output to that content in the typed/persisted trace.
- Reject overlapping selected/conflicting assertion roles in shared validation and durable storage.
- These repairs are required by existing OpenSpec behavior and schema alignment; they are not
  implemented or silently waived by this RED slice.

## Required checks

- Focused normal Task 5.1 run: exactly five strict xfails and zero failures/errors/XPASS.
- Focused forced RED: exactly five failures, all caused by absent
  `src.data_agents.canonical_v2.canonical_decision_engine` and no other error class.
- Once that module exists, any nested missing dependency must fail normally rather than be masked by
  the strict RED marker.
- Canonical V2 no-DB regression, S1 target safety, S2/S2B, Ruff, Pyright, strict OpenSpec, and
  diff/secret checks pass.
- Final read-only formal gate, original pause/volume/hash, recovery isolation, and candidate
  revision/table/row checks match the S4 acceptance checkpoint.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- A scenario requires a product/interface choice not traceable to approved OpenSpec.
- The test can pass when only local fake outputs/types exist and no concrete decision behavior runs.
- The RED failure is anything other than the absent future module.
- Task 5.2+, schema, source, provider, or runtime work becomes necessary.
- A proposed generic current selection becomes a typed domain or published projection.

## Done means

- Five scenarios express all Task 5.1 effects through one decision batch/result seam.
- Normal/forced RED shapes are exact, regressions/static/safety checks pass, and evidence is current.
- Task 5.1 is Accepted and committed alone; task 5.2 has not started in the same commit.

## Acceptance checkpoint

- Five tests cover retained/current field selection, exact deterministic survivor filtering before
  recorded adjudication, content-bound structured LLM trace and order-independent replay,
  unresolved field no-projection behavior, and accepted/unresolved relationship symmetry.
- Tests drive a future concrete ephemeral `CanonicalDecisionEngine`; only the structured-LLM port
  is recorded. They do not fake engine results, expose SQL/repository calls, or awaken Task 7.2
  `KnowledgeBuild`.
- Normal focused pytest reported exactly `5 xfailed`; forced `--no-cov --runxfail` reported exactly
  `5 failed`, all `ModuleNotFoundError` for the exact absent target module. An exact `exc.name` guard
  prevents future nested missing dependencies from being masked.
- Canonical V2 no-DB regression was `73 passed, 33 skipped, 9 expected xfails`; S1 was `10 passed,
  5 skipped`; S2/S2B was `32 passed`. Ruff check/format, Pyright, strict OpenSpec, and diff checks
  passed.
- Formal S2B admission remained Accepted for 50 sources. Original Postgres stayed paused on the
  exact source volume; original/backup Milvus and salvage hashes matched. Candidate stayed
  C2_0004 with landing `15/6/6/21/6` and zero canonical/release rows; the frozen S4 checkpoint
  remained 0550/0440.
- Independent review found and closed exact-xfail masking, unbound source-preference policy,
  unbound LLM output hashes, missing unresolved-relationship coverage, and undocumented Task 5.2
  shared-contract/schema reconciliation. Final review reported zero Critical/Important findings.
- No production/shared-contract/migration/database/source/index/provider/runtime file or state was
  changed. `acceptance.md` canonical-knowledge outcomes and S5 overall remain unaccepted.
