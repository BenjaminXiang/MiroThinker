# Slice Contract: S8R5 Release-scoped Displayed Patent-to-Company Applicant Traversal

## Status

Accepted at `2026-07-20T09:38:32Z` after Candidate verification and targeted re-review reported
`C=0/I=0/M=0/YAGNI=0`. Ready was reached at `2026-07-20T09:00:14Z` after S8R4 contract and receipt
became Accepted, strict OpenSpec passed, and one lean independent review reported
`C=0/I=0/M=1/YAGNI=0`. Reviewed Specified hashes
were contract `efee07e08d8b769d9f87b96ec41a8e641961e8271d5be771f4f3a37fa1d4ab00`, plan
`47ffd65a944071320611b03053137e9573594c5c9edeee73378469817e0aa395`, and audit
`54c1eec24c72935af34ab14496d17c61919cb912309bd0edba6284fdfab11956`. The sole wording Minor was
repaired before Ready; Minor/YAGNI remain non-blocking and SHALL NOT create additional review
rounds. Task 8.3 remains unchecked and the formal ledger remains `56/80`.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- Requirement: `specs/evidence-first-query-orchestration/spec.md` — validated structured paths,
  bounded relationship recall, honest enumeration, source traceability, and displayed-set binding
- Accepted derived contract: Task 6 catalog scenarios `traversal_scenario.company_to_patent` and
  `traversal_scenario.patent_to_company`
- OpenSpec task: `8.3` (one public relationship direction only; remains unchecked)
- Depends on: Accepted S6, S7/S7K, S8P2, S8E1, S8L2, S8R1, S8R2, and sequencing acceptance of S8R4
- Audit: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r5/dependency-audit.md`
- Plan: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r5/implementation-plan.md`

## Goal

Execute one public relationship direction through the existing `KnowledgeRead.execute` interface:

```text
planner relationship type: company_has_patent
planner direction:         patent_to_company
planner source/target:     patent -> company
canonical relationship:   patent_has_applicant@canonical-v2-relationship-v1
canonical orientation:    Patent -> accepted Company applicant
execution orientation:    forward
```

Select only accepted current canonical relationships whose exact Patent source equals one exact
displayed Patent, whose exact target is an accepted current-release Company projection, and whose
only role is `applicant=<that Company stable reference>`. Return the Company projection without
reversing or relabeling the canonical claim.

## Non-goals

- No additional Patent relation, owner/assignee/inventor interpretation, generic organization
  relation, Professor/Company, Professor/Patent, or aggregate Task 8.3 completion.
- No relationship inference from PatentInventor, names, applicant strings, projected `company_ids`,
  current Web, or free text.
- No planner heuristic, new public API, factory, relationship type, registry, schema, migration,
  physical store read, index rebuild, release publication, or source mutation.
- No refactor/generalization of Accepted S8R2 trace classes or relationship infrastructure.
- No exhaustive-completeness claim for an open-world representative result.

## Request contract

Add the exact private path and finite endpoint mapping:

```python
_PATENT_TO_COMPANY_QUERY_PATH = (
    "company_has_patent",
    "patent_to_company",
    "patent",
    "company",
)

_RELATIONSHIP_ENDPOINTS[("company_has_patent", "patent_to_company")] = (
    "patent",
    "company",
)
```

The positive public plan has `domains=("company",)`, a `relationship` lane and optional independent
`web` lane, no relationship-reference/internal-reference query, one non-empty displayed Patent ID,
and exactly one equal protected `displayed_entity_set`. The plan may not retain the relationship
path after removing the relationship lane.

`LaneRequest.relationship_enumeration_policy` remains omission-preserving and is copied only for
the exact supported public path. It equals `plan.enumeration_policy`; all three as-of values on the
plan, policy, and lane request agree. The accepted shape is:

```text
mode:                   representative
scope:                  non-empty Patent-to-Company applicant scope
finite_universe_id:     None
finite_universe_source: None
finite_universe_ids:    ()
eligible_member_ids:    ()
required_member_ids:    ()
exhaustive:             false
continuation_state:     available
```

