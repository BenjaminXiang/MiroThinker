# Slice Contract: S8R2 Release-scoped Displayed Company-to-Patent Traversal

## Status

Accepted at `2026-07-19T22:19:19Z` from Candidate contract SHA-256
`26a5cdae9a3c83ed74cff31d4738d46b834b08c892e83f061145c892e765dd86` and Candidate plan
SHA-256 `3ead28171477574740d6d09166505a9860c7e5aad607582793c5cbcd38652514`, themselves derived from
the reviewed Ready contract SHA-256
`bff5de56db2f367dfc950db54801231924d7a672fadff4a5dda0e62c3402f982` and Ready plan SHA-256
`49c9f3073aef6295b71853502065a5cf0d5562e85b2082cf67e16cd8f80ad9ed`. The public
Company-to-Patent applicant traversal, complete authority trace, valid-zero/request/temporal matrix,
constraint-aware result ownership, and hostile postvalidation are GREEN. Required tests, static
checks, strict OpenSpec, offline wheel/source parity, frozen-target checks, and cleanup passed.
Three final independent reviews report zero open Critical/Important; one nonblocking wording Minor
is recorded. S2C3C2 does not block this deterministic Task 8.3 predecessor. The
formal ledger remains `56/80`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Requirements: `specs/evidence-first-query-orchestration/spec.md` — structured validated
  relationship paths, applicant-to-Patent enumeration, bounded release-scoped relationship recall,
  and complete traceability
- Accepted derived contract: Task 6 catalog scenario `traversal_scenario.company_to_patent`
- OpenSpec task: `8.3` (one real relationship predecessor only; remains unchecked)
- Depends on: Accepted S6 relationship catalog/projection, S7 candidate/index/release authority,
  S7K generic relationship-pair authority, S8P2 planning, S8E1 composition, S8L2 displayed-set
  binding, and S8R1 relationship replay/postvalidation mechanics
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r2/dependency-audit.md`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r2/implementation-plan.md`

## Goal

Execute one public relationship family through the existing `KnowledgeRead.execute` interface:

```text
planner relationship type: company_has_patent
planner direction:         company_to_patent
planner source/target:     company -> patent
canonical relationship:   patent_has_applicant@canonical-v2-relationship-v1
canonical orientation:    patent -> accepted Company applicant
execution orientation:    reverse
```

The Slice shall not create a canonical `company_has_patent` edge. It shall select only accepted
current `patent_has_applicant` relationships whose exact target endpoint and `applicant` role equal
one exact displayed Company in the request, then return the exact source Patent public projection.
Applicant shall never be relabeled as owner, assignee, inventor, or general organization.

## Request contract

Existing structured constraints and the protected displayed set remain the sole source-Company
identity authority. `EnumerationPolicy` already owns scope, as-of, mode, universe, exhaustiveness,
and continuation, so add only one omission-preserving copy for this public relationship lane:

```python
class LaneRequest(_ContentModel):
    relationship_enumeration_policy: EnumerationPolicy | None = None
```

The field is valid only on `lane="relationship"` with exactly the four-axis S8R2 path. `_lane_request`
shall copy the plan's exact enumeration policy only for that path. It shall remain absent for no
path, an unsupported public path, every non-relationship lane, and the S8R1 Technology path. The
LaneRequest serializer shall remove it when `None`, preserving every legacy/S8R1 literal JSON and
SHA-256. The release wrapper shall require
`plan.as_of == plan.enumeration_policy.as_of == relationship_enumeration_policy.as_of` and exact
plan/policy equality before delegate/Web effects.

S8R2 accepts only exact `representative` enumeration with no finite-universe ID/source/IDs, eligible
or required members; `exhaustive` is false and `continuation_state == "available"`. Every other mode
or universe/member claim fails before effects. The final `EnumerationCoverage` remains exact
open-world representative coverage: `unknown_scope=True`, `exhaustive=False`,
`continuation_state="open_world"`, and `continuation_required=True`.

The positive public plan has `domains=("patent",)`, includes the independent `relationship` and
`web` lanes, has no internal-reference target/query, and carries one displayed Company only as
source authority. The returned Patent is the sole public result domain.

