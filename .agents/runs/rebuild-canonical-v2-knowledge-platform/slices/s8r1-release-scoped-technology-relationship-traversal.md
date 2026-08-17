# Slice Contract: S8R1 Release-scoped Technology Relationship Traversal

## Status

Accepted at `2026-07-19T20:05:54Z`. S7K supplies the exact release-scoped relationship publication
pair, and S8P1/S8P2, S8E1, and S8IR1 remain Accepted. Initial independent contract review reported
`0 Critical / 2 Important`; initial feasibility review reported
`0 Critical / 2 Important / 3 Minor / 1 YAGNI`. The contract/plan now close Company raw-ID versus
stable-reference authority, scope/enumeration/as-of identity, model-valid eligibility coverage,
canonical freshness formatting, exact route-anchor/source-record selection, RED fixture order, and
the redundant S7K matrix. Both targeted re-reviews report
`0 Critical / 0 Important / 0 Minor / 0 YAGNI` and `Ready`. Strict OpenSpec validation exits `0`.
S2C3C2 gates reviewed calibration and claim-level acceptance-oracle execution only; it does not
block this deterministic Task 8.3 predecessor. The formal ledger remains `56/80`.

Exact RED/GREEN, the corrected 13-test predecessor matrix, complete physical/release and no-external
owners, static/package/frozen-target gates, independent review, receipt-first owned-output cleanup,
and acceptance evidence synchronization are complete. Final evidence is `345 passed / 141 skipped`
with three intentional hostile-model serializer warnings, Pyright
`0 errors / 0 warnings / 0 informations`, and targeted re-reviews at
`0 Critical / 0 Important / 0 Minor / 0 YAGNI`. S8R1 is Accepted only as a Task 8.3 predecessor;
Task 8.3 remains open and the formal ledger remains `56/80`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Requirements:
  `specs/evidence-first-query-orchestration/spec.md` — typed Technology alias/route relationship
  retrieval, exact relationship-state preservation, release traceability, and Product-capability
  non-propagation
- OpenSpec task: `8.3` (real relationship-lane predecessor only; remains unchecked)
- Depends on: Accepted S6R Technology/relationship projection, S7 candidate/index/publication,
  S7K relationship publication authority, S8P1/S8P2 release-bound planning, S8E1 composition, and
  S8IR1 internal route authority