At the package-internal direct adapter seam, no displayed ID returns zero; one syntactically valid
release-unknown, internal, or known non-Patent ID returns zero; more than one ID fails. If a
protected set is present it must be the one exact equal tuple.

At public `KnowledgeRead.execute`, exactly one non-empty displayed Patent ID and one equal protected
slot are required. Missing, empty, duplicate, multiple, known wrong-type, internal, cross-release,
or protected-set-drift source authority fails before delegate/Web effects. One bare syntactically
valid but release-unknown public ID is an authoritative local zero; the independently planned Web
lane may still run.

Multiple paths, wrong path axes, a relationship-reference query, missing policy, policy/as-of drift,
wrong result domain, or relationship path/lane drift fails before effects.

## Release authority and replay contract

Reuse `_RelationshipAuthority` and the sole `create_isolated_relationship_lookup_adapter`. The
positive bundle is the Accepted S8R2 Company/Patent graph; no new authority fixture is required. For
each returned relation replay this exact chain in memory:

```text
RelationshipProjectionRequest.candidates
  -> exact RelationshipProjectionCandidate
  -> exact TypedRelationshipAssertionInput
  -> exact RelationshipCandidateOutcome
  -> exact RelationshipDecisionInput and TypedRelationshipDecision
  -> exact accepted CurrentRelationshipProjection
  -> selected RetainedAssertionReference
  -> exact public SourceAssertion/source-record identity
  -> exact PatentApplicant subobject on the displayed Patent
  -> exact displayed Patent public projection
  -> exact returned Company public projection
  -> Patent patent_to_company eligibility
  -> Company company_to_patent eligibility
```

Candidate, assertion, outcome, decision/current projection, selected evidence, release/run/schema/
registry identity, endpoints, observed/valid time, and content hashes remain exact. The candidate's
assertion input selects the typed assertion; its source-record reference equals the retained
reference and public `SourceAssertion.source_record_id`.

The canonical relation has source Patent, target Company, and exactly:

```python
{"applicant": f"canonical:company:{company_id}"}
```

The evidence binding has kind `patent_applicant_assertion`, one retained assertion reference, and
no substituted owner, assignee, or inventor evidence. The public assertion has Patent subject,
`field_path="applicants"`, the same retained source-record identity, and selects exactly one
`PatentApplicant` whose parent is the displayed Patent, `canonical_company_id` is the returned
Company, and supporting assertions contain the public assertion. A `PatentInventor`, owner,
assignee, generic organization target, name match, or ID-list match is never acceptable.

Both endpoint eligibility results bind the same current relationship decision. The displayed
Patent result has `traversal_directions=("patent_to_company",)`; the returned Company result has
`traversal_directions=("company_to_patent",)`. `admitted` returns; `limited` returns with the sorted
unique union of visible endpoint limitations; `excluded` at either endpoint yields zero. Review or
any other non-returnable outcome fails closed. Returned candidates carry no hard exclusions.

An earlier query than the relationship snapshot fails closed. Equal time adds no freshness flag. A
later query keeps the snapshot evidence and adds exactly
`relationship_snapshot_as_of:<canonical-UTC-timestamp>`.

## Result and trace contract

Add one dedicated `LocalPatentCompanyRelationshipTrace` union variant. Do not mutate
`LocalCanonicalRelationshipTrace` or its S8R2 hashes. The new trace has:

- `path="patent_company_relationship_traversal"` and `execution_lane="relationship"`;
- the release/manifest/index/publication and lane-request envelope from S8R2;
- `displayed_entity_ids=(patent_id,)`, `displayed_patent_id=patent_id`, and exact protected-slot ID/
  hash;
- query literals exactly matching `_PATENT_TO_COMPANY_QUERY_PATH`;
- the complete S8R2 request/result, candidate/assertion/outcome/decision/current, retained/public
  source-record, PatentApplicant, endpoint projection, and dual eligibility lineage;
- `candidate_domain="company"`, returned Company canonical ID/display, canonical identity,
  resolved state, score `1.0`, exact origin public evidence IDs, and exact quality flags;
- canonical-orientation claim fields exactly:

```text
claim_subject_id = canonical:patent:<displayed-patent-id>
claim_predicate  = patent_has_applicant
claim_value      = canonical:company:<returned-company-id>
claim_status     = accepted
```

