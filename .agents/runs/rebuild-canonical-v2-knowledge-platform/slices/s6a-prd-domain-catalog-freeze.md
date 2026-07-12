# Slice Contract: s6a-prd-domain-catalog-freeze

## Status

Accepted at `2026-07-12T16:40:08Z` against Accepted Task 5.6 commit `40a0bef`.
All four vertical TDD increments, the one merged specification/code-quality
review, and the merged commit-checkpoint L2/L3 are closed with zero open
Critical or Important findings. This slice implements OpenSpec Task 6.1 only;
it does not implement domain projections, inclusion, relationship persistence,
eligibility, release publication, retrieval, or answer behavior.

## Parent

- OpenSpec change: `openspec/changes/rebuild-canonical-v2-knowledge-platform/`
- OpenSpec task: `6.1`
- Depends on: Accepted aggregate S5 at commit `40a0bef`
- Authority reconciliation: `source-links.md` records the Professor/Paper
  requirement-review precedence and workbook ground-truth policy.

## Lean execution

- This slice contract and OpenSpec Task 6.1 are the only implementation-plan
  sources.
- Implement one catalog effect at a time through an observed RED and the nearest
  deterministic validation.
- Perform one merged specification/code-quality review for Task 6.1.
- Run Task 6.1 L2/L3 once at the commit checkpoint. No database, Milvus, provider,
  or broad runtime regression belongs to this evidence-only slice.

## Goal

Freeze a compact, deterministic, versioned, source-cited catalog that makes the
Professor, Company, Paper, and Patent knowledge expected by the PRDs explicit.
The catalog must give later builders one unambiguous typed field/sub-object
vocabulary and an extensible relationship vocabulary broad enough for exact,
structured, semantic, relationship, cross-domain, and progressive multi-turn
effects. It must not confuse source-grounded canonical relationships with
release-derived or session-only relationships.

## User effect

- Every PRD-required object fact can later be projected, filtered, displayed,
  cited, and assessed through a named typed field or sub-object rather than an
  untyped summary or ad-hoc JSON convention.
- Business relations are not limited to Professor→Company, Professor→Paper, and
  Company→Patent. The catalog covers all seven approved canonical families and
  records direction, roles, evidence, state, time, and future eligible paths.
- The four cross-domain base pairs support both documented traversal directions
  for later user-directed multi-turn exploration; one query is not required to
  exhaust the graph.
- Missing local evidence is reported as supported, absent, or insufficient for a
  relationship scenario. A missing edge does not cause the type to disappear or
  encourage an invented fact.

## Source precedence

1. Active OpenSpec behavior contract and modified capability specs.
2. `docs/Data-Agent-Shared-Spec.md` for shared logical contracts.
3. Domain authority:
   - Company: `docs/Company-Data-Agent-PRD.md`;
   - Professor: the Requirements Audit plus explicit locked Professor Review
     overrides, not the legacy Professor PRD;
   - Paper: the Paper PRD plus explicit locked Paper Review overrides;
   - Patent: `docs/Patent-Data-Agent-PRD.md`.
4. Accepted S2 source-to-PRD coverage and threshold/corpus evidence.
5. Workbook rows as high-value case-specific ground truth and scenario seeds,
   never as schema authority or a generalized answer template.

## Catalog contract

### Frozen artifact

The frozen artifact SHALL contain:

- `schema_version`, `catalog_version`, `status=frozen`, and canonical JSON hash;
- a deduplicated source manifest with path, authority tier, complete-file SHA-256,
  and exact citation ranges;
- one shared projection envelope and exactly four domain catalogs;
- a requirement/scenario coverage ledger and a deferred-owner ledger;
- deterministic ordering and globally unique IDs.

The validator SHALL reject source hash/range drift, missing source terms,
duplicate IDs, unknown fields, incomplete domain/family coverage, unresolved
Task 5.5/5.6 placeholders, or nondeterministic serialization.

### Fields and sub-objects

Every field records at least a stable `field_path`, value shape, cardinality,
requiredness scope, semantic use, temporal class, evidence obligation, and
citations. Every sub-object records its type, parent/cardinality, typed members,
identity key where applicable, temporal class, evidence obligation, and
citations.

Freeze now:

- shared identity/type/display/core/summary/evidence/update/run/quality-signal
  envelope semantics;
- Professor identity/name, affiliation/department/title/contact, research,
  profile/paper/patent summaries, metrics, projects, awards, lifecycle and
  manual-review semantics plus affiliation, education, work, contact, award,
  project, and metric-history sub-objects;
- Company identity/corporate/geography/foundation, industry, summaries,
  capital/website/patent count and structured personnel plus financing,
  personnel education/work, product, capability, scenario, and public-update
  sub-objects;
- Paper title/identifiers/authors/time/venue, abstract/keywords/metrics,
  summaries, Professor projection, optional accepted enrichment/full-text
  fields plus author, identifier, publication, full-text, summary, funding,
  reference, and enrichment-provenance sub-objects;
- Patent identifiers/titles, applicants/inventors, type/time,
  abstract/summary/effect/IPC and Company/Professor projections plus applicant,
  inventor, IPC, milestone, and technical-summary sub-objects.

`top_papers` is not a Professor canonical field. Representative Papers are a
later release-derived relation over eligible Paper relationships.

### Relationships

Each frozen canonical relationship type SHALL be representable by the Accepted
`RelationshipType` contract and include `relationship_type_id`, `version`,
`layer`, endpoint types, direction, structured roles, required evidence kinds,
time semantics, allowed decision states, future eligible path names, and exact
citations.

The catalog SHALL cover these canonical families:

1. identity/lifecycle;
2. organization/role;
3. scholarly output;
4. intellectual property;
5. Company business/product/event;
6. taxonomy/topic/geography;
7. evidence/lineage.

Concrete coverage includes affiliation, department, education and work;
role-distinct Professor–Company founder/employment/adviser/investor/cooperation
semantics; Company team roles; Professor–Paper attribution distinct from Paper
existence; Paper author/venue/reference/topic; Patent applicant/inventor;
Company–Patent and Professor–Patent evidence; Company product/capability/
scenario/financing/public update; industry/topic/geography/IPC; and artifact,
record, assertion, decision, policy, run, merge/split, and supersession lineage.

The artifact SHALL also freeze the three relationship-layer boundaries:

- canonical relations require retained source/assertion/decision evidence;
- derived similarity/ranking/trend/representative-result relations are
  release-scoped computations and never canonical facts;
- session referents, displayed sets, constraints, and traversed paths are
  conversation state and never canonical facts.

Concrete derived relation definitions remain S7/S8-owned; concrete session
relation definitions remain S9-owned. Task 6.1 records those exclusions and
owners rather than inventing their later execution contracts.

## Scenario accounting

- Each cataloged canonical relationship type has at least one PRD/user-effect
  scenario reference.
- Every required relationship family and both directions of the Professor↔Paper,
  Professor↔Company, Professor↔Patent, and Company↔Patent base pairs are
  accounted as `supported`, `absent`, or `insufficient_evidence` against the
  Accepted S2 source matrix.
- `supported` means source evidence exists, not that a canonical edge has been
  built or accepted.
- `absent` and `insufficient_evidence` remain explicit coverage gaps; the
  validator cannot silently omit them.

## Non-goals / deferred owners

- Task 6.2–6.3: inclusion scenarios, admission rules, Pydantic domain current
  projections, physical tables, adapters, and migrations.
- Task 6.4–6.5: executable relationship scenarios, persistence, assertions,
  decisions, and cross-row integrity.
- Task 6.6–6.7: path admission/limitation outcomes. Task 6.1 freezes only named
  future paths and never recreates a global `ready` gate.
- S7/S8: derived relation execution, candidate manifests, published/index
  projections, and retrieval.
- S9: session relationships and progressive traversal execution.
- Candidate population, recollection, enrichment, release/index parity, and
  benchmark acceptance.
- Patent ownership/assignee semantics not established by an authoritative
  applicant source.