- Implementation plan:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r1/implementation-plan.md`

## Goal

Execute the one currently frozen release-bound Technology relationship query family through the
existing public `KnowledgeRead.execute` seam:

```text
query relationship type: technology_company_relationship
direction:                technology_to_company
source type:              technology_route
target type:              company
```

The relationship lane shall map that query family only to the three already-registered current
canonical relationship types and their exact user-visible states:

```text
entity_discusses_or_mentions_technology -> discussion_or_mention
entity_claims_adoption_of_technology     -> claimed_adoption
entity_demonstrates_use_of_technology    -> demonstrated_use
```

Add omission-preserving `LaneRequest.relationship_paths` and
`LaneRequest.relationship_reference_queries`. `_lane_request` shall copy the plan's relationship
paths and only its `technology_route` internal-reference queries into those fields only for the
`relationship` lane. `internal_reference_queries` remains exclusive to the `internal_reference`
lane. Empty fields shall be omitted so the Accepted S8V2 literal LaneRequest JSON and SHA-256 remain
unchanged.

Add one discriminated `LocalRelationshipTrace(path="relationship_traversal")`. Core lane validation
shall require this trace only when relationship evidence carries it; it shall not globally require
a trace for every synthetic relationship candidate because the Accepted S8RF/S8RG recorded-adapter
seam remains a valid unbound predecessor. A traced relationship item/candidate shall bind one exact
request, current relationship, source assertion, Technology route/public anchor, Product source
subobject, parent Company, Company path-eligibility result, and release/publication identity.

The isolated factory shall install a relationship adapter only when both authorities are present:

1. the S7K `relationship_projection_request` / `relationship_projection_result` pair, including an
   authoritative zero-result pair; and
2. the existing exact `index_projection_request` / `release_institution_catalog` pair replayed by
   `_InternalReferenceAuthority`.

A legacy no-pair zero bundle is valid publication compatibility but is not relationship authority.
Missing either authority leaves the relationship lane unsupported and execution must fail before
Web, physical lookup, database, provider, or other effects. The adapter reads the validated bundle
and replayed projection graph in memory; it shall not open the relationship PostgreSQL store or add
another persistence/read model.

The S7K relationship request's complete internal-reference pair shall be replayed through
`compose_candidate_projections`. The resulting complete `CandidateProjectionResult` shall equal the
index authority's complete candidate result, not merely share seven manifest hashes. Relationship
request/result replay, combined-registry identity, release, run, schema, `as_of`, and content hashes
shall remain exact.

The adapter accepts exactly one frozen relationship path and exactly one Technology-route reference
query. The query shall require relationship evidence, preserve exactly the three states above,
permit no state promotion, name one accepted canonical route ID, and bind that route ID to its
recorded alias and release. Its request-owned `scope`, non-null timezone-aware `as_of`, and
`enumeration_policy` shall remain exact, with `scope == enumeration_policy.scope` and
`as_of == enumeration_policy.as_of`; missing or drifted values fail before delegate/Web effects.
The target endpoint of every returned current relationship shall match that route's exact canonical
stable reference. The relationship type/version shall exist in the replayed result registry and
declare `relationship_traversal` eligibility. Only an admitted candidate outcome with an accepted
typed decision and one exact current projection may be returned.

The current Product endpoint is the factual subject. For each relationship, the evidence chain is:

```text
CurrentRelationshipProjection.selected_evidence_refs
  -> RelationshipProjectionRequest.retained_assertions
  -> retained public SourceAssertion/source record
  -> exact TechnologyEvidenceAnchor selected by the route projection
  -> exact Product typed subobject
  -> exact parent Company public projection
```

The adapter shall derive `root_company_id` only from
`TechnologyEvidenceAnchor.root_canonical_identity_id`. That raw ID locates and validates the Product
`parent_canonical_identity_id`, Company projection, and path-eligibility pair. It shall then
independently require
`source_endpoint.parent_canonical_identity_ref == f"canonical:company:{root_company_id}"`; it shall
never parse or strip the endpoint reference to derive the raw ID. The Product source endpoint must
also equal the exact typed subobject stable reference. The route endpoint must equal the exact
accepted Technology route projection. The selected retained reference, assertion, source record,
Technology anchor, Product subobject, and Company projection must all agree.

The route anchor shall be selected only from the accepted route projection's exact
`source_anchor_ids`, then matched to its route `technology_source_identity_id`, Product subobject,
root Company, and source record. Product-only matching is forbidden because several Technology
concept/route anchors may share that Product. “Source record” in this Slice means identity equality,
not a new loaded `SourceRecord` object:

```text
retained.source_record_ref
  == source_assertion.source_record_id
  in technology_anchor.source_record_ids