`EvidenceItem.object_id`, candidate identity, fused identity, and canonical handle are the returned
Company. The evidence snippet remains the canonical JSON of the exact `PatentApplicant` subobject;
its locator remains the local release relationship locator and its observed time is the
relationship snapshot.

All tuple lineage is sorted and unique where ordering is not semantic. The new content-bound IDs
use distinct namespaces:

```text
local-patent-company-relationship-candidate:sha256:<...>
local-patent-company-relationship-evidence:sha256:<...>
```

The adapter preserves the content-bound current-relationship order and adds no ranking policy. An
internal Company-to-Patent replay SHALL use the finite authoritative current-relationship count,
not the caller result cap. The caller's `max_candidates` applies only after exact displayed-Patent
filtering and Company-candidate construction; a target Patent beyond the first internal forward
candidate therefore cannot become a false zero. Existing fusion may merge multiple raw edges that
resolve to the same Company.

## Source witness, constraints, Web, and fusion

The displayed Patent is a source-side constraint witness, not the returned identity. Only a valid
local `LocalPatentCompanyRelationshipTrace` with the exact displayed Patent and protected-slot
identity may satisfy `displayed_entity_set`. All relationship traces fused into one Company must
agree on that witness. Missing, forged, mixed, unrelated-lane, or current-Web witnesses fail.

Every other structured constraint applies to the returned Company and Company-scoped fused
evidence. Patent-only relationship text cannot satisfy or reject a Company geography, identifier,
or negation constraint.

Legitimate current Web evidence for the same returned Company may fuse under the existing snapshot
and handle rules. It may not manufacture the displayed Patent witness, a canonical Company ID, a
Patent-applicant relation, local evidence/trace IDs, or ownership of the canonical relationship
handle. The Accepted finite Web identity states remain exact: direct `canonical` evidence binds the
Company domain/object; `web_candidate` may retain an evidence-subject alias while proposing the
already accepted returned Company ID; `web_only` remains unresolved without a Canonical ID; unknown
or inconsistent states fail as invalid output. After fusion, the fused Canonical ID/domain must be
the returned Company. A non-local claim subject may be that Company's Canonical reference or its own
evidence alias, but another Canonical Company subject fails release-bound postvalidation. A Web
Patent alone cannot make the local traversal non-zero.

Top-level and fused evidence, raw/evidence IDs, candidate/auxiliary traces, constraint receipts,
snapshots, and entity handles remain collision-free and exactly replayable. Release-bound
postvalidation rebuilds expected local output from the in-memory authority and rejects missing,
extra, altered, or cross-lane-owned relationship material.

## Coverage contract

Coverage counts returned Company IDs only; the displayed Patent is not a returned or displayed
Company member. For representative results the exact semantics remain:

```text
unknown_scope:          true
exhaustive:             false
accounting_complete:    true
unknown_count:          None
required_member_outcomes: ()
continuation_state:     open_world
continuation_required:  true
```

Checked, eligible, retrieved, and displayed IDs are the bounded returned Company IDs; omitted and
unknown IDs are empty for this representative snapshot. Top-K or any non-empty result never implies
an exhaustive applicant population.

## Valid zero and integrity boundaries

Valid zero results include authoritative-empty relationship authority, a valid Patent with no
matching accepted applicant relation, a nonmatching relationship family, an excluded endpoint, and
`max_candidates == 0`. A syntactically valid release-unknown public Patent also yields local zero
without becoming a wildcard.

Integrity failure, not zero, applies to a matching relation with a missing/cross-release endpoint,
non-Company target, wrong canonical type/version, owner/assignee/inventor or extra role, wrong
evidence kind/field/subobject/source record, candidate/assertion/outcome/decision cross-wire,
missing/ambiguous eligibility, query predating the snapshot, or hostile delegate drift.

Hostile postvalidation rejects altered query axes, displayed witness, claim orientation, candidate
domain/identity/display, relation ID/state/roles, evidence/trace/quality flags, duplicate ownership,
missing/extra top-level or fused evidence, forged canonical/Web handles, cross-lane ID reuse, and
forged exhaustive coverage. The owner includes both the pre-filter cap-ordering regression and the
self-reported-canonical-ID/Web-evidence crosswire regression inherited from S8R4's inverse-view
boundary repair.

