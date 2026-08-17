# Slice Contract: S8E1 Release-bound KnowledgeRead Composition

## Status

Accepted at `2026-07-19T08:08:07Z`. Exact RED/GREEN, review-driven contract hardening, complete
proportional verification, package/source parity, frozen-target checks, and independent final review
are complete. Final review reports zero Critical/Important/Minor/YAGNI and verdict `Accept`. S2C3C2
gates reviewed calibration and later claim-level acceptance-oracle execution only; it did not block
this deterministic release-bound Task 8.3 predecessor. Task 8.3 remains open and the formal ledger
remains `56/80`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.3` (release-bound execution-composition predecessor only; remains unchecked)
- Depends on: Accepted aggregate S7/S7I, S8RG synthetic mechanics, S8L1 physical exact lookup,
  S8L2 physical displayed-set structured lookup, and S8P1/S8P2 release-bound planning
- Implementation plan:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8e1/implementation-plan.md`

## Goal

Add one package-internal release-bound composition root:

```python
create_isolated_release_knowledge_read(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
    universal_web_policy: WebSearchPolicy,
    web_search: Callable[[LaneRequest], object],
    web_snapshot_policy: WebSnapshotPolicy,
    clock: Callable[[], datetime] = ...,
) -> KnowledgeRead
```

The factory shall hide construction of the existing physical exact and structured adapters and the
existing `KnowledgeRead` execution mechanics. Its returned service shall exact-revalidate every
`RetrievalPlan` and require a `PlanningReleaseBinding` whose execution-relevant release identity—
release, serviceable publication state, publication hash/evidence, manifest hash, and index-result
hash—matches the bound
`IsolatedReleaseBundle` and `PublishedRelease` before any physical lookup or Web call. This Slice
supports only exact, structured, and Web execution lanes; any other configured lane fails before
effects instead of degrading as a provider failure.

The factory does not own the index request, candidate/internal projection graph, institution catalog,
or planning policy, so it does not independently recompute those four planner-bound hashes. Their
typed/content-bound values remain preserved on the exact-revalidated plan and continue to be owned by
the Accepted S8P1 planner boundary.

The caller supplies only the true current-Web port, bounded Universal-Web policy, snapshot policy,
and clock. It must not supply an arbitrary local `lane_adapters` mapping. Existing
`KnowledgeRead.execute(RetrievalPlan) -> EvidenceSet` remains the sole execution interface.

## Non-goals

- No lexical, vector, relationship, internal Person/Technology, supplemental, handle-resolution,
  identity-fuser, reranker, sufficiency-decider, or real network/provider adapter in this Slice.
- No full Task 8.3/8.5/8.7 or aggregate S8 acceptance, reviewed S2C replay, calibration, threshold,
  latency, cost, or production-runtime claim.
- No query-planner behavior change, public API promotion, second execution service, generic adapter
  registry, arbitrary lane map, persistence, migration, database/index/source write, pointer change,
  Commit, Push, PR, Archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for the package-
  internal factory, release-bound wrapper, and reuse of existing exact/structured validation.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  lazy physical vertical group using the existing S7 bundle fixture and public `execute` seam.
- This Slice Contract, its implementation plan, and S8E1-only evidence. After Candidate review,
  update existing verification/change-log/agent-links/portfolio/mainline-plan artifacts only.
- `tasks.md` and `acceptance.md` remain unchanged.

## Forbidden changes

- Any production file other than `knowledge_read_isolated.py`; any shared/public contract, S7
  builder/reader/publication behavior, accepted assertion, fixture source, original target, or
  active pointer.
- Exposing caller-owned local adapter mappings; silently accepting unsupported local lanes; treating
  missing release binding as legacy-compatible inside this release-bound factory; or checking only
  `plan.release_id` while ignoring publication/manifest/index binding.
- Performing physical lookup or Web invocation before release/binding/lane validation; swallowing a
  binding/configuration failure as `invalid_output`, timeout, or ordinary Web degradation.
- Test-local positive adapter, monkeypatched positive physical reader, copied lookup/index store,
  broad exception masking, xfail/skip weakening, live network/credentials, or source mutation.

## Expected unchanged behavior