```

`RelationshipCandidateOutcome.retained_assertion_id` remains the existing typed assertion input ID;
the `RetainedAssertionReference` is resolved only from the current relationship's
`selected_evidence_refs`.

For the parent Company, the adapter shall locate exactly one replayed
`verified_relationship_traversal` path decision in the index request's exact path-eligibility pair:

- `admitted`: return the Company candidate and copy any exact limitations into `quality_flags`;
- defensive typed `limited`: return it and copy the exact limitations into `quality_flags`, but do
  not claim that the complete Accepted S7 public graph can produce this outcome;
- path-specific `excluded`: return no candidate.

`DomainInclusionResult` forbids a `limited` inclusion outcome in the complete Accepted S7 public
graph. A path-specific quality signal remains `PolicyOutcome.admitted` with visible nonempty
limitations; S8R1 copies those limitations without reopening S7 eligibility semantics. The Accepted
S7/index authority also cannot publish this Company with a model-valid `review` inclusion outcome,
so S8R1 fabricates neither `limited` nor `review`. Defensive support for an independently
model-valid typed `limited` decision remains fail-safe compatibility; every other non-excluded,
non-returnable outcome fails closed.

This public-object eligibility does not replace the exact Product-to-Technology relationship proof;
the trace binds both authorities. S8R1 does not add Technology relationship IDs to the existing
path-result relationship-decision list and does not change S6/S7 eligibility semantics.

For each accepted current relationship, emit one raw candidate before the existing fusion step:

- `domain="company"` and `canonical_id=<parent Company ID>` locate the returned public object;
- `display_name` comes only from the exact replayed Company projection;
- `reference_type="technology_route"`;
- `relationship_state` is exactly one of the three recorded states;
- `origin_public_evidence_ids` is the exact sorted Technology anchor ID tuple;
- `EvidenceItem.object_id` is the parent Company ID;
- `EvidenceClaimBinding.subject_id` is the Product source endpoint stable reference;
- `predicate` is the exact canonical relationship type ID;
- `value` is the exact Technology target endpoint stable reference;
- `status` is the exact relationship state.

Company identity on the candidate/item is a result locator only. It must not promote a Product fact
into a direct Company adoption/capability claim, and no `product_has_capability` evidence or
canonical relation may appear. Deterministic ordering is by relationship state/type/ID and the
existing `max_candidates` bound is applied after ordering.

The relationship snapshot is authoritative at `relationship_projection_result.as_of`. The real-
planner/public-`execute` positive covers equal time. A query whose Technology reference `as_of` is
earlier than that snapshot fails closed. A later query may return only the snapshot evidence and
shall add the exact visible quality flag
`relationship_snapshot_as_of:<canonical-UTC-Z-timestamp>` while the trace binds both query and
snapshot `as_of`. For the frozen fixture the exact flag is
`relationship_snapshot_as_of:2026-07-13T17:00:00Z`. Earlier/later cases use the direct relationship
adapter or a fully revalidated wrapper-plan copy. They shall update the query `as_of` and its
enumeration-policy `as_of` coherently, plus plan-level `as_of` and plan enumeration `as_of` when
exercising the wrapper, while leaving the release snapshot and route hashes unchanged. The adapter
must not claim query-time currency or recompute temporal validity without an explicit comparison
context.

The relationship trace shall content-bind at least:

- target marker, manifest, index result, publication evidence, release, and LaneRequest hash;
- relationship request/result hashes, projection run/schema/registry identities, and snapshot/query
  `as_of`;
- query path/direction/source/target and selected canonical Technology route;
- current canonical relationship ID/hash, decision ID, exact type/version, endpoints, roles,
  selected evidence refs, valid-from/valid-to, and semantic state;
- retained reference, public assertion, and source-record identities;
- Technology route projection ID/hash, Technology anchor ID/hash, Product ID/hash, and parent Company
  ID/projection hash/display identity;
- Company path-result hash and its exact decision/policy/outcome/limitations/hard exclusions/
  supporting assertions;
- claim subject/predicate/value/status, snippet hash, candidate/evidence identities, and trace hash.

The release-bound wrapper shall validate the relationship request before delegate execution and
rebuild the expected relationship result from its in-memory authority after delegate execution. It
shall reject altered raw evidence, candidate traces, fused candidates, entity handles, auxiliary
traces, or cross-lane evidence without reopening physical storage.

## Non-goals

- No generic public-to-public relationship traversal, Person-backed author/inventor/team-member
  traversal, reverse Company-to-Technology path, multiple routes, route comparison, or aggregate
  Task 8.3 completion. Later S8R slices own those families.
- No relationship database reader, schema, migration, relationship persistence, index point, build
  manifest, release-publication, candidate-projection, or path-policy change.
- No identity-aware fusion/reranker policy change, sufficiency/supplemental retrieval, Web-handle
  lifecycle change, answer/session/Industry-Brief behavior, reviewed corpus execution, provider, or
  live network.
- No public Product/Technology domain, Company-level adoption inference, canonical Product-
  capability relation, or Product-capability propagation.
- No Task checkbox, aggregate S8 acceptance, Commit, Push, PR, Archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` for the two omission-
  preserving relationship request fields, `LocalRelationshipTrace`, explicit traced relationship
  item/candidate validation, and locator handling.
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for relationship
  replay authority, the in-memory real adapter, optional composition installation, and release-
  bound pre/postvalidation.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  exact S8R1 vertical RED/GREEN group plus the smallest reusable relationship/path-eligibility
  fixture parameters.
