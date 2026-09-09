# Slice Contract: s10d-gap-remediation-mechanics-green

## Status

Accepted at `2026-07-15T06:47:34Z`. This is the pure mechanics GREEN predecessor for OpenSpec Task
10.3. It implements only the already-Accepted S10C typed linkage/transition contract. It does not
check Task 10.3, claim durable or operational gap closure, or consume S8/S9 runtime effects. The
global ledger remains 54/80.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `10.3` (pure GREEN predecessor only; the task remains unchecked)
- Depends on: Accepted S7 build/release contracts, Accepted S10B gap creation/classification, and
  Accepted S10C three-group remediation RED
- Parallel-start authority: S10C freezes the complete synthetic typed input/result/refusal mechanics;
  no reviewed S2C case, live query/answer trace, provider, persistence, or active release is consumed

## Goal

Extend the existing deep module without adding another service:

```python
class KnowledgeGapFeedback:
    def record(self, signal: GapSignal) -> KnowledgeGap: ...
    def apply_remediation(
        self, request: GapRemediationRequest
    ) -> GapRemediationResult: ...
```

Implement exactly the Accepted S10C behavior:

1. Typed, immutable, content-bound offline remediation and intended-effect receipts bind the exact
   gap, source/candidate releases, affected domain/path, offline run, source batches, landing
   artifacts, build run, review evidence, query/answer/benchmark traces, scenario, and time order.
2. A reviewed offline receipt linked to a candidate release produces a deterministic `linked` result
   whose gap remains unresolved and preserves every original fact. Only an exact accepted candidate,
   accepted zero-deviation release verification, and later accepted intended-effect verification
   produce a deterministic `resolved` result with accepted review and exact resolution evidence.
3. Revalidate constructed Pydantic inputs and fail closed on every S10C cross-wire, stale/tampered/
   duplicate, caller-final-gap, incomplete lifecycle, online-only, and clock/request ordering case
   without mutating the original gap. Same input is stable and changed input separates without
   freezing transition-ID encoding.

## Non-goals

- Do not implement persistence, durable dedup/update, queues, retries, scheduling, provider
  recollection, landing/build execution, publication, telemetry ingestion, or admin/API/UI wiring.
- Do not consume real S8/S9 query/answer results or claim that a synthetic intended-effect receipt is
  operational acceptance evidence.
- Do not implement universal remediation-kind compatibility, prioritization, SLA/cost, rollback,
  reopen/dismiss, multi-gap batches, or Tasks 10.4/10.5.
- Do not change shared `KnowledgeGap`, CandidateRelease, ReleaseVerification, release/publication,
  database/index, source, or public API contracts outside the existing module surface.
