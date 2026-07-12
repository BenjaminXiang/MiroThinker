# Slice Contract: s6d-relationship-red

## Status

Accepted. This is a test-only strict RED slice for OpenSpec Task 6.4 against
Accepted Task 6.1 commit `e6e6403`. Nine scenario groups have the exact intended
missing-module RED shape and focused static checks are green. It does not
authorize Task 6.5 production code, shared-contract or migration changes,
catalog edits, database writes, or Task 6.2/6.3 domain projection work.

Acceptance checkpoint: 2026-07-12. The task's single merged specification and
code-quality review initially found three Important issues: a future product
module received an `.agents` path; canonical relationship outputs lacked real
source-identity, assignment, assertion, and decision continuity; and source
potential was caller-reported. The test contract now supplies only the installed
catalog identity, binds real retained inputs through the shared S5 contracts,
and derives source potential from scenario plus catalog identity. The merged
review was rerun with no remaining Critical or Important issue.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.4`
- Depends on: Accepted aggregate S5 contracts/decision behavior and Accepted
  Task 6.1 catalog at commit `e6e6403`

## Goal

Freeze executable relationship behavior through one package-internal deep
module seam. The future implementation must consume the exact Accepted catalog,
retain evidence, enforce endpoint/direction/role/time/state semantics, and keep
metadata or typed-subobject endpoints distinct from canonical identities.

## Lean execution

- This slice contract and OpenSpec Task 6.4 are the only plan sources.
- Add one scenario group at a time and observe its exact missing-module RED
  before retaining the next group.
- Do not update OpenSpec task status or verification evidence in this writer
  checkpoint.

## Frozen seam

The future module is
`src.data_agents.canonical_v2.relationship_projection` and exposes one behavior
interface:

```python
class RelationshipProjection:
    def project(
        self, request: RelationshipProjectionRequest
    ) -> RelationshipProjectionResult: ...