- This contract/plan and S8R1-only receipt/evidence. Existing verification/change-log/agent-links/
  portfolio/mainline-plan artifacts may be synchronized only after Candidate review. Keep
  `tasks.md` and `acceptance.md` unchanged.

## Forbidden changes

- `relationship_projection.py`, `relationship_projection_postgres.py`,
  `internal_reference_projection.py`, `candidate_projection.py`, `index_projection*.py`,
  `release_publication*.py`, path-eligibility production code, catalogs, migrations, or unrelated
  tests.
- Query-text inference inside the relationship adapter; a second relationship result/store;
  trusting manifest counts without exact replay; endpoint-string parent inference; treating a
  Technology definition anchor alone as relationship proof; or accepting legacy no-pair zero as
  authority.
- Requiring Product capability, rewriting Product evidence as Company evidence, promoting mention to
  adoption/use, collapsing the three states, accepting an unregistered type/version/path, or
  returning excluded/review Company eligibility.
- Physical lookup, PostgreSQL, Milvus, Web, provider, or other effect before complete authority and
  request validation; post-delegate storage reopen; xfail/skip weakening; credentials/network;
  broad formatting; or destructive worktree cleanup.

## Expected unchanged behavior

- Existing `RetrievalPlan`, every non-relationship `LaneRequest`, S8V2 literal JSON/hash, public
  exact/vector/internal traces, synthetic trace-less S8RF/S8RG relationship adapters, and all
  existing lane output remain byte/value compatible when the new fields are empty.
- S8IR1 continues to carry `internal_reference_queries` only on its own lane. The relationship lane
  receives a separate Technology-only copy and cannot execute Person queries.
- Existing legacy no-pair bundles and authoritative-zero bundles remain distinguishable. Only the
  latter installs the relationship lane and returns an empty successful result.
- No physical relationship store is opened. Original PostgreSQL/Milvus/forensic sources, accepted
  candidate bytes, active pointers, Task 8.3, `tasks.md`, `acceptance.md`, and formal `56/80` remain
  unchanged.

## Required checks

- Pre-production S8V2 literal legacy LaneRequest payload/hash passes unchanged.
- RED normal: exactly one strict xfail. Forced `--runxfail`: exactly one direct
  `_MissingIsolatedRelationshipLookupAdapter` failure before fixture/target acquisition or external
  effect. The resolver checks the public factory symbol, both LaneRequest fields, and
  `LocalRelationshipTrace`.
- GREEN focused: exactly one pass through the real S8P1 release-bound planner and the existing public
  `KnowledgeRead.execute` seam. The plan executes exactly `relationship + web`, carries one frozen
  Technology path and one Technology reference query, uses one real S7K three-current-relationship
  bundle, and supplies no test-owned positive relationship adapter.
- The positive result proves the exact three type/state mappings; Product claim subject and route
  target; Company candidate/object/display/root anchor; exact Company eligibility; deterministic
  ordering/bounding; release/manifest/publication/relationship/index trace identity; successful Web
  independence; no Company-adoption rewrite; and zero Product-capability relation or claim.
