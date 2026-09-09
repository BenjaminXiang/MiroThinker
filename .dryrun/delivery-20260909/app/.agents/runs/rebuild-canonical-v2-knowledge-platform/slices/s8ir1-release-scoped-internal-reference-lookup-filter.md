# Slice Contract: S8IR1 Release-scoped Internal-reference Lookup/filter

## Status

Accepted at `2026-07-19T16:07:14Z`. Exact RED/GREEN, predecessor/owner/full no-external tests,
static/package/frozen-target gates, receipt-first owned-output cleanup, and synchronized evidence
are complete. The sole Important no-match Person finding is closed and targeted re-review reports
`0 Critical / 0 Important / 0 Minor / 0 YAGNI`. S8V2 and every consumed S7/S8 predecessor remain
Accepted.
S2C3C2 gates reviewed calibration and claim-level acceptance-oracle execution only; it does not
block this deterministic Task 8.3 predecessor. The formal ledger remains `56/80`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Requirements:
  `specs/evidence-first-query-orchestration/spec.md` — bounded internal Person retrieval and
  release-resolved Technology aliases/routes
- OpenSpec task: `8.3` (internal-reference lane predecessor only; remains unchecked)
- Depends on: Accepted S6R Person/Technology projections, S7 internal auxiliary lookup documents,
  S8P1 release-bound internal-reference queries, S8P2 planning contract, and S8E1 release-bound
  composition
- Implementation plan:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8ir1/implementation-plan.md`

## Goal

Carry the already-typed `RetrievalPlan.internal_reference_queries` only into the
`internal_reference` `LaneRequest`, omitting the field from every other request and from serialized
identity when empty. The S8IR1 physical scenario shall derive the Accepted S8P1 proposal but freeze
its executable lanes to exactly `("internal_reference", "web")`, with no relationship path. The
recorded Technology query still retains `relationship_evidence_required=True` and its state
semantics as unsatisfied plan trace; neither is executable relationship authority in this Slice.

A real isolated internal-reference adapter shall receive the optional factory pair
`index_projection_request: IndexProjectionRequest | None` and
`release_institution_catalog: InstitutionCatalog | None`. The factory shall require both or neither,
and install the lane only when both are present. Before any physical effect, it shall replay the
same accepted S7 candidate/internal-reference results used by S8P1 and compare the exact
`PlanningReleaseBinding` index-request, candidate-result, internal-result, and institution-catalog
hashes, in addition to the existing publication/manifest/index-result checks. It shall then audit
the exact physical internal lookup documents and execute only the recorded queries.

For a Person query, the adapter shall recheck the recorded typed education/Company-role/geography
filters against replay-derived `PersonReferenceRecord` values. It shall admit only listed resolved
eligible Person IDs, reject cross-wired eligible/excluded/content-hash/origin evidence, and emit
bounded raw candidates anchored to the resolved Person projection's originating public Professor,
Company, Paper, or Patent references that are also within the plan's public domains. Each candidate
shall retain the internal Person identity plus exact public anchor evidence, while its displayed
domain/canonical object remains that public origin; no public `person` domain or independently
promoted Person handle may be created. Recorded unresolved and nonmatching Person references remain
in the plan trace and produce no eligible candidate or traversal authority.

Candidate expansion is deterministic for both internal reference types: group accepted anchors by
`(reference_type, internal_reference_id, public_domain, root_canonical_identity_id)`, emit exactly
one raw candidate per group, emit one evidence item per distinct anchor ordered by `anchor_id`, sort
groups by that four-tuple, and only then truncate to `LaneRequest.max_candidates`. Multiple anchors
to the same public object are retained in that candidate; Person and Technology matches to the same
public object remain separate raw candidates and may be merged only by the existing public canonical
fusion key. `RecallCandidate.origin_public_evidence_ids` is exactly the group's sorted anchor IDs;
the internal `LookupProjectionDocument.source_evidence_ids` remains separate document lineage and
must never substitute for those public-origin IDs. `domain` and `canonical_id` come from the replayed
anchor. `display_name` comes only from
the unique replayed public projection for that anchor — `CompanyProjection.name`,
`ProfessorProjection.name`, `PaperProjection.title`, or `PatentProjection.title` — whose domain,
canonical ID, release, and `content_sha256` exactly equal the anchor's root authority. Fused output
and `CanonicalEntityHandle` must preserve that same public identity and display name.

For a Technology-route query, release-owned authority shall recheck canonical route ID, selected
alias, exact definition, `technology.definition` field-lineage evidence, route-record hash,
projection hash, release/as-of, and Technology anchor/root-projection identity against the replayed
`TechnologyRouteRecord`, `TechnologyRouteProjection`, and `TechnologyEvidenceAnchor` values.
Request-owned `scope`, `enumeration_policy`, and their `as_of` shall instead be copied unchanged into
the internal `LaneRequest` identity and checked against the recorded query; they are not fields of a
route record/projection. A Technology evidence claim is exactly
`subject_id=<canonical_route_id>`, `predicate="definition"`, and
`value=<TechnologyRouteProjection.definition>`, bound to the projection's
`technology.definition` lineage. Its separate public Company/Paper/Patent anchor is only an origin
locator and does not prove the definition, discussion, adoption, use, Product capability, or a
relationship. This Slice does not return or infer any such relationship/traversal result; those
still require the relationship lane and a separately Accepted relationship-publication authority
correction.

Internal-reference evidence shall use a distinct discriminated
`LocalInternalReferenceTrace(path="internal_reference_lookup")`. Its content-addressed identity
binds target/marker/manifest/index-result; internal lookup document/projection/reference type;
internal reference ID, projection hash, and replay-derived record hash; release; public origin
domain/object, anchor ID/content hash, and root-projection hash; exact LaneRequest content hash;
claim subject/predicate/value and definition/filter evidence IDs; raw candidate; and evidence
identity. Person claims use the internal Person ID with predicate `internal_person_filter_match` and
value equal to the exact `PersonProjection.content_sha256`; Technology claims use the definition
shape above. Public origin lineage remains a separate locator in both cases. Core validation shall
branch explicitly for this trace rather than weaken the public exact/vector invariants. The existing
release-bound post-delegate authority seam shall reject unknown/cross-release internal documents,
query/result cross-wires, unresolved Person admission, public-origin mismatch, altered
trace/content/evidence, and forged fused/auxiliary output without reopening physical storage.

The Person trace shall additionally retain the exact ordered `InternalReferenceQuery.typed_filters`;
the Technology trace retains an empty filter tuple. Existing geography constraint evaluation may
read a `geography` value only from those content-bound Person trace filters when the item's exact
claim is `internal_person_filter_match`. The trace is already bound to the LaneRequest and replayed
Person query/projection, so this is narrow compatibility for the existing protected-slot invariant,
not a second inference path. No other constraint kind or arbitrary auxiliary evidence is promoted.

The S8E1 factory shall install `internal_reference` only when its exact replay authority inputs are
provided as one validated pair; existing factory calls and supported-lane behavior remain unchanged
when they are absent.

## Non-goals

- No relationship adapter, relationship-state/adoption/use result, typed traversal, relationship
  publication payload, or Task 8.5 fusion/rerank policy.
- No query classifier, heuristic filter/alias inference, prompt/provider call, threshold,
  calibration, supplemental retrieval, or new public domain.
- No unresolved Person candidate, accepted identity creation, query-time write, canonical mutation,
  Product-capability propagation, or Industry Brief synthesis.
- No Technology-concept comparison beyond validating a selected route's existing typed definition;
  no claim that definition-only recall satisfies relationship evidence.
- No S7 projection/index/schema/content change, migration, relationship persistence, Universal-Web
  behavior, answer/session behavior, Task 8.3 completion, aggregate S8 acceptance, Commit, Push, PR,
  Archive, promotion, or Cutover.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` for an omission-preserving
  lane-specific internal-query request field, one typed internal auxiliary trace, exact output
  validation, and narrow trace-bound Person geography constraint compatibility only.
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for replay authority,
  the real physical internal-reference adapter, optional composition installation, and release-
  authority post-validation.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  exact physical vertical group and unchanged predecessor assertions.