```

Tests drive a future concrete in-process composition returned by
`create_ephemeral_relationship_projection()`. `KnowledgeBuild` later hides this
module; Task 6.4 does not awaken or extend the external `KnowledgeBuild` seam.

The request binds:

- the installed catalog schema/catalog/content identity, without a repository or
  `.agents` filesystem path;
- release/run/as-of context;
- candidate relationships with catalog relationship type/version, stable typed
  endpoints, roles, and proportional time values;
- for four-domain endpoints, the actual shared source-identity
  `RelationshipAssertion`, exact source-to-canonical assignments, and an
  evidence/policy-bound S5-shaped decision input selecting that assertion;
- for registry/sub-object/lineage endpoints, a complete typed assertion input
  plus a decision input selecting its exact assertion/evidence refs;
- retained assertion and artifact references;
- evidence-kind bindings from every catalog-required evidence kind to one or
  more retained assertion/artifact references.

The result exposes every candidate's admitted/rejected constraint outcome,
retained evidence references, relationship decision/state, and any current
relationship projection. Unresolved, rejected, or superseded outcomes never
produce a current relationship.

For four-domain canonical endpoints, accepted output includes the retained
shared `RelationshipAssertion`, an evidence-selected and relationship-policy-
bound shared `RelationshipDecision`, and the current projection when the row's
time/state makes it current. For registry/sub-object or lineage endpoints, the
result uses typed assertion/decision IDs with exact selected evidence refs and
policy binding; those IDs are not stored in canonical-identity-only fields.
Input/output source identity, source record, relationship type/version,
assignment, selected assertion/evidence, roles, policy, endpoint, and current
projection must remain field-for-field continuous. A caller-provided state or
generic evidence reference alone is insufficient and the module may not invent
source identities, records, assertions, or selections.

## Endpoint and evidence representation

`RelationshipEndpointReference` is discriminated by `reference_kind`:

1. `canonical_identity`: four-domain canonical identities use an explicit
   `canonical_identity_id` plus the catalog endpoint type.
2. `registry_entity`: a stable non-canonical registry entity such as a person,
   institution, topic, industry, geography, venue, or IPC class uses its catalog
   endpoint type and registry reference. It has no parent or canonical identity.
3. `typed_subobject`: a parent-owned product, capability, scenario, event, or
   other typed sub-object uses its catalog endpoint type plus an exact parent
   canonical-identity reference. It has no canonical identity of its own.
4. `lineage_record`: artifacts, source records, assertions, decisions, policies,
   and runs use a stable retained metadata reference plus the catalog endpoint
   type; they have no canonical-identity field.

Every endpoint type must be allowed by its catalog row. Metadata and sub-object
references must never be coerced into canonical-identity IDs merely to fit the
Accepted S5 canonical-identity-only relationship decision shape.

`RetainedEvidenceBinding` names one exact catalog `evidence_kind` and non-empty
`assertion_refs` and/or `artifact_refs`. All references resolve against the
request's retained registries, and every `required_evidence_kinds` entry is
covered. Model memory, summaries, unsupported strings, and a source-potential
label are not retained evidence.

## Frozen catalog

- Path:
  `.agents/runs/rebuild-canonical-v2-knowledge-platform/s6/domain-catalog-v1.json`
- Schema version: `canonical-v2-domain-catalog-v1`
- Catalog version: `canonical-v2-prd-catalog-2026-07-12`
- Content SHA-256:
  `c7730380f4534dc4c38a62e85550672d6d05b9c23d4a4a3f87df5eb397d808d2`
- File SHA-256:
  `e0c725859015b7b38b71220074ef03ed31193fc4fe8c2036c6cb2617435f55e3`

The tests read this artifact directly. They do not copy or redefine its 34 type
rows, seven families, required evidence kinds, roles, endpoints, states, times,
or eight direction records.

The artifact path is test authority only. A future product module must not
import, open, or receive a path under `.agents`; it resolves the supplied
schema/catalog/content identity against its installed packaged catalog.

## Required scenario groups

1. Identity/lifecycle: same-domain source/canonical identity resolution,
   merge/split, and decision supersession/reversal continuity.
2. Organization/role: exact role ownership, Professor-Company role distinction,
   team-member ownership, and non-Company organization separation.
3. Scholarly output: authorship/publication/reference and Professor-Paper
   attribution without changing Paper existence.
4. Intellectual property: applicant is not owner, page listing is not inventor,
   and Company/Professor paths require correctly resolved endpoints.
5. Company business/product/event: typed targets plus proportional validity or
   event-time behavior.
6. Taxonomy/topic/geography: typed target and time semantics without cross-family
   coercion.
7. Evidence/lineage: immutable accepted-only metadata lineage and matching
   decision/assertion family and subject.
8. Eight cross-domain directions: endpoint orientation is enforced while source
   potential remains distinct from built traversal or path eligibility. A RED
   direction probe validates only catalog orientation and non-fabrication; it
   does not execute retrieval or decide path admission.
9. Layer/non-fabrication: canonical, derived, and session layers remain distinct;
   absent or insufficient-evidence scenarios never fabricate accepted edges.

## Negative invariants

- Reject unknown type/version, disallowed or reversed endpoint types, dangling
  references, wrong identity, and cross-domain identity mismatches.
- Reject missing, extra, unsupported, or wrong-owner roles.
- Reject missing required evidence kinds or unresolvable retained references.
- Reject state/time shapes outside the catalog row.
- Preserve competing evidence; only accepted evidence-backed decisions may
  project current canonical relationships.
- Professor-Paper attribution rejection does not reject Paper identity.
- Patent applicant is not silently relabeled owner/assignee; Professor page
  listing is not automatically inventor identity.
- Derived/session relations are never source-grounded canonical facts.
- Catalog `supported` means source potential only; `absent` and
  `insufficient_evidence` remain non-edges.
- Source-potential outcomes are derived from `scenario_id` plus the installed
  catalog identity. Callers cannot supply or override an outcome label.

## Allowed scope

- This slice contract.
- `apps/miroflow-agent/tests/canonical_v2/test_relationship_projection_contract.py`

## Forbidden changes

- `apps/miroflow-agent/src/`, shared contracts, migrations, schemas, or any
  Task 6.1 catalog/builder/validator/test artifact.
- Any product import/open of `.agents` or a `.agents` path in the future module
  request.
- OpenSpec tasks, acceptance, change log, verification contract, or verification
  evidence in this writer checkpoint.
- Database, source, Milvus, provider, runtime, admin, retrieval, answer, release,
  or benchmark writes/calls.
- Local fake projection results, direct SQL/table assertions, or implementation
  call-count/order assertions.

## Required checks

- Observe each scenario group's exact-target missing-module RED before retaining
  the next group.
- Focused normal run reports exactly nine strict xfails and no failure/error/
  XPASS.
- Focused `--runxfail --no-cov` reports exactly nine `_MissingTargetModule`
  sentinel failures caused by the absent exact module. Nested or lazy missing
  dependencies fail normally.
- Focused Ruff check/format and app-environment Pyright pass.
- Accepted Task 6.1 catalog/shared-contract baseline remains 24 passed.

## Stop conditions

- A scenario requires semantics not present in OpenSpec or the Accepted catalog.
- Correct RED requires production/shared-contract/migration/catalog changes,
  Task 6.2/6.3 projections, persistence, DB/Milvus, provider, or retrieval/path
  eligibility behavior.
- Metadata/sub-object endpoints would be represented as canonical identities.
- A test can pass through a local fake instead of the future projection seam.
- RED fails for anything other than the exact absent target module.

## Done means

- Nine strict scenario groups freeze all seven families, eight cross-domain
  directions, and layer/non-fabrication through one future module interface.
- Normal/forced RED shapes and focused static checks are exact.
- Only this slice and one test module changed; Task 6.4 remains unchecked and no
  Task 6.5 implementation starts.