## Allowed scope

- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read.py`
- `apps/miroflow-agent/src/data_agents/canonical_v2/knowledge_read_isolated.py`
- `apps/miroflow-agent/tests/canonical_v2/test_internal_reference_projection_contract.py`
- S8R5-owned artifacts under
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r5/` and this contract
- Existing status/evidence summaries only after Candidate or Accepted evidence exists

## Forbidden changes

- OpenSpec `tasks.md`, `acceptance.md`, Task 8.3, or the formal `56/80` ledger
- Any existing slice contract, especially S8R1-S8R4 fields, discriminators, hashes, or behavior
- Catalog, relationship registry/projection, path eligibility, persistence, index/build/release
  schema, migration, or public API changes
- A second adapter/factory, physical relationship read, free-text inference, test-only positive
  production branch, or untraced relationship output
- Original PostgreSQL/Milvus/forensic source, business data, provider, secret, pointer, or external
  target mutation
- Xfail/skip masking, weakened validation, broad fallback, Commit, Push, PR, Archive, promotion, or
  Cutover

## Expected unchanged behavior

- All Accepted S1-S8R3 behavior and serialized literals remain exact; S8R4 behavior remains exact
  once Accepted.
- Company-to-Patent continues to return Patents from a displayed Company and preserves its S8R2
  trace/hash contract.
- Professor/Paper and Technology traversal, every non-relationship lane, Web lifecycle, fusion,
  rerank, sufficiency, and answer/session behavior remain unchanged.
- Unsupported planner paths/directions/endpoints retain their accepted error categories.
- No query without this exact path can construct or accept the S8R5 trace.

## Required checks

1. Verify S8R4 is Accepted before Ready or implementation.
2. Exact normal strict-xfail sentinel RED and forced RED before fixture/effect acquisition.
3. Focused S8R5 GREEN with warnings as errors.
4. S8R1 literal plus exact S8R1-S8R5 relationship matrix.
5. Relevant S7K/S8P2/S8E1/S8L2, relationship projection, path eligibility, release publication,
   query-planning, and physical/release owner tests.
6. Complete no-external Canonical V2 suite.
7. Ruff check/format-check, complete Canonical V2 Pyright, and changed-file `py_compile`.
8. Strict OpenSpec validation, `git diff --check`, targeted secret/forbidden-marker scan, generated
   cache cleanup, and confirmation that no original store/source/pointer was touched.
9. One lean final review with zero open Critical/Important. Record Minor/YAGNI without blocking or
   adding review loops.

## Evidence to update

- This contract and `s8r5/implementation-plan.md`
- `s8r5/verification-receipt.json` only after Candidate evidence exists
- Existing verification/portfolio/mainline/change-log/agent-link summaries only after Candidate or
  Accepted evidence exists
- Keep OpenSpec `tasks.md`, `acceptance.md`, Task 8.3, and `56/80` unchanged

## Stop conditions

Stop this slice without marking the global goal blocked if implementation requires a new relation
type, public/schema/storage change, physical data access, inference absent from S8R2 authority,
mutation of an Accepted trace, or a product decision about applicant/owner/assignee/inventor
semantics. Also stop before implementation if S8R4 is not Accepted.

Reviewer timeout, optional provider absence, S2C3C2, or a recorded Minor/YAGNI is not a global-goal
blocker and does not authorize scope expansion.

## Done means

After S8R4 acceptance, the exact Patent-to-Company planner path executes through public
`KnowledgeRead.execute`, returns only fully traced accepted Company applicants from one displayed
Patent, preserves the canonical Patent-to-Company applicant claim and strict role/evidence/
subobject identity, honors source-witness/Web/coverage/zero boundaries, passes all Required checks,
and receives zero-Critical/Important acceptance without checking Task 8.3 or performing any
forbidden action.

## Rollback note

Before acceptance, remove only S8R5-owned additions in the two read modules, the one vertical owner
test, and S8R5 artifacts. No migration, release pointer, original source, provider, or external
target rollback is required.
