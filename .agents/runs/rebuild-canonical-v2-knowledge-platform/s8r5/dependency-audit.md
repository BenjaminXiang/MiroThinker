# S8R5 Dependency Audit — 2026-07-20

## Outcome

The next smallest independently testable Task 8.3 predecessor is one release-scoped displayed-
Patent-to-Company applicant traversal:

```text
planner path:       company_has_patent / patent_to_company / patent -> company
canonical relation: patent_has_applicant@canonical-v2-relationship-v1
canonical direction: Patent -> accepted Company applicant
execution:          forward canonical traversal from one displayed Patent to Company applicants
```

There is no unresolved product, schema, storage, or authority decision for this direction. The
slice remains **Specified**, not Ready: S8R4 must first have an Accepted contract and receipt under
the repository's one-slice-at-a-time rule. S8R5 may be reviewed while S8R4 is finishing, but no
S8R5 production or test implementation may begin before that dependency is Accepted.

S8R5 is one Task 8.3 predecessor only. It SHALL NOT check Task 8.3 or change the formal ledger from
`56/80`.

## Why this path is authoritative

- The Accepted domain catalog maps both `company_to_patent` and `patent_to_company` to
  `patent_has_applicant@canonical-v2-relationship-v1` and marks both traversal scenarios
  `supported`.
- The catalog fixes the canonical source as Patent, the Company endpoint as target, and exactly one
  target role named `applicant` backed by `patent_applicant_assertion` evidence.
- The existing planner alias is `company_has_patent`. Following the already accepted inverse-
  direction convention, the exact reverse public path is therefore
  `company_has_patent / patent_to_company / patent -> company`; the planner alias does not become
  a canonical predicate.
- S8R2's clean relationship authority already requests both traversal directions, publishes the
  exact Patent and Company projections, and carries one current accepted Patent-to-Company
  applicant relation.
- S8R2's index helper already creates direction-bound `verified_relationship_traversal` results for
  the Company with `company_to_patent` and the Patent with `patent_to_company`, both bound to the
  same current relationship decision.

## Exact observable boundary

The displayed source witness is one exact accepted-release Patent bound by the matching protected
`displayed_entity_set`. The returned public candidate, fused identity, and canonical handle are the
accepted Company target. The canonical claim is not reversed:

```text
subject:   canonical:patent:<displayed-patent-id>
predicate: patent_has_applicant
value:     canonical:company:<returned-company-id>
status:    accepted
```

The relation must bind exactly:

```text
type/version: patent_has_applicant@canonical-v2-relationship-v1
source:       canonical:patent:<displayed-patent-id>
target:       canonical:company:<returned-company-id>
roles:        {"applicant": "canonical:company:<returned-company-id>"}
evidence:     one patent_applicant_assertion retained reference/source record
subobject:    the exact PatentApplicant on the displayed Patent
```

Applicant remains distinct from owner, assignee, inventor, and a generic organization link. Exact
type, singleton role equality, `SourceAssertion.field_path == "applicants"`, evidence kind, and
`PatentApplicant` continuity are all required; owner/assignee/inventor roles, `PatentInventor`,
name matching, Company ID lists, and Web claims are not substitutes.

## Reuse and implementation boundary

- Reuse `_RelationshipAuthority`, `_company_patent_relationship_authority`,
  `_s8r2_index_projection_request`, and the sole
  `create_isolated_relationship_lookup_adapter` factory.
- Reuse the existing S8R2 in-memory candidate/assertion/outcome/decision/current/evidence replay.
  A small inverse view may discover Company targets for the displayed Patent, replay the existing
  Company-to-Patent helper for each target, filter back to that Patent, and emit a dedicated
  Patent-to-Company trace and Company candidate.
- Add a dedicated inverse trace rather than changing the Accepted S8R2 trace fields, discriminator,
  or content hashes.
- Do not change the domain catalog, relationship registry, projection/storage schema, release
  format, path-eligibility engine, migration, or physical read path.

## Dependency decision

Required predecessors are the Accepted S6 catalog/relationship semantics, S7 candidate/index/
release authority, S7K generic relationship publication authority, S8P2 planner, S8E1 composition,
S8L2 displayed-set binding, S8R1 relationship replay mechanics, and S8R2 Company/Patent authority.
S8R4 is a sequencing gate only: it must be Accepted before S8R5 becomes Ready, but S8R5 does not
reuse Professor/Paper semantics.

S2C3C2 continues to gate reviewed calibration/oracle work, not this deterministic release replay.
Minor and YAGNI review notes are recorded but do not block Ready, Candidate, or Accepted; only open
Critical or Important findings block those transitions.

## Durable sources

- `openspec/changes/rebuild-canonical-v2-knowledge-platform/tasks.md` — Task 8.3;
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/specs/evidence-first-query-orchestration/spec.md`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/catalogs/domain-catalog-v1.json`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/relationship_projection.py`;
- `apps/miroflow-agent/src/data_agents/canonical_v2/path_eligibility.py`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8r2-release-scoped-displayed-company-patent-traversal.md`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s8r2/verification-receipt.json`;
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/slices/s8r4-release-scoped-displayed-paper-professor-traversal.md`.

No production code, test, OpenSpec task/acceptance artifact, existing slice, external store,
provider, source, pointer, Commit, Push, PR, Archive, promotion, or Cutover changed during this
audit.