- This contract/plan and S8IR1-only evidence. Existing verification/change-log/agent-links/
  portfolio/mainline-plan artifacts may be synchronized only after Candidate review. Keep
  `tasks.md` and `acceptance.md` unchanged.

## Forbidden changes

- Caller-owned lane map, a second read service, arbitrary internal query dictionaries, inference
  from query text, use of unresolved references as identities, or treatment of internal IDs as a
  fifth public population.
- Fabricating a public origin from an internal ID, returning a public object outside plan domains,
  trusting bundle-only documents without physical audit, or accepting a query/trace whose replayed
  content/evidence/release identity differs.
- Returning Technology relationship state from definitions/mentions, promoting discussion to
  adoption/use, or introducing `product_has_capability`.
- Any index/projection/publication, relationship, answer/gap, provider, migration, admin/chat,
  original source/target, pointer, or other test file.
- Xfail/skip weakening, credentials/network, broad formatting, or destructive worktree cleanup.

## Expected unchanged behavior

- Proposal, RetrievalPlan, every non-internal LaneRequest, public local/vector traces, and exact/
  structured/lexical/vector/Web payloads remain byte/value identical when the new request field is
  empty. The Accepted S8V2 literal LaneRequest JSON/SHA baseline remains exact.
- Existing synthetic unbound `internal_reference` adapters may continue to receive an empty query
  tuple; the real isolated adapter rejects missing authority before physical effects.
