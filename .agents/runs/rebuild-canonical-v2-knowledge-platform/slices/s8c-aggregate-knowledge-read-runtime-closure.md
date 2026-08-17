# Slice Contract: S8C Aggregate KnowledgeRead Runtime Closure

## Status

Accepted at `2026-07-20T10:50:22Z` after Candidate evidence existed at
`2026-07-20T10:49:57Z`. Ready was reached at `2026-07-20T09:43:54Z`; the exact seven-port RED and
the subsequent public release-bound replay RED were both observed before their GREEN changes. The
minimal implementation exposes and forwards all seven existing runtime ports, admits only the
existing lane-free/disabled-Web/exact-release/exact-session handle replay shape, and retains the
protected displayed-Patent boundary. Focused, detailed-mechanics, physical/release, and complete
no-external results are respectively `1`, `8`, `13`, and `351` passes; static, package, strict,
scope, and frozen-source checks pass. The initial review's one TTL-observability Important was
closed with a public negative-TTL probe; targeted final review reports `C=0/I=0/M=0`. Tasks 8.3,
8.5, and 8.7 are Accepted together, moving the formal ledger `56/80 -> 59/80`. Tasks 8.1 and 8.8
remain unchecked for S2C/calibrated aggregate acceptance.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Requirement: `specs/evidence-first-query-orchestration/spec.md` — concurrent validated recall,
  full traceability, identity-aware late selection, evidence-bound Web handles, material-part
  sufficiency, bounded supplemental retrieval, and reproducible attempts
- OpenSpec tasks: `8.3`, `8.5`, and `8.7` (aggregate runtime closure; all remain unchecked until
  S8C is Accepted)
- Depends on: Accepted S8RG, S8S, S8E1, S8L1-L3, S8V1-V2, S8IR1, and S8R1-R5
- Readiness gate: S8R5 must be Accepted; S2C is not a dependency for this runtime-only slice
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8c/dependency-audit.md`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8c/implementation-plan.md`

## Goal

Close the release-bound `KnowledgeRead` runtime through one public execution seam:

```text
accepted isolated release + validated RetrievalPlan
  -> concurrent exact / structured / lexical / vector / relationship /
     internal_reference / current-Web lanes
  -> identity-aware evidence fusion
  -> deterministic constraints and structured late rerank
  -> bounded snapshots and typed Web handles
  -> material-part sufficiency and honest enumeration
  -> targeted budgeted supplemental retrieval
  -> traceable EvidenceSet with partial continuation when needed
```

Extend the existing `create_isolated_release_knowledge_read` composition root so it can receive and
forward the already-Accepted identity, rerank, sufficiency, supplemental, handle-resolution,
accepted-identity, and TTL ports. Admit the existing handle-replay interaction through the same
public service when it carries that service's exact release binding. Prove both operations with one
release-bound vertical owner and reuse the Accepted detailed owner matrix for hostile and edge-case
evidence.

## Required behavior

- All seven validated independent lanes execute through one release-bound service and retain
  query-view, lane, attempt, release, adapter/provider, evidence, candidate, and decision lineage.
- Independent lanes retain the Accepted bounded concurrency behavior; a release-bound composition
  must not serialize or bypass the S8RG executor.
- Identity fusion aggregates same-identity evidence before deterministic constraints and structured
  late rerank. Ordinary quality limitations do not become blanket early exclusion.
- Initial Web evidence is admitted only from bounded content-addressed bytes. The Accepted S8RF
  matrix proves distinct Web-only handle creation/tamper/change/expiry. The S8C public
  release-bound service accepts a content-bound retained-handle replay under its exact release
  binding; successful canonical resolution is read-only and retains original handle/snapshot
  lineage.
- Sufficiency is decided per material question part as supported, conflicting, or missing. The
  aggregate matrix covers `exhaustive_bounded`, `required_members`, and `representative` accounting,
  targeted wall-time/call/retry/cost budgets, unresolved limitations, best-evidence retention, and
  typed partial continuation.
- Query execution performs no online canonical identity, source-map, release, database, index, or
  original-source write.
- Public relationship acceptance is exactly Company-to-Patent, Patent-to-Company applicant,
  Professor-to-Paper attribution, and Paper-to-Professor attribution. Unsupported or
  insufficient-evidence directions return an explicit zero/limitation/gap and never an invented
  edge.

## Non-goals

