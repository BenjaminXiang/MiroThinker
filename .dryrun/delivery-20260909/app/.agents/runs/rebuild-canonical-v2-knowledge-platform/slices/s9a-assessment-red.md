# Slice Contract: s9a-assessment-red

## Status

Accepted at `2026-07-15T02:32:31Z`. This test-only RED slice completes OpenSpec Task 9.3. Exact RED,
complete no-external regression, static/strict/package/source checks, and the targeted review repair
pass. Independent re-review reports zero Critical/Important findings. It uses synthetic typed
assessment intent/evidence fixtures and does not consume the pending S2C corpus as an acceptance
oracle.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `9.3`
- Depends on: Accepted S3A `KnowledgeAnswer.answer(TurnRequest) -> TurnResult` interface contract and
  the frozen shared evidence shape from the S3A `KnowledgeRead` interface test
- Parallel-start authority: `agent-links.md` permits S9 answer/session RED against typed evidence
  fixtures; production answer behavior still consumes an Accepted S8 evidence/trace result

## Goal

Freeze three strict RED groups through the single future `KnowledgeAnswer.answer` interface:

1. parameterized technical-strength, competitiveness, maturity, and expert-standing assessment
   intents preserve explicit user criteria ahead of model-selected dimensions;
2. when the user supplies no criteria, a schema-validated selector may choose a small per-turn
   dimension set from the current question and evidence rather than a global registry;
3. every dimension binds current evidence and returns a supported conclusion, disclosed conflict,
   or `insufficient_evidence` plus uncertainty; the overall assessment remains conditional answer-
   scoped synthesis without a numeric or canonical score or fixed/universal weighting.

## Non-goals

- Do not implement Task 9.4, `knowledge_answer.py`, `KnowledgeRead`, production assessment, prose
  generation, HTTP/chat rendering, provider clients, prompts, sessions, or continuation offers.
- Do not implement Task 9.1/9.2 base claim selection/citation, Task 9.5+ multi-turn behavior, or
  aggregate S9 acceptance.
- Do not materialize the Task 9.1 human-reviewed query bank, consume S2C pending cases/reference
  prose, run an LLM judge, or claim an Accepted S8 evidence trace.
- Do not introduce a public Assessment module, global dimension registry, fixed dimension catalog,
  universal weights, numeric score, canonical quality label, database/index write, or production-like
  target.

## Allowed scope

