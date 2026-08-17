# Slice Contract: s10a-knowledge-gap-trigger-red

## Status

Accepted at `2026-07-14T19:23:58Z`. This is a test-only RED slice for OpenSpec Task 10.1. It
consumes only the Accepted shared `KnowledgeGap` contract and synthetic typed signal/trace fixtures.
All Required checks passed with zero open Critical/Important findings. Task 10.2 and aggregate S10
remain open; no production implementation exists.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `10.1`
- Depends on: Accepted S3 shared typed contracts, including `KnowledgeGap`, `GapClass`, `GapStatus`,
  `ReviewState`, `GapSeverity`, and release/trace lifecycle validation
- Parallel-start authority: `agent-links.md` permits S10 RED against shared typed gap/trace fixtures;
  operational closure and admin migration still consume accepted build/release/query/answer evidence

## Goal

Freeze the smallest deep-module interface and observable RED scenarios for converting each named
Task 10.1 signal into a typed, traceable `KnowledgeGap`:

- no result;
- insufficient evidence;
- repeated current-Web dependence;
- recurring answer-scoped Product-capability demand;
- missing relationship;
- user feedback;
- benchmark failure; and
- index parity failure.

All eight triggers must preserve release, affected domain/path, symptom, available evidence, and at
least one query/answer/benchmark/telemetry trace identity. New gaps begin open and unreviewed, carry
no resolution evidence, and cannot masquerade as a canonical Product-capability relationship.

## Interface

Use one deep module at one seam:

```python
class KnowledgeGapFeedback:
    def record(self, signal: GapSignal) -> KnowledgeGap: ...
```

The caller supplies one typed observation. The module owns trigger normalization, initial
classification proposal, confidence/review state, owner/remediation proposal, demand/PRD-impact
accounting, gap identity, and persistence/adaptation details. Tests and future callers use only
`record`; classifier, storage, clock, LLM, and admin adapters remain internal seams.

## Non-goals

- Do not implement Task 10.2, `knowledge_gap_feedback.py`, LLM/provider classification, persistence,
  deduplication/update policy, remediation workflow, gap closure, admin UI/API, or operational S10
  acceptance.
- Do not implement or substitute for S8 query traces, S9 answer traces, S2C acceptance cases, or S12
  benchmark execution. Synthetic trace identities are fixtures, not Accepted upstream results.
- Do not choose one universal class for semantically ambiguous user-feedback or benchmark signals.
  Exact classification is required only where the fixture supplies the owning facts.
- Do not add Product-capability canonical state, close a gap from online evidence, or write any
  database, index, release pointer, provider, source, or production-like target.
- Do not design an operations queue, UI, durable deduplication key, automatic remediation, or a
  global priority formula in this slice.

## Allowed scope

