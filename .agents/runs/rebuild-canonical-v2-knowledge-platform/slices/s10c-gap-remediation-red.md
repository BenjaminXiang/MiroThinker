# Slice Contract: s10c-gap-remediation-red

## Status

Accepted at `2026-07-15T05:35:23Z`. This synthetic fixture-only RED predecessor freezes the missing
remediation/lifecycle behavior for OpenSpec Task 10.3 without checking Task 10.3 or claiming
production gap closure. Exact RED, owner regressions, complete no-external regression, static/
strict/package/source checks, and two independent final review tracks pass with zero Critical/
Important findings. It does not consume S2C reviewed cases or Accepted S8/S9 runtime traces.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `10.3` (RED predecessor only; the task remains unchecked)
- Depends on: Accepted S3 shared `KnowledgeGap`/release contracts, Accepted S7 build/release
  substrate, and Accepted S10A/S10B `KnowledgeGapFeedback.record` behavior
- Parallel-start authority: synthetic gap/build/release/effect fixtures do not execute the S2C
  acceptance oracle; S2C3C2/S2C3C3 therefore do not block this RED

## Goal

Freeze three strict RED groups through one extension of the existing deep module:

```python
class KnowledgeGapFeedback:
    def record(self, signal: GapSignal) -> KnowledgeGap: ...
    def apply_remediation(
        self, request: GapRemediationRequest
    ) -> GapRemediationResult: ...
```

1. The specification's missing-relationship scenario can link a reviewed offline relationship-
   repair receipt to its exact gap, original release/trace/scope, offline run, source/landing inputs,
   build run, and candidate release. Before accepted release plus intended-effect proof, the gap
   remains unresolved with no resolution fields. Online Web/model output can remain answer evidence
   but cannot act as an offline remediation receipt or close the gap.
2. Resolution requires the exact linked candidate release in accepted state, accepted exact-
   parity release verification, and accepted verification of the original affected user/operational
   effect. The resolved result preserves gap identity, class, original release/traces, demand/PRD
   impact, creation time, and remediation lineage while adding only the accepted resolving release,
   verification evidence, accepted review state, and later update time.
3. Cross-gap, cross-release, cross-run, wrong-path, stale, tampered, duplicate, caller-constructed,
   candidate-only, verified-only, rejected, online-only, and release-only-without-effect inputs fail
   closed without mutating the original immutable gap.

## Non-goals

- Do not implement Task 10.3 GREEN, persistence, durable dedup/update, a queue, retries, automatic
  remediation, provider collection, admin UI/API, telemetry ingestion, or consumer wiring.
- Do not execute real recollection, landing, build, publication, query/answer acceptance, S2C
  judging, or active release/index mutation.
- Do not define universal remediation scheduling, prioritization, SLA, cost, rollback, reopen,
  dismissal, or multi-gap batch policy.
- Do not freeze a gap-class-to-remediation-kind compatibility matrix; this RED uses only the active
  specification's missing-relationship/relationship-repair scenario.
- Do not check Task 10.3 or claim aggregate S10 acceptance from RED evidence.

## Allowed scope

- One new test owner:
  `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_remediation_contract.py`.
- This Slice Contract and, after Candidate review, existing change-log/agent-link, portfolio,
  mainline-plan, and verification evidence files. `tasks.md` remains unchanged for this RED.
- Synthetic immutable `KnowledgeGap`, build/release verification, offline remediation, and intended-
  effect verification fixtures only.

## Interface and seam constraints

- `KnowledgeGapFeedback.apply_remediation` is the only new behavior method. Parsing, content
  identity, lineage closure, transition validation, and conservative refusal remain hidden.
- A request carries an existing immutable gap plus typed receipts; it never carries a caller-created
  final `KnowledgeGap` or caller-selected final status/review/resolution fields.
- Remediation and effect receipts are content-addressed and identify the exact gap, release, offline
  run/build, affected domain/path, timestamps, and evidence IDs needed for cross-wire validation.
- The result returns the transitioned gap plus an immutable transition/remediation receipt. Tests
  assert public values, complete content identity, same-input stability, different-input separation,
  and typed failure behavior, not private call order/helpers.
- An accepted release label alone is insufficient: release identity/parity evidence and an
  accepted intended-effect verification bound to the original gap scope are both required.

## Forbidden changes

- Any production/shared-contract/migration/database/index/provider/admin/chat/query/answer/source
  file, including `knowledge_gap_feedback.py` and `contracts.py`.
- Existing Accepted S10A/S10B/shared/release assertions, active pointers, candidate/index state,
  original PostgreSQL/Milvus/forensic sources, or external credentials/network calls.
- A second public lifecycle service, test-local implementation, hand-built returned resolved gap,
  broad exception-mask xfail, `importorskip`, runtime `pytest.xfail`, private call-order assertion,
  or reference prose/model memory as truth.

## Expected unchanged behavior

- Accepted S10A/S10B record/classification behavior and shared `KnowledgeGap` validation remain
  GREEN and byte-unchanged.