- No Task 8.1 reviewed-case calibration, ambiguity threshold selection, or S2C oracle consumption.
- No Task 8.8 aggregate claim-level/provider quality, recall/rank threshold, latency, or cost
  acceptance.
- No live provider credential/network call, production threshold, product-wide TTL/size/budget
  selection, or provider implementation.
- No S9 answer/session implementation, S10 operations, S11 consumer migration, API/UI wiring,
  candidate promotion, or Cutover.
- No fifth public domain, canonical Product-capability relation, new relationship direction, name/
  URL/embedding-derived relationship, or persistence of query-time resolution.
- No second `KnowledgeRead`, fusion, rerank, sufficiency, Web-handle, provider, or composition
  framework.

## Allowed scope

- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` only to add
  optional typed composition parameters and pass them unchanged into the existing
  `create_ephemeral_knowledge_read` delegate.
- Modify `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` only in the existing
  planner-owned interaction validator: admit `handle_replay` with no lanes, disabled Web execution,
  no freshness/assessment/material-part execution, a non-empty session ID, and every retained or
  replayed handle bound to that exact session. Add no field, serializer, replay algorithm, or other
  planner behavior.
- Modify `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`
  with one S8C strict RED/GREEN release-bound vertical owner, reusing the final Accepted S8R5
  fixture/authority rather than creating a parallel release graph.
- Update this contract, the S8C plan/audit, and add an S8C verification receipt after evidence
  exists.
- After Candidate review only, update existing verification/status evidence and atomically check
  Tasks 8.3, 8.5, and 8.7 on acceptance. `acceptance.md` may record only this runtime closure and
  must leave Task 8.8 gates pending.

## Forbidden changes

- Any change to `knowledge_read.py` beyond the one finite release-bound `handle_replay` validator
  branch; any field/serialized-shape, lane algorithm, physical-adapter, schema, migration, storage,
  release-manifest, provider, answer/session, API/UI, or source-data change.
- Caller-provided `lane_adapters` on the release-bound factory, a second factory, or duplication of
  the existing physical adapter map.
- Weakening or rewriting any Accepted S8 assertion, fixture, serialized literal, content hash,
  trace, receipt, or existing Slice Contract.
- Test-local runtime implementations, private executor/call-order assertions, broad exception
  swallowing, `importorskip`, live network access, or reference prose/model memory as evidence.
- Checking only one or two of Tasks 8.3/8.5/8.7, checking Task 8.1 or 8.8, or changing the ledger
  before S8C acceptance.
- Query-time writes, Commit, Push, PR, Archive, promotion, destructive cleanup, or Cutover.

## Expected unchanged behavior

- All Accepted S1-S8 predecessor behavior and exact public serialization remain unchanged.
- `create_ephemeral_knowledge_read` and every Accepted detailed S8RG/S8S/S8RF owner remain unchanged;
  S8C exposes those ports and the already-existing replay mode through the release-bound
  composition without changing replay results.
- The release-bound factory continues to hide its local lane adapter map, exact-validate the release
  binding, reject unsupported lanes before effects, and postvalidate vector/internal-reference/
  relationship evidence against the accepted release.
- S2C continues to block only Task 8.1 calibration and Task 8.8/S9 aggregate oracle execution.
- Before S8C acceptance the formal ledger remains `56/80`. On acceptance it becomes exactly
  `59/80`, with Tasks 8.1 and 8.8 still unchecked.
- Original PostgreSQL/Milvus/forensic sources, isolated target bytes, release pointers, and external
  state remain unchanged.

## TDD RED contract

Add one exact-target owner named:

```python
def test_s8c_closes_release_bound_knowledge_read_runtime(
    request: pytest.FixtureRequest,
) -> None:
    ...