- Existing ephemeral factory, S8L1 exact factory, S8L2 structured factory, planner identities,
  exact/structured candidate/evidence IDs, and all accepted KnowledgeRead owners remain unchanged.
- Initial RED is exactly one strict xfail and one forced exact missing-symbol sentinel before the
  expensive physical fixture is acquired. GREEN is one pass through the new factory without a
  caller local-lane map.
- Original PostgreSQL/Milvus/forensic sources, isolated bundle bytes, active pointers, and the
  `56/80` ledger remain unchanged.

## Required checks

- RED normal: exactly `1 xfailed`; forced `--runxfail`: exactly one direct
  `_MissingIsolatedReleaseKnowledgeReadFactory` failure before physical fixture acquisition.
- GREEN focused: exactly `1 passed`, proving exact plus structured physical execution and Universal
  Web invocation through one release-bound service, collision-free two-lane lineage for one
  Canonical identity, complete lane traces, and no caller local adapter map.
- The same group independently mutates publication state/hash/evidence, manifest hash, and index-
  result hash and proves cross-release/missing binding, every mismatch, unsupported lanes, and a
  non-serviceable publication fail before explicit physical-reader and Web spies observe any call.
- Universal-Web construction rejects non-Universal mode, zero provider-call/timeout/result bounds,
  and a scoped domain allowlist. A recorded current-Web item with content-addressed payload produces
  an accepted snapshot receipt; oversize and missing-payload variants are rejected through the exact
  supplied `WebSnapshotPolicy` while supported local evidence remains.
- Existing S8L1/S8L2/S8P1/S8P2 focused groups, complete shared physical owner, all KnowledgeRead
  owners, and complete no-external Canonical V2 pass with actual counts recorded.
- Scoped/complete Ruff and format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source/target
  checks pass.
- One independent review ends with zero open Critical/Important findings. Minor/YAGNI is recorded and
  nonblocking unless it proves a Spec/safety/model-valid bypass.

## Evidence to update

- This contract and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8e1/verification-receipt.json`.
- Existing `verification.md`, OpenSpec change-log/agent-links, portfolio, and mainline plan after
  acceptance. Do not change `tasks.md` or `acceptance.md`.

## Acceptance evidence

- Exact TDD: normal `1 xfailed, 49 deselected`; forced RED `1 failed, 49 deselected` at the direct
  `_MissingIsolatedReleaseKnowledgeReadFactory` sentinel; GREEN `1 passed, 49 deselected`.
- Predecessor-focused is `6 passed, 44 deselected`; the complete physical/release owner is
  `48 passed, 2 skipped`; all KnowledgeRead owners are `17 passed`; complete no-external Canonical V2
  is `337 passed, 141 skipped, 0 xfailed` with the three intentional hostile-model warnings.
- Complete Ruff, changed-file format/compile, complete Pyright (`0/0/0`), strict OpenSpec,
  `git diff --check`, offline wheel/source parity, scope/secret/cache, and frozen-target checks pass.
- The final independent review reports zero Critical/Important/Minor/YAGNI. The secret-free receipt
  is `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8e1/verification-receipt.json`.
- No task checkbox, acceptance criterion, provider/network, persistence, database/index/source,
  active pointer, Commit, Push, PR, Archive, promotion, or Cutover changed. S8L3 release-scoped
  lexical lookup is the next smallest real-lane Slice.

## Stop conditions

- Correct release binding cannot be proven without changing an Accepted S7/S8 public contract or
  adding speculative product semantics.
- The factory must expose arbitrary local adapters, silently runs an unsupported lane, or cannot
  fail before physical/Web calls on binding mismatch.
- Existing exact/structured identity compatibility regresses, an external target changes, or a
  Critical/Important finding remains.

## Done means

- One exact RED becomes one release-bound vertical GREEN through the existing public `execute` seam;
  all Required checks and independent review pass with zero open Critical/Important findings.
- S8E1 is Accepted only as a Task 8.3 predecessor. Task 8.3 and aggregate S8 remain open, the formal
  ledger stays `56/80`, and the next smallest real-lane Slice is named.

## Rollback note

Remove the release-bound wrapper/factory, the single S8E1 test group, and S8E1-only evidence. S8L1,
S8L2, the ephemeral mechanics, physical bundle, external state, and task ledger need no rollback.