At the package-internal direct adapter seam, zero displayed IDs return zero candidates and one
release-unknown, internal, or non-Company ID returns zero; more than one ID fails. Any protected set,
when present, must be the one exact equal tuple. At public `KnowledgeRead.execute`, S8R2 requires
exactly one non-empty displayed Company ID and exactly one equal `displayed_entity_set` slot;
missing, duplicate, empty, multiple, known wrong-type, internal, cross-release, or mismatched source
authority fails before delegate/Web effects. One syntactically valid but release-unknown public ID
returns authoritative local zero without becoming a wildcard; the independently planned Web lane
may still run. Multiple paths, another path/direction/type, a relationship-reference query, missing
enumeration policy, or plan/policy/as-of drift fails before effects.

Valid zero results include an authoritative-zero pair, a valid Company with no matching accepted
applicant relation, an excluded relationship/endpoint, and `max_candidates == 0`. These remain
distinct from invalid source authority and legacy no-pair unsupported behavior.

## Release authority and evidence chain

S8R2 uses the existing `_RelationshipAuthority` and
`create_isolated_relationship_lookup_adapter`; it shall not add a second public factory or adapter
seam. The S8R2 positive bundle is a clean test-owned input to the Accepted generic S7K interface:

- one combined-registry relationship request/result pair;
- the same complete internal-reference graph and seven candidate manifests as the index/release;
- one accepted Company projection;
- one accepted Patent projection with one exact applicant subobject/assertion;
- one accepted current `patent_has_applicant` relationship and exact decision/evidence chain; and
- matching Company and Patent path-eligibility pairs.

For every returned relationship, replay and bind this complete chain rather than joining only the
current projection to retained evidence:

```text
RelationshipProjectionRequest.candidates
  -> exact RelationshipProjectionCandidate
  -> exact TypedRelationshipAssertionInput
  -> exact RelationshipCandidateOutcome
  -> exact typed/current RelationshipDecision
  -> CurrentRelationshipProjection
  -> selected RetainedAssertionReference
  -> exact public SourceAssertion/source-record identity
  -> exact Patent applicant typed subobject
  -> exact Company applicant public projection
  -> exact Patent public projection
  -> exact source and target verified_relationship_traversal decisions
```

The canonical relationship type/version must be installed, declare `company_to_patent` eligibility,
and carry source Patent, target Company, and `applicant=<Company stable reference>`. Candidate,
typed assertion, outcome, typed/current decision, selected assertions/evidence, role bindings,
release, run, schema, registry, and their canonical model hashes remain exact. The candidate's
assertion input must select that typed assertion, whose `source_record_ref` equals the retained
reference and public `SourceAssertion.source_record_id`. The applicant subobject must have the
Patent parent ID, exact Company ID, selected supporting assertion, and same source-record identity.
Organization/person applicants are not valid on this Company path.

Both public endpoints must have exact Accepted release projections and direction-bound eligibility
pairs for the same relationship decision. The Company pair has Company subject/projection,
`traversal_directions=("company_to_patent",)`, and the exact current relationship decision ID. The
Patent pair has Patent subject/projection, `traversal_directions=("patent_to_company",)`, and that
same decision ID. Each pair's `verified_relationship_traversal` decision must be `admitted`, or the
defensive model-valid `limited` outcome with visible limitations. Exact limitations from both
endpoints are sorted, deduplicated, and copied to candidate quality flags. `excluded` at either
endpoint emits no candidate; `review` or any other non-returnable outcome fails closed. The complete
Accepted S7 public graph does not fabricate `limited` inclusion to satisfy this branch.

## Result and trace contract

Add `LocalCanonicalRelationshipTrace(path="canonical_relationship_traversal")` to the discriminated
local trace union rather than making the Technology/Product/Company trace fields optional. Existing
S8R1 trace JSON/hashes remain exact. The new model has these exact semantic fields, plus derived raw
candidate, evidence, and content hashes:

- release envelope: `target_id`, marker/manifest/index hashes, publication evidence IDs,
  `release_id`, and `lane_request_content_sha256`;
- query identity: `relationship_enumeration_policy_sha256`, exact displayed tuple,
  `displayed_company_id`, protected-slot ID/hash, query as-of, and the four literal planner path
  axes;