- Accepted S7 build/release/publication behavior remains GREEN; no release pointer is changed.
- Existing KnowledgeRead/KnowledgeAnswer fixture REDs remain expected.
- S2C3C2 remains externally pending and blocks only reviewed calibration/claim-level S8/S9 oracle
  execution, not this synthetic S10C RED.

## Required checks

- Focused normal execution reports exactly three strict xfails and zero failures/errors/XPASS.
- Focused `--runxfail` reports exactly three failures caused only by the exact absent Task 10.3
  remediation-contract sentinel in `src.data_agents.canonical_v2.knowledge_gap_feedback`.
- Accepted S10A/S10B plus shared gap lifecycle and targeted KnowledgeBuild/ReleasePublication
  contract tests pass unchanged.
- Complete no-external Canonical V2 reports no real failure and exactly the existing 19 named xfails
  plus these three S10C groups.
- Ruff check/format and Canonical V2 Pyright pass for changed/applicable scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- At least one independent review reports zero open Critical/Important findings. Minor/YAGNI
  findings are recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `change-log.md` and `agent-links.md` after RED Candidate acceptance; `tasks.md` stays
  unchecked until Task 10.3 GREEN.
- `.agents/portfolio.md` and the current code-grounded mainline plan after acceptance.

## Stop conditions

- The RED cannot express exact linkage through one existing deep-module boundary without changing a
  shared/production contract.
- Correct behavior depends on real S8/S9 acceptance traces, live provider truth, durable storage, or
  an active release/index mutation rather than typed synthetic fixtures.
- A caller-created resolved gap, bare accepted-state label, unrelated verification ID, online Web/
  model receipt, or cross-wired lineage can satisfy the test.
- The RED needs a second public lifecycle service, masks nested failures, broadens Task 10.3 into
  Task 10.4/10.5/S11, or retains an unresolved Critical/Important finding.

## Done means

- Three strict groups close offline-linkage, accepted-release-plus-effect closure, and cross-wire/
  online/tamper refusal through `KnowledgeGapFeedback.apply_remediation`.
- Exact RED, accepted-owner regressions, complete no-external/static/strict/package/source checks,
  and independent review pass with zero open Critical/Important findings.
- S10C RED is Accepted as a predecessor only; Task 10.3 and Tasks 10.4-10.5 remain open.

## Plan

1. Add three exact-target strict RED groups without changing production/shared contracts.
2. Prove normal/forced RED identity and accepted S7/S10 owner regressions.
3. Run complete no-external/static/strict/package/source checks and independent read-only review.
4. Persist RED acceptance. Do not implement GREEN without a separate Ready Slice Contract.

## Rollback note

Remove the new RED test, this contract, and its RED acceptance evidence. No external state exists to
roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `9eb04505041732a36950a2678dd907fc46bdd6f36bdb6839408f95c603bbac0d`; final test SHA-256 is
  `21baad0207cbb79921c0e318ce4144ddef29b1f7c409949f4c5880ba862c0d3f`.
- Focused normal execution is exactly `3 xfailed`; forced `--runxfail` is exactly three
  `_MissingKnowledgeGapRemediationContract` failures naming only the absent
  `GapEffectVerification`, `GapRemediationRequest`, `GapRemediationResult`,
  `OfflineRemediationReceipt`, and `KnowledgeGapFeedback.apply_remediation` target surface.
- The linkage group retains one open missing-relationship gap and binds the exact original release,
  trace/scope, offline run, source batch/landing/build inputs, and candidate release. Online Web or
  model output cannot act as the offline remediation receipt or prematurely resolve the gap.
- The closure group requires the exact accepted candidate, accepted exact-parity release
  verification, and a later accepted intended-effect verification bound to the original query/
  answer traces, benchmark case/scenario, domain, and path. The transitioned gap preserves original
  facts and adds only content-bound resolution fields.
- Hostile matrices independently reject cross-gap/release/domain/path/run/source/build/manifest/
  review/trace/scenario/time wiring, stale or rehashed nested/outer tamper, duplicates, caller-
  supplied final gaps, candidate-only, release-only, rejected, and online-only evidence without
  mutating the original immutable gap. Result and transition identities are stable for equal inputs
  and separate changed inputs without freezing an implementation-specific ID encoding.
- Accepted S10A/S10B, shared lifecycle, KnowledgeBuild, and ReleasePublication owner regressions are
  `15 passed`. Complete no-external Canonical V2 is `296 passed, 141 skipped, 22 xfailed`; the three
  additions are exactly these S10C RED groups. Targeted Ruff check/format and Canonical V2 Pyright
  pass.
- Strict OpenSpec, `git diff --check`, scope/secret/cache checks, and locked offline package checks
  pass. The wheel has SHA-256
  `af7332f68739a5d87c87639089765580a0e446f3788d2d8aeeb87ade1c884d00`, contains 273 entries and
  Accepted `knowledge_gap_feedback.py`, and excludes tests/`.agents` and any S10C production module.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery remains network-
  none/no-port/restart-no; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Specification and test-integrity final reviews each report zero Critical/Important findings. Two
  nonblocking YAGNI notes remain: do not expand a universal remediation-kind compatibility matrix,
  and do not freeze transition-ID encoding. Task 10.3 and the 54/80 ledger remain unchanged.
