# Slice Contract: s6b-domain-inclusion-red

## Status

Accepted at `2026-07-12T17:17:06Z` against Accepted Task 6.1 commit
`e6e6403`. The five exact-target RED scenarios, the single merged
specification/code-quality review, and the lightweight test-only checkpoint are
closed with zero open Critical or Important findings. This slice does not
authorize Task 6.3 production code, schema or database changes, candidate
writes, publication, indexing, or runtime behavior.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.2`
- Depends on: Accepted Task 6.1 at commit `e6e6403`

## Lean execution

- This slice contract and OpenSpec Task 6.2 are the only plan sources.
- Add one observable inclusion scenario at a time and prove its exact missing-
  module RED before retaining the next scenario.
- Perform one merged specification/code-quality review after all Task 6.2
  scenarios are RED.
- Run only focused RED checks while iterating. Run the relevant no-database
  contract regression, static checks, strict OpenSpec, and diff/scope checks once
  before commit. This test-only task does not repeat database/source/candidate
  safety totals.

## Goal

Freeze the observable, versioned domain-inclusion behavior that decides whether
an identity-resolved object belongs in the Professor, Paper, Patent, or Company
canonical domain. Inclusion must be grounded in approved offline source scope
or retained validation evidence and must remain separate from enrichment
quality, retrieval-path eligibility, query-time Web evidence, and publication.

## User effect

- Approved Shenzhen Professor seeds remain discoverable even when ordinary
  profile enrichment is incomplete.
- Papers discovered through an included Professor roster anchor belong to the
  Paper domain without requiring a complete summary or a prematurely accepted
  Professor-authorship relationship.
- Every identity-resolved row in an approved Patent export remains in Patent
  scope without topic, linkage, patent-type, inventor, or IPC pre-filtering.
- Approved Company skeleton batches remain in scope despite ordinary profile
  gaps, while independently validated incremental Shenzhen innovation
  Companies can enter without being hardcoded into a legacy batch.
- A relevant national Web Company may support the current answer but cannot be
  silently written into the local Company canonical domain.

## Required scenarios

1. An identity-resolved Professor backed by a record in an approved Shenzhen
   seed roster is admitted with retained source/assertion evidence. Missing
   optional profile enrichment is at most a visible limitation, not an
   inclusion exclusion.
2. An identity-resolved Paper discovered from an included Professor roster
   anchor is admitted with the discovery provenance. Missing abstract/summary
   and unresolved authorship attribution do not change Paper existence or
   inclusion.
3. Identity-resolved Patents from an approved platform export are admitted as a
   set without topic or relationship filtering. Missing patent type, inventor,
   IPC, or semantic enrichment does not remove export rows from the domain.
4. Identity-resolved Companies from an approved skeleton batch are admitted
   without a completeness gate. A Company outside those batches is also
   admitted when a versioned offline decision independently validates both
   Shenzhen scope and innovation-company scope with retained assertions.
5. A query-time Web-only national Company with no approved skeleton membership
   and no offline Shenzhen-innovation validation is excluded from canonical
   Company inclusion. Its Web evidence remains outside the inclusion result and
   no query/answer path can mutate the decision.

## Interface boundary

Tests exercise one package-internal deep seam in
`src.data_agents.canonical_v2.domain_inclusion`:

```python
DomainInclusionEngine.evaluate(
    InclusionBatchRequest
) -> DomainInclusionResult
```

The request binds release/run/as-of, four shared inclusion `PolicyReference`
values, active identity-resolved candidates, retained source assertions/records,
included Professor anchors, retained incremental-Company validation decisions,
and one versioned content-bound approved-source-scope manifest. The manifest
names approved Professor seed, Paper discovery, Patent export, and Company
skeleton batches by immutable source-batch identity and content hash; candidates
cannot self-assert approval through a Boolean or a batch-name convention.

The result exposes shared `PolicyDecision` values, admitted/review/excluded
identity IDs by domain, evidence bindings, visible limitations, and a
deterministic content hash. The policy never consumes a global `ready` value and
never invokes Web, LLM, storage, or publication adapters.

Professor seed membership is the executable inclusion rule. “Shenzhen” is the
governance intent used when an operator approves the seed manifest, not a
runtime institution-name/geography whitelist.

An incremental Company outside an approved skeleton batch is admitted only
when one versioned offline validation decision records all four approved
dimensions as supported: basic identity, Shenzhen geography, innovation/business
relevance, and source validation. Each dimension binds retained assertion IDs;
the decision is independent when it was produced by the offline build from
landing evidence rather than by the current query, live-Web result, or bare LLM
world knowledge. The four dimensions are conjunctive for automatic admission.
Incomplete or materially ambiguous evidence yields `review` with visible
limitations and no canonical admission; explicit contrary geography or business
scope yields `excluded` with a named scope code. This avoids both automatic Web
promotion and an unnecessarily strict completeness gate.

Task 6.3 may keep this seam internal to `KnowledgeBuild`; Task 6.2 does not
activate `KnowledgeBuild.build` or expose a new public API.

## Non-goals

- Implement the inclusion adapter, typed domain projection, Pydantic domain
  objects, physical schema, migration, or PostgreSQL store (Task 6.3).
- Define or evaluate exact/structured/semantic/traversal/recommendation/ranking
  eligibility (Tasks 6.6-6.7).
- Implement relationship decisions or persistence (Tasks 6.4-6.5).
- Recollect sources, call live Web/LLM providers, write a candidate release,
  publish, build Milvus, or alter query/chat behavior.
- Enumerate Shenzhen institutions, reinterpret workbook answers as an inclusion
  template, or require pre-launch ID compatibility.

## Allowed scope

- One focused test module under
  `apps/miroflow-agent/tests/canonical_v2/`.
- This slice contract and Task 6.2 verification/task/change-log evidence.
- Deterministic synthetic source scopes, identity-resolved candidates,
  assertions, anchor references, and offline validation decisions.

## Forbidden changes

- Any file under `apps/miroflow-agent/src/` or `canonical_v2_alembic/`.
- Task 6.1 frozen catalog bytes or authority sources.
- Any database, original/recovery/candidate source, Milvus, provider, runtime,
  admin, retrieval, answer, benchmark, dependency, or secret mutation.
- A local fake policy that fabricates expected decisions, SQL/repository call-
  order assertions, institution-name enumeration, global `ready` mapping, or
  automatic Web-to-canonical promotion.
- A normal failing suite. Intentional RED is limited to the exact absent future
  `src.data_agents.canonical_v2.domain_inclusion` module and must be
  demonstrated separately with `--runxfail`.

## Expected unchanged behavior

- Accepted S1-S5 and Task 6.1 artifacts remain immutable and GREEN.
- The durable candidate remains the Accepted C2_0004 landing checkpoint with no
  typed domain, relationship, release, or index population.
- Existing Task 3.1 future deep-module and earlier accepted RED contracts retain
  their current expected states.

## Required checks

- Each scenario first fails for the exact absent target module.
- Focused normal run reports exactly five strict xfails and zero failures,
  errors, or XPASS.
- Focused `--runxfail` reports exactly five direct target-module sentinel
  failures; nested missing dependencies or fixture/setup failures are not
  masked.
- One merged Task 6.2 specification/code-quality review closes all Critical and
  Important findings.
- At commit checkpoint: relevant Canonical V2 no-database contract regression,
  Ruff, Pyright, strict OpenSpec, and diff/secret/cache/scope checks pass.
- No real PostgreSQL, Milvus, or provider check is required for this test-only
  slice; the accepted backup/source/candidate evidence is referenced rather than
  replayed because this task touches none of those boundaries.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`