- One new test owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_feedback_contract.py`.
- This Slice Contract and, after Candidate review, the existing OpenSpec task/change-log/agent-link,
  portfolio, mainline-plan, and verification evidence files.
- The Accepted shared `KnowledgeGap` types are read-only inputs to the RED contract.

## Forbidden changes

- Any production file under `apps/miroflow-agent/src/`, shared contract, migration, source fixture,
  database, index, active pointer, provider, runtime, consumer, or admin change.
- A test-local `KnowledgeGapFeedback` implementation or caller-selected final `KnowledgeGap` that
  makes the scenarios pass without the future target module.
- An `xfail` that catches `ModuleNotFoundError` broadly, masks a nested dependency error, or treats an
  assertion/fixture failure as the intended RED.
- Any claim that Task 10.2+, aggregate S10, S2C, S8, S9, or final candidate acceptance is complete.

## Expected unchanged behavior

- S7 and all earlier Accepted slices remain unchanged.
- S2C3C2 remains Ready and awaits attributable external human review; Task 2.8 remains open.
- S8 and production S9 behavior remain blocked by their Accepted predecessor/oracle requirements.
- Original Postgres/Milvus/forensic sources, candidate databases/indexes, and active release pointers
  remain unchanged.

## Required checks

- Focused normal execution reports exactly three strict xfails and zero failures/errors/XPASS.
- The same three scenarios with `--runxfail` report exactly three failures, each caused only by the
  exact absent `src.data_agents.canonical_v2.knowledge_gap_feedback` target sentinel.
- Existing shared `KnowledgeGap` lifecycle/enum tests pass unchanged.
- The complete no-external Canonical V2 suite has no real failure and only named future-interface
  xfails.
- Ruff check/format and Canonical V2 Pyright pass.
- Strict OpenSpec, `git diff --check`, production-scope, secret, generated-cache, package-content, and
  frozen-source checks pass.
- One independent review reports zero open Critical/Important findings. Minor/YAGNI findings are
  recorded and do not block acceptance.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, and `agent-links.md` only after complete Task 10.1 RED
  acceptance.
- `.agents/portfolio.md` and the current code-grounded mainline plan after acceptance.

## Stop conditions

- A scenario requires behavior absent from the active knowledge-gap OpenSpec capability.
- The intended RED can pass through caller-supplied final classification/gap output, broad exception
  masking, or an assertion-order accident.
- A production/shared-contract edit, external write, or unresolved Critical/Important finding is
  required to accept this test-only slice.

## Done means

- Three strict scenario groups cover all eight named Task 10.1 triggers, trace/release/domain/path/
  symptom/evidence binding, explicit classification ownership, and safe initial lifecycle through the
  future single `KnowledgeGapFeedback.record` interface.
- Normal/forced RED identity, shared-contract/no-external regression, static/strict/safety/scope
  checks, and independent review pass with zero open Critical/Important findings.
- Task 10.1/S10A is Accepted as RED only; Task 10.2 and aggregate S10 remain unstarted/open.

## Plan

1. Add three exact-target RED scenario groups without production or shared-contract edits.
2. Prove normal and forced RED identity, then run shared/no-external/static/strict/safety checks.
3. Obtain one independent read-only review and repair only Critical/Important findings.
4. Persist Task 10.1 RED acceptance evidence. Do not start Task 10.2 GREEN until its production
   predecessors and separate Slice Contract are Accepted.

## Rollback note

Remove the new RED test, this Slice Contract, and its status/evidence entries. No runtime or external
state exists to roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256: `aebb3a711aa6c785b016843d94b65c7b7a2738066a8099faed31b76b74fba1c4`.
  Final RED test SHA-256: `9b8dd6e00e1dd5e6efdc2842e523d19a2bd198166943613a2c0c9d4b4434d4b7`.
- Focused normal execution returned exactly `3 xfailed`; forced `--runxfail` returned exactly three
  failures caused by `_MissingKnowledgeGapFeedbackModule` for the exact absent target module.
- Shared contract plus RED returned `16 passed, 3 xfailed`. Complete no-external Canonical V2
  returned `291 passed, 141 skipped, 5 xfailed`; the five xfails are exactly KnowledgeRead,
  KnowledgeAnswer, and the three S10A scenarios.
- Complete Canonical V2 Ruff rule checking passed; the changed test passed Ruff format checking;
  complete Canonical V2 Pyright returned zero findings. Strict OpenSpec, `git diff --check`,
  secret/cache/scope checks, and final package-content checks passed. The fresh wheel SHA-256 is
  `aa9471c025dd129fe181e0fbb82823f57f93abb2420794e7736dcf0c4276136a` and contains no S10
  implementation, test, or `.agents` artifact.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; the recovery lab remains
  network-none/no-port; original Milvus hash-only verification remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Independent review closed module-owned outcome/accounting, Product-capability boundary, and
  repeated/recurring demand false-green findings. Final review reports zero Critical, zero
  Important, and one nonblocking Minor/YAGNI: the test composition factory is additional
  construction scaffolding outside the one-method behavior interface.
- Task 10.1/S10A is Accepted at 48/80 as RED only. No production/shared contract, database, index,
  provider, source, release pointer, Commit, Push, PR, archive, or Cutover changed.