- Existing S8P1 plan and query identities do not change. S8IR1 uses an explicitly named derivative
  proposal only to remove the unavailable relationship lane/path; it copies the same already-
  recorded Person/Technology query values and performs no new filter, alias, or relationship
  planning.
- Public fusion keys remain public canonical object IDs. Internal Person/Technology identities are
  visible only through typed auxiliary trace/evidence lineage and never become public handles.
- Original PostgreSQL/Milvus/forensic sources, accepted target bytes, active pointers, Task 8.3,
  `tasks.md`, `acceptance.md`, and formal `56/80` remain unchanged.

## Required checks

- Pre-production S8V2 literal legacy LaneRequest payload/hash passes unchanged.
- RED normal: exactly one strict xfail. Forced `--runxfail`: exactly one direct
  `_MissingIsolatedInternalReferenceLookupAdapter` before physical fixture acquisition. The resolver
  checks both the factory and required LaneRequest/trace contract fields.
- GREEN focused: exactly one pass through real release-bound planner and `KnowledgeRead.execute`.
  One combined recorded request exercises SUSTech education + Shenzhen founder Person filters and
  the accepted `vision servo` route alias. Its proposal lanes are exactly `internal_reference` and
  `web`, with no relationship path; the captured internal lane request exactly preserves the two
  typed queries, including unsatisfied relationship trace state. Web remains independent; no test-
  supplied positive internal adapter is used.
- The Person result proves exact eligible/filter/content-hash/origin replay, resolved-only public-
  origin candidates, no candidate for unresolved/nonmatching records, no public Person domain, and
  auxiliary traces with `public_population=false`. It also proves per-public-object anchor
  aggregation, four-tuple ordering/bounding, replay-owned display identity, and that the existing
  protected Shenzhen slot is satisfied only by the trace-bound recorded geography filter. The Technology
  result proves alias/route/definition/field-lineage/content-hash/release-as-of replay, exact request-
  owned scope/enumeration identity, and the frozen definition-only claim plus a separate public-
  origin locator with no relationship state or adoption/use claim.
- Direct adapter negatives reject empty/stray/cross-release queries, unsupported reference types,
  duplicate eligible/excluded IDs, changed typed filters/record hashes/evidence, unresolved Person
  admission, changed route alias/hash/definition evidence/scope/as-of, and zero public origin before
  physical lookup or before returning candidates as applicable.
- Physical/release-authority negatives reject missing/duplicate/cross-release/wrong-scope/wrong-
  reference/wrong-projection/content/source-hash lookup authority, altered internal trace/document/
  public origin, and a model-valid hostile adapter result whose fused or auxiliary output is
  cross-wired. They also reject one-of-two optional factory inputs, any mismatch in the binding's
  index-request/candidate-result/internal-result/catalog hashes, forged public display identity,
  forged root-projection hash, and treating a Technology anchor as definition/relationship support.
  No post-delegate physical reopen is allowed.
- Existing S8P1/S8P2/S8E1/S8L3/S8V1/S8V2 predecessors, complete physical/release owner, all
  KnowledgeRead/query-planning owners, and complete no-external Canonical V2 pass with actual counts
  recorded.
- Complete Ruff/format, changed-file compile, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, locked offline wheel/source parity, scope/secret/cache, and frozen-source/
  target checks pass.
- One independent review ends with zero open Critical/Important. Minor/YAGNI is recorded and does
  not block unless it proves a Spec/safety/model-valid bypass.

## Evidence to update

- This contract and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8ir1/verification-receipt.json`.
- Existing verification/change-log/agent-links/portfolio/mainline plan after acceptance. Do not
  change `tasks.md` or `acceptance.md`.

## Stop conditions

- Person/Technology definition recall cannot be grounded in exact replayed authority plus the
  audited internal lookup projection, or requires exposing an internal identity as a public domain.
- Technology route definition recall requires inventing relationship/adoption/use semantics or a
  relationship publication payload; defer that portion rather than broadening S8IR1.
- The local auxiliary trace requires changing S7 projection/index content, legacy absent-field
  identities cannot remain stable, an existing owner regresses, or a Critical/Important finding
  remains.

## Done means

- One exact RED becomes a real release-bound internal Person filter plus Technology route-definition
  GREEN through the existing public `KnowledgeRead.execute` seam; required checks and independent
  review pass with zero open Critical/Important findings.
- S8IR1 is Accepted only as a Task 8.3 predecessor. Task 8.3 and aggregate S8 remain open, formal
  progress stays `56/80`, and the relationship-publication correction is named before any real
  relationship adapter.

## Rollback note

Remove the optional internal query request field, auxiliary trace/validation, isolated adapter,
optional factory authority inputs, the single S8IR1 group, and S8IR1-only evidence. S8P1/S8E1/
S8V1/S8V2, S7, external state, and the task ledger otherwise need no rollback.