## Stop conditions

- A scenario needs a product rule not traceable to the approved OpenSpec or
  authoritative domain sources.
- Inclusion would be inferred from quality completeness, semantic topic,
  relationship availability, query-time Web relevance, or model world
  knowledge rather than approved offline scope/evidence.
- Paper inclusion would require accepted authorship and thereby conflate Paper
  existence with Professor attribution.
- Patent export membership would be narrowed by missing type/IPC/inventor,
  topic, or linkage.
- Correct RED coverage requires production/shared-contract/migration/database/
  provider/query code or Task 6.3+ behavior.
- The RED failure is anything other than the exact absent target module.

## Done means

- Five strict scenarios cover all Task 6.2 effects through one concrete future
  inclusion-policy seam with evidence-bound, versioned, deterministic results.
- Normal and forced RED shapes are exact; the one merged review has zero open
  Critical/Important findings; checkpoint evidence is current.
- Task 6.2 is Accepted and committed alone. Task 6.3 has not started in the same
  commit.

## Acceptance checkpoint

- Five strict scenarios cover approved and unapproved Professor seeds,
  roster-anchored and global-only Paper discovery, approved and unapproved
  Patent exports, Company skeleton plus four-dimension incremental validation,
  incomplete Company review, contrary Company scope, and query-time Web-only
  Company exclusion.
- Professor seed membership is the executable rule without a runtime Shenzhen
  institution whitelist. Paper discovery evidence is distinct from authorship;
  Patent export rows are not filtered by topic, linkage, type, inventor, IPC, or
  enrichment; ordinary Company profile gaps do not become inclusion gates.
- The approved-source manifest is deterministic and content-bound to shared
  `EvidenceArtifact` hashes. Every result records the manifest hash; mismatched
  artifact content fails closed. Admitted, review, and excluded decisions bind
  retained source assertions and shared versioned inclusion policies.
- The one merged review initially found two Important issues: the manifest was
  not observably bound to results and non-admitted decisions could be asserted
  without evidence. Both were repaired in the same review; final status has no
  open Critical or Important findings.
- Focused normal pytest reports exactly `5 xfailed`; forced RED reports exactly
  five `_MissingTargetModule` failures for
  `src.data_agents.canonical_v2.domain_inclusion`. Ruff check/format and Pyright
  pass. Relevant no-database contract, strict OpenSpec, and diff/scope checks
  are recorded in `verification.md`.
- No production/shared-contract/migration/database/source/Candidate/Milvus/
  provider/runtime file or state changed. Task 6.3 owns GREEN implementation.