- Do not check Task 10.3 or aggregate S10; complete Task 10.3 still requires accepted operational
  query/answer effect evidence and a separately Ready integration slice.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_gap_feedback.py`.
- `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_remediation_contract.py` only to remove
  the three strict RED xfail decorators/reason after first proving the exact unmasked RED; assertions,
  fixtures, hostile matrices, and exact-target sentinel remain unchanged or may be strengthened.
- This Slice Contract and, after Candidate review, existing change-log/agent-link, portfolio,
  mainline-plan, and verification evidence files. `tasks.md` remains unchanged.

## Interface and seam constraints

- `KnowledgeGapFeedback.apply_remediation` is the only new behavior method. Validation, replay,
  content identity, lineage closure, and state transition stay hidden in the existing module.
- `OfflineRemediationReceipt`, `GapEffectVerification`, `GapRemediationRequest`, and
  `GapRemediationResult` are strict immutable module-owned contract models. Caller-provided final gap,
  state/review/resolution fields, extras, or ambient defaults are forbidden.
- `GapRemediationResult.content_sha256` binds the complete result except itself and the opaque
  `transition_id`; `remediation_input_sha256` binds the exact request. Transition ID must be stable
  for the same normalized input and different for changed inputs, but its encoding is private.
- Existing `record` behavior, factory/classifier degradation, and the public `KnowledgeGap` shared
  contract stay unchanged.

## Forbidden changes

- Any other production/shared-contract/migration/database/index/provider/admin/chat/query/answer/
  source file or existing Accepted test assertion.
- Persistence, network, Docker/database/Milvus writes, active pointer or candidate release mutation,
  test-local implementation, broad exception masking, weakened validation, xfail replacement,
  hardcoded fixture IDs, or transition-ID encoding assertions.
- A second remediation/lifecycle service or a compatibility branch for online evidence.

## Expected unchanged behavior

- Accepted S10A/S10B gap trigger/classification behavior remains GREEN and byte-compatible.
- Accepted S7 KnowledgeBuild/ReleasePublication behavior remains GREEN; no release/index pointer is
  changed.
- S8Q1/S8W/S8S/S9 and interface REDs remain exact expected xfails.
- Original PostgreSQL/Milvus/forensic sources, recovery lab, candidate/index state, and active
  pointers remain unchanged.

## Required checks

- After removing only the three S10C xfail decorators, focused execution reports exactly three real
  failures caused only by `_MissingKnowledgeGapRemediationContract`; no assertion is weakened.
- After implementation, the same focused file reports exactly `3 passed` with no xfail/XPASS.
- Accepted S10A/S10B plus shared gap lifecycle and targeted KnowledgeBuild/ReleasePublication owner
  tests pass unchanged.
- Complete no-external Canonical V2 reports `299 passed, 141 skipped, 23 xfailed` with no real
  failure; the only count change from the S8Q1 checkpoint is S10C's three RED groups becoming GREEN.
- Ruff check/format and Canonical V2 Pyright pass for changed/applicable scope.
- Strict OpenSpec, `git diff --check`, scope, secret, generated-cache, package-content, and frozen-
  source checks pass.
- At least one independent implementation/test-integrity review reports zero open Critical/Important
  findings. Minor/YAGNI findings are recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `change-log.md` and `agent-links.md` after GREEN Candidate acceptance; `tasks.md` stays
  unchecked until full Task 10.3 integration/operational acceptance.
- `.agents/portfolio.md` and the current code-grounded mainline plan after acceptance.

## Stop conditions

- Correct mechanics require a shared-contract/public API change, persistence, live provider, real
  query/answer effect, or active release/index mutation rather than the Accepted S10C contract.
- An online receipt, caller-resolved gap, bare accepted label, unrelated verification, stale/tampered
  nested model, or cross-wired lineage can transition or mutate the gap.
- Implementation needs another service/module, broadens into Task 10.4/10.5/S11, changes Accepted
  S10B behavior, weakens a test, or retains an unresolved Critical/Important finding.

## Done means

- The three Accepted S10C groups are GREEN through the existing module/factory with all named hostile
  matrices and identity invariants intact.
- Owner/full no-external/static/strict/package/source checks and independent review pass with zero
  open Critical/Important findings.
- S10D is Accepted as pure mechanics only; Task 10.3, Tasks 10.4-10.5, aggregate S10, and the 54/80
  ledger remain open/unchanged.

## Plan

1. Remove only the three S10C xfail decorators and capture the exact three-sentinel RED.
2. Add strict module-owned models, `apply_remediation`, validation, transition, and result identity in
   `knowledge_gap_feedback.py` until the exact file is GREEN.
3. Run S10 owner/full no-external/static/strict/package/source checks and independent read-only review.
4. Persist pure-mechanics acceptance without checking Task 10.3. Do not begin durable/operational
   integration without a separate Ready Slice Contract.

## Rollback note

Revert the production module extension, restore the three exact S10C xfail decorators, and remove
this contract/evidence. No external state exists to roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256 is
  `17b2b66a3fbc6a72e1d2f80dab8586f0401cadbf21b8e5f3a32251e8c8646160`; final production/test
  SHA-256 values are `c611acd75e3d8c9e10fdcadad6908fb1ef752eb1e4db86f30fb182dceb4d7115`
  and `03dece88753f30a0242b6724a5504c3ed4b1df8117ba4b8c10a5f8cb2063be89`.
- Before GREEN, removing only the three Accepted S10C xfail wrappers produced exactly three real
  `_MissingKnowledgeGapRemediationContract` failures. Final focused execution is `3 passed` under
  warnings-as-errors; the exact S10A/S10B/shared-lifecycle/KnowledgeBuild/ReleasePublication owner
  matrix is `18 passed`.
- Typed content-bound receipts and request/result records now reject online evidence, constructed-
  model tamper, incomplete lifecycle, duplicate/cross-wired scope and lineage, source-release self-
  closure, stale requests, non-later effect verification, and caller-supplied final state before
  producing an immutable linked or resolved gap. Same validated requests replay stably within the
  ephemeral instance even under an advancing clock; changed inputs remain distinct.
- Complete no-external Canonical V2 is exactly `299 passed, 141 skipped, 23 xfailed`; the only
  checkpoint count change is the three S10C groups becoming GREEN. Complete Canonical V2 Ruff and
  Pyright, changed-file format, strict OpenSpec, `git diff --check`, scope/secret/cache, and package
  gates pass.
- The locked offline wheel SHA-256 is
  `78f4cd8a199de8ba79141528c3db958b65c05ea5ce20056d7d932162fa8a4791`, contains 273 entries and the
  updated `knowledge_gap_feedback.py`, and excludes tests and `.agents` artifacts.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery remains network-
  none/no-port/restart-no; original Milvus SHA-256 remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Two independent final reviews report zero Critical/Important findings. Nonblocking Minor notes:
  the ephemeral replay cache is unbounded for a future long-lived singleton; opaque `transition_id`
  is excluded from result content identity; and one stale-case loop asserts the base immutable gap
  while a directed probe also confirmed the exact stale input remains unchanged. External receipt
  truth, universal remediation-kind policy, and cross-instance/concurrent/durable replay remain
  explicit YAGNI for a future operational integration slice.
- Task 10.3 remains unchecked, aggregate S10 remains open, and the OpenSpec ledger remains 54/80.
  No persistence, provider, database/index/source, active pointer, Commit, Push, PR, archive, or
  Cutover changed.
