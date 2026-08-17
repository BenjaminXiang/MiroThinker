# Slice Contract: s10b-knowledge-gap-feedback-green

## Status

Accepted at `2026-07-15T02:10:55Z`. This slice implements OpenSpec Task 10.2 against Accepted S10A
synthetic typed signal/trace fixtures. All Required checks passed with zero open Critical/Important
findings. It does not claim that S8/S9 runtime traces or S2C acceptance-oracle execution exist.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `10.2`
- Depends on: Accepted S10A/Task 10.1 RED and Accepted shared `KnowledgeGap` contracts
- Does not unlock: Task 10.3 closure, Task 10.4 admin migration, Task 10.5 aggregate verification,
  S11, or S12

## Goal

Implement one pure deep module:

```python
class KnowledgeGapFeedback:
    def record(self, signal: GapSignal) -> KnowledgeGap: ...
```

The module SHALL validate a typed observation, derive a content-bound gap identity, initial open/
unreviewed lifecycle, demand/PRD-impact accounting, severity, classification confidence, owner, and
remediation proposal, and return the shared immutable `KnowledgeGap`. It SHALL support an optional
schema-validated recorded classifier at an internal true-external seam while deterministic trigger
invariants remain authoritative and classifier failure degrades conservatively.

## Non-goals

- No database, ops-table, migration, durable deduplication/update, queue, admin UI/API, telemetry
  ingestion, live provider, prompt client, or production runtime wiring.
- No gap closure, offline recollection/build linkage, accepted-release resolution, direct canonical
  or Milvus write, or online Product-capability relationship.
- No S8/S9 production trace generation, S2C corpus oracle, LLM judge, real-provider acceptance, or
  aggregate S10 acceptance.