- relationship authority: request/result hashes, run/schema/registry identity, snapshot as-of,
  canonical relationship ID/hash, type/version/orientation, endpoints, role bindings, selected
  evidence, observed/valid time, and exact current decision identity/hash/state;
- input replay: projection-candidate ID/hash, typed-assertion ID/hash/source-record ref,
  candidate-outcome ID/hash, and typed-decision ID/hash;
- retained evidence: retained-reference ID/hash, retained assertion/source-record IDs, public
  SourceAssertion ID/hash, and exact source-record identity equality;
- public endpoints: Company ID/stable ref/projection hash/display identity; Patent ID/stable ref/
  projection hash/display identity; applicant subobject ID/hash/Company binding/assertion IDs;
- direction-bound eligibility: separate Company and Patent path-result hashes, traversal directions,
  relationship decision IDs, decision/policy/outcome/limitations/exclusions/supporting assertions;
- observable candidate: exact Patent domain/ID/display, identity kind/resolution, reference type,
  origin evidence IDs, quality flags, score, and claim subject/predicate/value/status.

The derived ID namespaces are distinct from S8R1:
`local-canonical-relationship-candidate:sha256:...` and
`local-canonical-relationship-evidence:sha256:...`. Every tuple field is sorted/unique where order
is not semantic. The trace validator requires the exact query/canonical reverse-orientation mapping,
one applicant role, one displayed Company, one returned Patent, exact candidate→assertion→outcome→
decision→current continuity, exact two-direction eligibility, and no hard exclusions on a returned
candidate.

The displayed Company is a source-side constraint witness, not the returned identity. For this
trace variant only, `_apply_constraints` (or an equivalent private helper) shall use the validated
`displayed_company_id` only when evaluating `displayed_entity_set`. The returned Patent remains the
identity/claim subject for geography, identifier, domain, negation, and every other constraint.
All relationship traces fused into that Patent must agree on the same source witness and protected-
slot identity. An absent, forged, mixed, untraced, unrelated-lane, or Web candidate witness cannot
satisfy the displayed set; hostile tests cover every bypass.

Emit one raw candidate per accepted current relationship before existing fusion:

```text
domain/display locator: patent / exact Patent canonical ID and display name
claim subject:          canonical:patent:<Patent ID>
claim predicate:        patent_has_applicant
claim value:            canonical:company:<Company ID>
claim status:           accepted
relationship_state:    accepted
```

The exact S7 relationship-result order is content-bound and retained before the unchanged
`max_candidates` bound; S8R2 adds no new multi-Patent ordering policy. `max_candidates == 0` returns
zero. Core emits the required representative `EnumerationCoverage`; S8R2 asserts its open-world,
non-exhaustive values but does not claim finite-universe coverage. Tasks 8.7/8.8 own broader
coverage accounting and calibrated gates.

The relationship snapshot is authoritative at `relationship_projection_result.as_of`. An earlier
query fails closed. Equal time has no freshness flag. A later query retains the snapshot evidence
and adds the exact canonical UTC `relationship_snapshot_as_of:<timestamp>` flag. The trace binds
both times and never claims query-time currency.

The release wrapper validates the public relationship request before delegate/Web execution,
rebuilds the exact expected result from in-memory release authority after delegate execution, and
rejects missing/extra/altered relationship evidence, traces, candidates, fused Patent identity,
quality flags, or canonical/Web handle ownership. It shall not reopen physical storage.

## Non-goals

- No Patent-to-Company direction, Professor/Paper/Patent/Company Person traversal, Technology route
  expansion or comparison, other Patent relation, multiple displayed Companies, generic public
  path registry, or aggregate Task 8.3 completion.
- No applicant-as-owner/assignee interpretation, organization/person applicant on the Company path,
  Product capability, inferred edge, or online canonical mutation.
- No planner heuristic, direct free-text Company resolution, fusion/rerank/sufficiency/coverage
  algorithm change, Web-handle lifecycle, answer/session, reviewed corpus, provider, or live network.