- An authoritative-zero pair installs the lane and returns an empty successful relationship result.
  A legacy no-pair zero bundle or absent index authority leaves the lane unsupported and fails before
  Web/physical/provider effects.
- The focused matrix rejects before return or before effects as applicable: empty/duplicate/wrong
  path; Person or extra reference query; unknown route/alias/state; state promotion; missing/drifted
  scope or enumeration identity; coherent query-only scope/`as_of`/enumeration drift from its plan;
  coherently earlier query `as_of`; cross-release request/result; one representative relationship
  replay/result mismatch; unregistered type/version/path;
  missing/ambiguous current/outcome/decision/selected evidence; endpoint/role/selected-ref/validity/
  state drift; source assertion/record cross-wire; route-anchor selection outside
  `source_anchor_ids`; Technology route/anchor, Product subobject, raw Company ID versus parent
  stable-reference cross-wire; or complete candidate-result cross-wire. S7K's already-Accepted
  exhaustive publication-envelope corruption matrix is not duplicated here.
- The focused matrix proves `PolicyOutcome.admitted` Company eligibility with visible nonempty
  limitations copies those exact limitations, path-specific excluded eligibility returns no
  candidate, equal snapshot time has no freshness flag, and a coherently later query time returns
  only snapshot evidence with the exact frozen-fixture flag
  `relationship_snapshot_as_of:2026-07-13T17:00:00Z`.
- Model-valid hostile delegate outputs are reconstructed through `model_validate` with every derived
  trace/candidate/evidence hash recomputed. Altered relationship evidence/trace, candidate state/
  anchor, fused identity/display/evidence, fused identity-kind/resolution drift, extra fused
  ownership without an expected raw ID, extra canonical/Web handle ownership, auxiliary relationship
  state, or an added Product-capability claim is rejected by the release wrapper without a physical
  reopen.
- Existing S7K, S8P1/S8P2/S8E1/S8L1-L3/S8V1-V2/S8IR1 focused predecessors, complete physical/release
  owner, all KnowledgeRead/query-planning owners, the S6 relationship owner, and complete no-external
  Canonical V2 pass with actual counts recorded.
- Complete Ruff/format, changed-file compile, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source/
  target checks pass.
- One independent implementation review ends with zero open Critical/Important. Minor/YAGNI is
  recorded and does not block unless it proves a Spec, safety, or current model-valid bypass.

## Evidence to update

- This contract and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r1/verification-receipt.json`.
- Existing `verification.md`, OpenSpec change-log/agent-links, portfolio, and mainline plan only
  after acceptance. Do not change `tasks.md` or `acceptance.md`.

## Stop conditions

- Exact Product-to-Technology evidence cannot be reconstructed from the S7K pair and existing
  Candidate/Technology anchors without changing S6/S7 semantics, persistence, schema, path policy,
  or public domains.
- Correct Company admission cannot be proven from the existing index request; the Slice would need
  a new eligibility decision contract or an unavailable external source.
- Request/authority validation cannot precede every external effect, a post-delegate check would
  require reopening storage, an existing owner regresses, original/production-like state changes,
  or a Critical/Important finding remains open.

## Done means

- One exact RED becomes one real release-bound Technology-to-Company relationship GREEN through the
  existing public execution seam; all Required checks and one independent implementation review pass
  with zero open Critical/Important findings.
- S8R1 is Accepted only as a Task 8.3 predecessor. Task 8.3 and aggregate S8 remain open, the formal
  ledger stays `56/80`, and the next real relationship family is selected by a fresh dependency audit.

## Rollback note

Remove the two relationship LaneRequest fields, relationship trace/validation, isolated authority/
adapter/composition wiring, the single S8R1 test group, and S8R1-only evidence. No schema, stored
relationship, index point, release pointer, task checkbox, or external target requires rollback.