- No universal prioritization formula, auto-remediation workflow, or exact classification for
  semantically ambiguous user-feedback/benchmark observations.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_gap_feedback.py`.
- `apps/miroflow-agent/tests/canonical_v2/test_knowledge_gap_feedback_green.py`.
- Existing Accepted S10A behavior assertions are read-only. S10B may remove only their strict RED
  marker after implementation so the unchanged assertions become ordinary GREEN tests.
- This Slice Contract and, after Candidate review, existing OpenSpec task/change-log/agent-link,
  portfolio, mainline-plan, and verification evidence files.

## Interface and seam constraints

- `GapSignal` contains only observation facts: trigger, release, affected domains/paths, trace IDs,
  symptom, available evidence, raw demand-observation IDs, and observation time. It forbids every
  final `KnowledgeGap` outcome field.
- `KnowledgeGapFeedback.record` is the only behavior interface. Construction MAY accept a recorded
  classifier and clock through a package-internal composition factory; callers never invoke
  classifier, storage, or lifecycle stages directly.
- A classifier request is content-bound to the normalized signal and module-owned accounting. A
  response must echo that binding and validate as a typed proposal before use.
- Explicit trigger invariants remain deterministic: repeated Web and Product-capability evidence
  gaps remain knowledge coverage; missing relationships remain relationship-owned; index parity
  remains index-owned; Product remediation remains direct-evidence collection only.
- LLM/model output can propose classification/owner/remediation/severity for ambiguous cases but
  cannot set status, review acceptance, timestamps, resolution evidence, canonical mutations, or
  weaken explicit trigger invariants.

## Forbidden changes

- Shared `contracts.py`, migrations, existing accepted source/tests, database/index/release state,
  providers, chat/admin/consumer code, source evidence, or production-like targets.
- Broad exception swallowing, model-memory evidence, classifier-controlled lifecycle, caller-owned
  final outcomes, or use of reference prose as truth.
- A test-only implementation hidden inside fixtures, or tests that inspect private helper calls/
  ordering instead of `record` output and recorded adapter input.

## Expected unchanged behavior

- S10A's exact eight triggers and caller-outcome rejection assertions pass unchanged after only the
  strict RED marker is removed.
- S2C3C2 remains externally pending; S8/S9 production behavior remains blocked by Accepted
  predecessor/oracle requirements.
- All S1-S7 accepted behavior, original sources, candidate/index releases, and active pointers remain
  unchanged.

## Required checks

- Before implementation, S10A plus two S10B classifier scenarios report exactly five strict xfails;
  forced RED reports exactly five exact missing-target sentinel failures.
- After implementation, all five scenarios pass with zero xfail, including recorded-classifier
  binding and conservative invalid/exception degradation.
- Shared `KnowledgeGap` tests and complete no-external Canonical V2 pass; only KnowledgeRead and
  KnowledgeAnswer remain expected xfails.
- Ruff check/format and Canonical V2 Pyright pass for changed/complete applicable scope.
- Strict OpenSpec, `git diff --check`, production-scope, secret, generated-cache, package-content,
  and frozen-source checks pass.
- One independent review reports zero open Critical/Important findings. Minor/YAGNI findings are
  recorded and nonblocking.

## Evidence to update

- This Slice Contract.
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `change-log.md`, and `agent-links.md` only after Task 10.2 Candidate acceptance.
- `.agents/portfolio.md` and current code-grounded mainline plan after acceptance.

## Stop conditions

- GREEN requires shared-contract/schema/storage/provider/runtime changes or upstream Accepted S8/S9
  traces rather than synthetic typed fixtures.
- A classifier can override explicit trigger ownership, create accepted/resolved state, or recommend
  a canonical Product-capability relation.
- RED is masked by an unrelated exception, or any Critical/Important finding remains open.

## Done means

- Accepted S10A and S10B classifier scenarios are GREEN through one deep-module interface.
- The module returns typed, immutable, content-bound open gaps; LLM-assisted proposals are bounded
  and failure-safe; demand/PRD impact and Product-capability boundaries remain correct.
- Required checks and independent review pass with zero open Critical/Important findings.
- Task 10.2/S10B is Accepted; Tasks 10.3-10.5 and aggregate S10 remain open.

## Plan

1. Add two strict classifier/binding/degradation scenarios and prove exact RED before production.
2. Implement the smallest pure module that makes Accepted S10A plus S10B GREEN.
3. Run focused/shared/full/static/strict/package/source checks and independent review; repair only
   Critical/Important findings.
4. Persist Task 10.2 acceptance evidence. Do not start closure/admin/aggregate work without their
   accepted upstream evidence and separate Slice Contracts.

## Rollback note

Remove the new module, S10B tests, this contract, and its evidence/status entries. No external state
exists to roll back.

## Acceptance evidence

- Candidate Slice Contract SHA-256: `850bb16705bcfcc974e7334df806915a43c5c8cc43b52735bb62977fa0af0b9b`.
  Final module/S10A-GREEN/S10B-test SHA-256 values are
  `18d062499dc648551b4b923f3f3e2586be64c3c878490b2313fc6a1798d61302`,
  `661cd849f0634024005aa73ddda3eb8601132921291b93f31b419ff8e3461a29`, and
  `27b1382444cb31e284b7f9be81a677af52445a233f3c38b4f068aa35483e0f11`.
- Exact pre-implementation RED was `5 xfailed`; forced RED was exactly five target-module sentinel
  failures. Final focused S10A+S10B is `5 passed`; shared contracts plus owner is `21 passed`.
- Complete no-external Canonical V2 is `296 passed, 141 skipped, 2 xfailed`; the only xfails are the
  existing future KnowledgeRead and KnowledgeAnswer interfaces.
- The module validates observation-only signals, content-binds complete classifier input, derives
  demand/scenario accounting, and returns one immutable open/unreviewed shared `KnowledgeGap`.
  Schema-invalid, wrong-bound, timeout, and connection failures degrade deterministically;
  programmer defects propagate. Same-class Pydantic `model_construct` values are dumped and
  revalidated before use.
- Recorded classifier success remains proposal-only. All four protected triggers retain exact
  deterministic class/owner/remediation, including direct Product-capability evidence collection
  and zero canonical Product-capability mutation. Hash tests prove same-signal stability,
  single-field divergence, and stale-digest cross-wire rejection.
- Complete Canonical V2 Ruff rule checking passed; all three changed files passed format checking;
  complete Canonical V2 Pyright returned zero findings. Strict OpenSpec, `git diff --check`, scope/
  secret/cache, and fresh wheel checks passed. Wheel SHA-256 is
  `af7332f68739a5d87c87639089765580a0e446f3788d2d8aeeb87ade1c884d00`; it includes the module and
  excludes tests/`.agents`.
- Original `pgtest` remains paused on exact volume
  `d81c6381b0c7c0a975ca0ff4a0054037e72b0d4cb80174f682abceb1127cd241`; recovery lab remains
  network-none/no-port; original Milvus hash-only verification remains
  `43ef203e0b101fcbed2a6c8fcde19a35d426199d3f02bc72525d0acf618867cc`.
- Two final independent reviews report zero Critical/Important. Nonblocking Minor/YAGNI: scenario
  families are trigger-level synthetic categories until operational PRD mapping; protected triggers
  still invoke and discard a classifier result; proposal rationale participates in gap identity but
  durable dedup/update policy is deferred to later operations slices.
- Task 10.2/S10B is Accepted at 49/80. Tasks 10.3-10.5 and aggregate S10 remain open. No database,
  index, provider, source, release pointer, Commit, Push, PR, archive, or Cutover changed.