- One new test owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_answer_assessment_contract.py`.
- This Slice Contract and, after Candidate review, existing OpenSpec task/change-log/agent-link,
  portfolio, mainline-plan, and verification evidence files.
- Synthetic future-shaped `EvidenceSet`, `AssessmentIntent`, selector proposal, `TurnRequest`, and
  `TurnResult` fixtures only. The test imports the absent answer target first and cannot claim the
  future `KnowledgeRead` module exists today.

## Forbidden changes

- Any production/shared contract/migration/provider/runtime/source/database/index/consumer file.
- A second public answer or Assessment interface; all observable behavior must emerge from
  `KnowledgeAnswer.answer(TurnRequest) -> TurnResult`.
- A test-local `KnowledgeAnswer` implementation, broad `ModuleNotFoundError` xfail, private call-order
  assertion, reference-prose oracle, or model-memory evidence.
- Any Task 9.4/S9/Task 9.1/S8/S2C acceptance claim.

## Expected unchanged behavior

- S10A/S10B and all S1-S7 Accepted behavior remain unchanged.
- S2C3C2 remains Ready and externally pending; S8/S9 corpus acceptance execution remains blocked.
- Existing KnowledgeRead and KnowledgeAnswer S3A interface xfails remain expected.
- Original Postgres/Milvus/forensic sources, candidate/index state, and active pointers remain
  unchanged.

## Required checks

- Focused normal execution reports exactly three strict xfails and zero failures/errors/XPASS.
- Focused `--runxfail` reports exactly three failures caused only by the exact absent
  `src.data_agents.canonical_v2.knowledge_answer` target sentinel.
- Complete no-external Canonical V2 has no real failure and only KnowledgeRead, the existing S3A
  KnowledgeAnswer interface, and these three S9A scenarios as named xfails.
- Ruff check/format and Canonical V2 Pyright pass for changed/applicable scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- One independent review reports zero open Critical/Important findings. Minor/YAGNI findings are
  recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, and `agent-links.md` only after complete Task 9.3 RED
  acceptance.
- `.agents/portfolio.md` and current code-grounded mainline plan after acceptance.

## Stop conditions

- A test requires a behavior absent from the active answer/assessment OpenSpec capability.
- The fixture must claim Accepted S8/S2C runtime/oracle evidence, or the test introduces another
  public Assessment seam.
- RED can pass through a local answer implementation, broad exception masking, or assertion-order
  accident.
- A production/shared-contract change or unresolved Critical/Important finding is needed to accept
  this test-only slice.

## Done means

- Three strict groups cover all named Task 9.3 assessment families and selection/evidence/
  supported/conflicting/missing/uncertainty boundaries through the future single answer interface.
- Exact RED, static/strict/scope/package/source checks, and independent review pass with zero open
  Critical/Important findings.
- Task 9.3/S9A is Accepted as RED only; Tasks 9.1-9.2 and 9.4-9.8 remain open.

## Plan

1. Add three exact-target strict RED groups without production/shared-contract edits.
2. Prove normal and forced RED identity, then run complete no-external/static/strict/package/source
   checks.
3. Obtain independent read-only review and repair only Critical/Important findings.
4. Persist Task 9.3 RED acceptance. Do not implement Task 9.4 without Accepted production
   predecessors and a separate Slice Contract.

## Rollback note

Remove the new RED test, this contract, and its status/evidence entries. No external state exists to
roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `1378e7d9caac5e1044c3b0d2c9be7d53914c10f174909222483f1149b6981e80`; final test SHA-256 is
  `33f8027959554be5c4f0f8a3f772293a694be8538ffed7d9c75cb7939e7fd34c`.
- Focused normal execution is exactly `3 xfailed`; forced `--runxfail` is exactly three
  `_MissingKnowledgeAnswerModule` failures for the absent
  `src.data_agents.canonical_v2.knowledge_answer` target. The answer target is imported before the
  future KnowledgeRead dependency, so nested or successor dependency failures remain real failures.
- The three groups cover all four named assessment families, explicit user-criterion precedence,
  small question/evidence-selected per-turn dimensions, and supported/conflicting/missing outcomes
  with current-evidence binding, conclusion/insufficiency, and uncertainty. Overall synthesis stays
  conditional and answer-scoped with no required registry, fixed weighting, numeric score, or
  canonical label.
- Complete no-external Canonical V2 is `296 passed, 141 skipped, 5 xfailed`; the xfails are exactly
  the future KnowledgeRead interface, existing S3A KnowledgeAnswer interface, and these three S9A
  assessment groups. Complete Canonical V2 Ruff and Pyright pass; the changed test is Ruff-formatted.
- Strict OpenSpec, `git diff --check`, scope/secret/cache, and fresh wheel checks pass. Wheel SHA-256
  remains `af7332f68739a5d87c87639089765580a0e446f3788d2d8aeeb87ade1c884d00`; it contains the Accepted
  S10B production module and excludes tests/`.agents`.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery lab remains
  network-none/no-port; original Milvus hash-only verification remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Independent review closed the conflict-disclosure and supported-outcome false-green findings;
  final counts are zero Critical/Important. Nonblocking Minor/YAGNI: the generic `weights` absence
  assertion is broader than fixed/universal weighting, and `canonical is False` is redundant with
  answer-scoped/non-persistence acceptance evidence. Neither creates a current Spec violation or
  executable bypass.
- Task 9.3/S9A is Accepted at 50/80. Tasks 9.1-9.2 and 9.4-9.8 remain open; S8/S9 claim-level corpus
  acceptance execution still awaits S2C3C2/S2C3C3. No external state, Commit, Push, PR, archive, or
  Cutover changed.