```

Before acquiring fixtures or invoking any physical/Web effect, its seam check requires
`create_isolated_release_knowledge_read` to expose the seven existing optional composition inputs:
`identity_fuser`, `reranker`, `sufficiency_decider`, `supplemental_search`,
`web_handle_resolver`, `accepted_identity_lookup`, and `web_handle_ttl`. Normal RED is exactly one
strict xfail. Forced RED is exactly one `_MissingS8CAggregateRuntimeClosure` failure naming the
missing release-bound port set. No production edit may precede that observed RED.

GREEN must use the final Accepted S8R5 release fixture and the real release-bound factory. It shall
execute a seven-lane plan, record all seven successful lane traces, exercise the injected fusion,
late-rerank, sufficiency, and supplemental ports, then execute a second content-bound handle replay
through the same public release-bound service to exercise handle resolution and accepted-identity
lookup. Before that validator fix, the exact real RED is `planner-owned plan has an unsupported
interaction mode`. The validator and owner must also reject empty or cross-session replay bindings;
GREEN must not capture or invoke the internal delegate. Detailed Web-only handle creation/tamper/
expiry/all-enumeration/all-budget semantics remain owned by the Accepted S8RG/S8S/S8RF tests and
are rerun in the aggregate matrix.

## Required checks

- S8R5 contract and receipt both report Accepted before any RED or production/test edit.
- Focused normal RED: exactly `1 xfailed`, zero failure/error/XPASS, at the S8C seam sentinel.
- Focused forced RED: exactly `1 failed`, caused only by
  `_MissingS8CAggregateRuntimeClosure` before fixture/effect acquisition.
- Focused GREEN with warnings as errors: exactly `1 passed`, no xfail/skip.
- The vertical result proves seven lane traces, release/evidence/candidate lineage, fusion before
  constraints/rerank, bounded Web snapshot admission, per-part sufficiency, targeted supplemental
  receipt/continuation, public release-bound read-only handle resolution, and zero writes. The
  Accepted S8RF owner remains the handle-creation/lifecycle evidence.
- Rerun the Accepted S8RG/S8RF/S8S owner files and the release-bound S8E1/L1-L3/V1-V2/IR1/R1-R5
  focused owners. Every selected node passes with no xfail/XPASS.
- The four public relationship direction owners and their authoritative-zero/insufficient-evidence
  cases pass; no unsupported direction is returned as a fact.
- Complete no-external Canonical V2 suite has zero failures. Intentional external skips remain
  explained and do not become S8C evidence.
- Ruff check/format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, scope, secret, generated-cache, package-content, and frozen-source checks pass.
- One lean implementation/test-integrity review reports zero open Critical/Important. Minor/YAGNI
  findings are recorded and non-blocking.

## Evidence to update

- This Slice Contract and `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8c/implementation-plan.md`.
- New `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8c/verification-receipt.json`.
- Existing `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`.
- OpenSpec `tasks.md`, `acceptance.md`, `change-log.md`, and `agent-links.md` only at acceptance.
- `.agents/portfolio.md`, the current code-grounded mainline/convergence status, and no Accepted
  predecessor slice.

## Stop conditions

- S8R5 lacks an Accepted contract or receipt, or any required predecessor regresses.
- Correct GREEN requires changing any `knowledge_read.py` behavior beyond the finite
  release-bound `handle_replay` validator branch, or requires a shared serialized shape, physical
  adapter, schema, migration, provider framework, or Accepted predecessor fixture change.
- A port can bypass release binding, author protected/accepted state, mutate canonical/source/index
  state, cross session boundaries, or turn a tampered/expired/unresolved handle into a canonical
  referent.
- Any lane loses complete traceability, concurrency is bypassed, constraints move before fusion,
  rerank can invent identities/evidence, or supplemental execution loses budgets/initial evidence.
- A relationship requires inference outside the four accepted public directions, or an
  insufficient-evidence direction would need a fabricated edge to pass.
- Task 8.1/8.8, S2C, S9+, live provider thresholds, or unresolved Critical/Important findings enter
  the scope.

## Done means

- S8R5 is Accepted; reviewed S8C hashes move Specified to Ready; exact RED and minimal GREEN are
  recorded through one release-bound vertical owner.
- The existing factory forwards all seven optional ports; the public release-bound service admits
  the already-Accepted lane-free handle replay without changing replay output or physical-adapter
  behavior; the complete required matrix passes.
- No online write or external-state change occurs; one lean review has zero open Critical/Important.
- S8C is Accepted and Tasks 8.3, 8.5, and 8.7 are checked together, moving the ledger exactly to
  `59/80`; Tasks 8.1 and 8.8 remain open for S2C/calibrated aggregate acceptance.

## Rollback note

Remove the S8C test owner, revert the optional parameters/imports/pass-through arguments in
`knowledge_read_isolated.py`, and remove the finite planner-owned `handle_replay` validator branch
from `knowledge_read.py`; then restore the pre-S8C evidence/status entries and uncheck Tasks
8.3/8.5/8.7 if acceptance evidence is rolled back. No database, index, source, provider, release
pointer, or external state requires rollback.