- No schema, migration, relationship persistence/read model, index/build/release-publication logic,
  task checkbox, threshold, Commit, Push, PR, Archive, promotion, or Cutover change.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py` for the omission-preserving
  relationship enumeration policy, trace variant, source-side displayed constraint witness, and
  explicit validation.
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py` for path dispatch,
  in-memory Company-to-Patent replay, and release-bound pre/postvalidation.
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py` for one
  exact vertical RED/GREEN owner and the smallest clean applicant fixture extension.
- S8R2 contract/plan/receipt and acceptance evidence after Candidate review. Keep `tasks.md` and
  `acceptance.md` unchanged.

## Forbidden changes

- Any S6/S7/S8 Accepted production behavior outside the two read modules, any catalog/registry,
  persistence, public domain/schema, build/index/publication interface, or external source.
- A second relationship adapter factory, test-local positive adapter, untraced real relationship
  output, free-text relationship matching, or physical relationship read.
- Weakening S7K replay/manifests, S8L2 displayed-set equality, S8R1 Product-scoped semantics,
  hostile postvalidation, Pydantic validation, hashes, tests, or warnings.
- Xfail/skip masking, broad fallback, hardcoded production data, original Postgres/Milvus/forensic
  write, pointer mutation, Commit, Push, PR, Archive, promotion, or Cutover.

## Expected unchanged behavior

- Every absent-field legacy LaneRequest and S8R1 request/trace/result JSON and SHA-256 remains exact;
  pre-change fixed literal LaneRequest and `LocalRelationshipTrace` JSON/hashes prove this rather
  than comparing values generated only after the change.
- Existing exact, structured, lexical, vector, internal-reference, Technology relationship, and Web
  behavior remains unchanged.
- S7K legacy no-pair zero remains non-authoritative; authoritative zero remains installed.
- Task 8.3, aggregate S8, `tasks.md`, `acceptance.md`, and formal `56/80` remain unchanged.

## Required checks

- Exact pre-production fixed-literal legacy/S8R1 LaneRequest and trace baseline, normal strict xfail,
  forced RED at the S8R2 missing seam, and the real unsupported-path RED after removing xfail.
- Focused S8R2 GREEN with warnings as errors, S8R1 regression, corrected release/read predecessor
  matrix, complete physical/release owner, relationship/publication owners, KnowledgeRead/planning
  owners, and complete no-external Canonical V2 suite.
- Ruff check/format, changed-file compile, complete Canonical V2 Pyright, strict OpenSpec,
  `git diff --check`, offline locked package/source parity, scope/secret/cache, and frozen-target
  checks.
- Independent contract/test-feasibility reviews before Ready and independent implementation review
  before Accepted; zero open Critical/Important is required. Minor/YAGNI is recorded only.

## Evidence to update

- This contract, the S8R2 plan, and
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r2/verification-receipt.json`.
- Existing verification/change-log/agent-links/portfolio/mainline plan only after acceptance. Do not
  change `tasks.md` or `acceptance.md`.

## Stop conditions

- A clean applicant edge cannot be built from accepted Company/Patent typed projections and
  retained source evidence without changing S6/S7 semantics or production publication logic.
- The planner-level path cannot be mapped uniquely to `patent_has_applicant`, displayed Company
  authority cannot be bound before effects, or exact source/target eligibility cannot be proven.
- The change requires a generic path registry, direct free-text identity resolution, storage reopen,
  unrelated module, schema/persistence interface, or aggregate relationship closure matrix.
- Any existing owner regresses, original/production-like state changes, or Critical/Important review
  finding remains open.

## Done means

- One exact RED becomes one real release-bound displayed Company-to-Patent applicant traversal GREEN
  through `KnowledgeRead.execute`, with full canonical decision/evidence/release trace and no
  physical relationship read.
- Required checks and independent review pass with zero open Critical/Important.
- S8R2 is Accepted only as a Task 8.3 predecessor. Task 8.3 and aggregate S8 remain open at `56/80`.

## Rollback note

Remove the optional relationship enumeration policy, canonical public trace/validation and
source-witness constraint branch, public path branch, one S8R2 owner group/fixture extension, and
S8R2 evidence. No stored relationship, schema, index point, release pointer, task checkbox, or
external target requires rollback.