## Allowed scope

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/s6/`
- this slice contract;
- Task 6.1 sections of `verification-contract.md` and `verification.md`;
- `source-links.md` and `agent-links.md` only for the approved authority/DAG
  synchronization;
- `tasks.md`, `change-log.md`, and applicable `acceptance.md` evidence at the
  Candidate-to-Accepted checkpoint.

## Forbidden changes

- Production Python, public interfaces, shared Pydantic contracts, migrations,
  domain tables/models, query/chat/admin code, Milvus schemas or collections.
- Original, recovery, durable-candidate, disposable-database, or provider writes.
- PRD rewrites, legacy ID compatibility rules, institution name enumeration,
  answer-template fields, or workbook-case hardcoding.
- Task 6.2+ implementation or acceptance.

## Vertical TDD increments

1. **Artifact/source RED/GREEN:** exact authority manifest, citation ranges,
   source terms, hashes, deterministic bytes, and four-domain envelope.
2. **Domain RED/GREEN:** complete typed fields and sub-objects with no unresolved
   requiredness/name conflicts after precedence is applied.
3. **Relationship RED/GREEN:** seven canonical families, exact
   `RelationshipType` shape, proportional time/state semantics, three-layer
   separation, and no attribution/existence or applicant/owner conflation.
4. **Scenario RED/GREEN:** 100% type/family/direction accounting with explicit
   supported/absent/insufficient-evidence outcomes and deferred owners.

## Required checks

- L1: nearest catalog validator/test for the active increment.
- L2: complete Task 6.1 catalog tests plus Accepted shared-contract tests.
- One merged Task 6.1 spec/code-quality review with zero open Critical/Important
  findings.
- L3: deterministic rebuild/check, Task 6.1 tests, relevant shared-contract
  tests, Ruff/Pyright for validator code, strict OpenSpec, formal verification-
  contract gate, diff/secret/source-drift checks, and clean artifact scope.
- No real PostgreSQL/Milvus/provider test is required because Task 6.1 changes no
  executable storage or runtime behavior.

## Evidence to update

- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification-contract.md`
- `.agents/runs/rebuild-canonical-v2-knowledge-platform/verification.md`
- `openspec/changes/rebuild-canonical-v2-knowledge-platform/{tasks.md,change-log.md}`
- applicable catalog-level assertions in `acceptance.md` only when objectively
  proven.

## Stop conditions

- A required field/sub-object lacks authoritative citations or a typed shape.
- A relationship needs product semantics absent from OpenSpec/authoritative
  sources, or cannot receive exact direction, roles, evidence, state, time, or
  future path semantics without invention.
- A derived/session relation would be mislabeled source-grounded canonical fact.
- Professor-page attribution would be conflated with Paper identity/existence,
  or Patent applicant would be silently relabeled owner/assignee.
- Correctness requires a production/shared-contract/migration change, DB/Milvus
  write, provider call, or Task 6.2+ behavior.
- Accepted source evidence or safety identities drift.

## Done means

- The compact frozen artifact deterministically covers all four domains, typed
  sub-objects, seven canonical relationship families, layer boundaries, future
  eligible paths, and required scenario/direction accounting with exact source
  citations and no stale unresolved placeholders.
- The one merged review has zero open Critical/Important findings; all required
  checks pass; Task 6.1 is Accepted and committed alone.
- No Task 6.2 implementation, domain schema, migration, database/Milvus write,
  provider call, or runtime/query behavior is mixed into the checkpoint.

## Acceptance evidence

- Frozen content SHA-256: `c7730380f4534dc4c38a62e85550672d6d05b9c23d4a4a3f87df5eb397d808d2`;
  checked-in file SHA-256: `e0c725859015b7b38b71220074ef03ed31193fc4fe8c2036c6cb2617435f55e3`.
- Catalog totals: 14 authority files, 27 exact citations, 9 shared fields,
  101 domain fields, 28 sub-objects, 7 families, 34 relationship types,
  42 scenarios, 8 cross-domain directions, and 5 explicit deferred owners.
- Deterministic builder `--check` passed. Task 6.1 plus Accepted shared-contract
  tests passed `24 passed in 0.62s`.
- Ruff check/format passed; app-environment Pyright returned `0 errors, 0
  warnings, 0 informations`.
- Formal S2B gate remained `state=accepted`, `source_count=50`, backup manifest
  `a14c1eab…e59c8`, and restore verification `98826e8d…7d231`.
- Strict OpenSpec validation, tracked diff/whitespace, high-confidence secret,
  generated-cache, and final artifact-scope checks passed.
- The one merged review closed five Important findings and returned final
  `Ready: Yes`; no Critical finding remained.
