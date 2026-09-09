# Slice Contract: s8l2-release-scoped-displayed-set-structured-lookup-green

## Status

Accepted at `2026-07-16T06:17:22Z`. Exact RED returned `1 xfailed`; forced `--runxfail` returned one
direct `_MissingIsolatedStructuredLookupAdapter` failure before lazy physical fixture acquisition.
GREEN is `1 passed`; the complete shared owner is `44 passed, 2 skipped`, all 16 KnowledgeRead
owners pass, and complete no-external Canonical V2 is `332 passed, 141 skipped, 0 xfailed` with the
three existing hostile-model serialization warnings. Static, strict, package/source-parity, scope,
secret/cache, and frozen-target gates pass.

The independent merged review found two Important test-integrity gaps in legacy exact evidence/
serialization compatibility and the service-level cross-lane trust seam. Both were repaired in the
single allowed test file; one mechanical format-gate failure was then reproduced and formatted.
Final targeted re-review reports zero Critical/Important/Minor/YAGNI. Accepted S8L1 remains
unchanged. This successor adds only one structured displayed-set consumer; Task 8.3, Task 8.5,
aggregate S8, and the formal ledger remain unchecked at 55/80.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `8.3` (real structured-lane predecessor only; remains unchecked)
- Optional downstream evidence for Task 8.5: exact and structured candidates for one Canonical object
  can fuse without ID collision, but this Slice does not accept fusion/rerank as a task
- Depends on: Accepted S7/S7I physical lookup and eligibility lineage, Accepted S8RG synthetic read/
  fusion mechanics, and Accepted S8L1 release-bound exact adapter/trust boundary
- Independent-start authority: uses only the same marked `IsolatedReleaseBundle`, serviceable
  `PublishedRelease`, and read-only lookup projection; no S2C oracle or calibrated threshold

## Goal

Add one package-internal factory:

```python
create_isolated_structured_lookup_adapter(
    *,
    release_bundle: IsolatedReleaseBundle,
    published_release: PublishedRelease,
) -> Callable[[LaneRequest], RetrievalLaneResult]
```

The adapter shall accept only `lane="structured"` and a non-empty exact
`StructuredConstraints.displayed_entity_ids` set, real-read and snapshot-compare the bound bundle,
and return only the requested Canonical members that also belong to the request's public domains.
Unknown, internal auxiliary, and cross-domain IDs return no candidate. An empty displayed set returns
empty before physical lookup rather than becoming a wildcard. A protected `displayed_entity_set`
slot, when present, must equal the structured displayed set or fail before read.

Reuse S8L1 typed projection, excluded-term, service-state, release, bundle, internal-boundary,
eligibility, and evidence mapping. Add an execution-lane discriminator to `LocalProjectionTrace` so
the physical path remains `exact_lookup` while exact versus structured candidate/evidence identities
cannot collide. Preserve legacy exact candidate/evidence IDs and exact trace-hash compatibility by
treating the default exact discriminator as the previously implicit value; structured identity/hash
must include its explicit lane. `KnowledgeRead` must cross-bind item/candidate lane to the trace.

## Non-goals

- No geography, institution, year, arbitrary field predicate, or general filter DSL; no lexical,
  vector, relationship, internal Person/Technology, Web, provider, rerank, or supplemental adapter.
- No full Task 8.3/8.5 or aggregate S8 acceptance, real threshold/latency/cost claim, reviewed S2C
  replay, Task 8.2 catalog binding, answer/session/consumer wiring, persistence, migration, or write.
- No second public `KnowledgeRead` service, generic repository, new public domain, cache, Commit,
  Push, PR, archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for the structured
  factory and reuse/generalization of the S8L1 package-internal validation/mapping helpers.
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` only to add the defaulted
  execution-lane discriminator and cross-bind it while preserving exact identity compatibility.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  lazy S8L2 vertical group reusing the existing physical fixture and all existing assertions.
- This contract/plan and, after Candidate review, the normal evidence/status files. `tasks.md` and
  `acceptance.md` remain unchanged.

## Forbidden changes

- Any other production/shared-contract/S7 builder-reader/publication/provider/migration/admin/chat/
  answer file, Accepted assertion value, original target, active pointer, or external source.
- Treating an empty displayed set as all objects; matching free text as a structured filter;
  returning an internal auxiliary or wrong-domain ID; ignoring protected-set disagreement; reusing
  one raw/evidence ID across exact and structured lanes; weakening S8L1 bundle/typed checks.
- Test-local adapter, monkeypatched positive reader, copied lookup database, new physical build,
  xfail/skip masking, broad exception fallback, network/credential use, or unsupported filter rules.

## Expected unchanged behavior

- S8L1 exact behavior, raw candidate/evidence IDs, accepted typed trace semantics, physical fixture,
  and all 16 KnowledgeRead owners remain GREEN. The trace gains a defaulted implicit-exact field but
  accepts the prior exact hash/identity representation.
- Before GREEN the new group is one strict xfail and one forced missing-symbol sentinel before lazy
  fixture acquisition. After GREEN it is one pass; the shared file becomes `44 passed, 2 skipped`
  and complete no-external Canonical V2 becomes `332 passed, 141 skipped, 0 xfailed` absent
  concurrent work.
- Original PostgreSQL/Milvus/forensic sources, release/index pointers, and formal 55/80 ledger remain
  unchanged.

## Required checks

- RED normal: exactly `1 xfailed`; forced `--runxfail`: exactly one
  `_MissingIsolatedStructuredLookupAdapter` failure before the physical fixture is acquired.
- GREEN focused: exactly `1 passed`, proving non-name displayed-set lookup, two public members,
  unknown/internal/cross-domain exclusion, empty-set no-read, protected-set mismatch fail-before-read,
  candidate bound, full-content excluded term, active/rolled-back service, cross-release/snapshot/
  unmarked refusal, lane-bound trace IDs, and exact+structured one-identity fusion without collision.
- Original S8L1 focused remains `1 passed`; complete shared file is `44 passed, 2 skipped`; the 16
  KnowledgeRead owners pass; complete no-external result is expected `332 passed, 141 skipped,
  0 xfailed` with actual counts recorded.
- Scoped/complete Ruff, format, `py_compile`, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source checks
  pass.
- One merged independent review ends with zero open Critical/Important. Minor/YAGNI is recorded and
  nonblocking.

## Evidence to update

- This Slice Contract and `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8l2/` receipt.
- Existing `verification.md`, OpenSpec change-log/agent-links, portfolio, and mainline plan after
  review. Do not change `tasks.md` or `acceptance.md`.

## Stop conditions

- Correct behavior requires new filter/product semantics, another physical index, S7 contract/
  schema/public method changes, provider truth, or original/production-like state.
- Exact IDs cannot remain stable while structured identities are collision-free; protected-set or
  bundle/typed/release checks cannot fail closed; any Accepted owner regresses; or a Critical/
  Important finding remains.

## Done means

- One exact RED becomes one real physical structured GREEN through the existing `KnowledgeRead`
  composition, with exact/structured trace separation and all Required checks/review passing.
- S8L2 is Accepted only as a Task 8.3 predecessor. Tasks 8.3/8.5 and aggregate S8 stay open; the
  ledger remains 55/80.

## Rollback note

Remove the structured factory/group and execution-lane generalization, then remove only S8L2
evidence. The shared physical target, S8L1 exact adapter, external state, and task ledger need no
rollback.
