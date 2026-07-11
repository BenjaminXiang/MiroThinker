## Context

The system is pre-launch. Its current V042 database, canonical writers, retrieval implementation,
and chat route are implementation evidence, not compatibility constraints. The current chat module
combines query classification, direct SQL, vector retrieval, Web search, relationship traversal,
session behavior, LLM calls, and response rendering. Provenance, identity, relationship, and quality
semantics are split between domain tables, JSON fields, scripts, and caller-specific rules. This
shape makes the confirmed outcomes—broad but precise retrieval, universal Web augmentation,
reversible identity, typed relationships, path eligibility, grounded generation, and release/index
parity—costly to implement and difficult to verify through a stable interface.

The destructive test incident removed the old production-like data and demonstrated a separate
operational requirement: recovery evidence and the original source volumes must remain immutable,
while all reconstruction, migration, and acceptance work occurs in an isolated new database and new
index release. Verified WAL/FPI salvage, historical SQLite/JSONL/XLSX files, Milvus copies, and new
collection responses are evidence inputs, not a schema to clone.

Dependencies fall into three design categories:

- Postgres and local files are local-substitutable dependencies and are tested with real isolated
  local instances/files through internal seams.
- Milvus has production and deterministic test adapters at a real index seam.
- Web, LLM, embedding, and reranking providers are true external dependencies behind injected ports
  with recorded fake adapters for tests.

## Goals / Non-Goals

**Goals:**

- Build a clean typed Canonical V2 database from immutable evidence while preserving source
  assertions, recovery lineage, conflicts, and reversible identity decisions.
- Keep Professor, Company, Paper, and Patent knowledge strongly typed while sharing identity,
  evidence, relationship, temporal, eligibility, release, and gap semantics.
- Expose deep module interfaces that hide physical storage, provider, policy, and orchestration
  complexity from callers and tests.
- Make exact, structured, lexical, semantic, relationship, and current-Web evidence available to a
  validated query plan with protected query constraints and traceable rewrites.
- Use LLM reasoning extensively for ambiguity, relevance, fusion, sufficiency, and synthesis without
  treating model memory or confidence as evidence.
- Publish canonical projections and Milvus indexes as one accepted release with deterministic parity
  and rollback evidence.
- Validate the rebuilt platform against PRD scenario families and multidimensional gates, not a
  fixed-answer workbook alone.

**Non-Goals:**

- Preserve V042 physical tables, pre-launch internal IDs, old collection names, old chat handlers,
  or implementation-coupled tests for compatibility.
- Turn the four-domain platform into an unbounded national knowledge base.
- Model every field as a generic graph property or apply full bitemporal storage to every value.
- Let online Web results write directly to active canonical or Milvus state.
- Generate exhaustive graph dumps or long-form research reports in one query.
- Write to or cut over the original `pgtest` database or original Milvus file in this change without
  a separate explicit promotion authorization.

## Decisions

### 1. Build a clean typed platform, not V042 sidecars or a generic graph

Canonical V2 uses a new database baseline with four kinds of physical schema:

- `landing`: immutable artifact manifests, source records, parser runs, and content references;
- `knowledge`: shared identity, source assertion, canonical decision, relationship catalog,
  relationship assertion, temporal, policy, and release metadata;
- typed domain schemas for Professor, Company, Paper, and Patent current projections and their
  business sub-objects;
- `publish` and `ops`: release projections/manifests plus knowledge gaps, reviews, and decisions.

Domain facts remain typed because PRD filters and invariants differ materially: Professor
affiliation is not Company financing, Paper authorship is not Patent applicant ownership, and IPC
filters are not research-direction filters. Shared claim/relationship metadata provides uniform
provenance and fusion without forcing all values into an EAV interface.

Alternatives considered:

- Extending V042 with assertion/release sidecars would reuse code sooner but retain duplicate status,
  writer, and query semantics across old and new paths.
- A fully generic node/claim/edge graph maximizes schema flexibility but makes common typed filters,
  constraints, and validation indirect and leaks complexity back to callers.

### 2. Make source assertions immutable and canonical values reproducible

Every source contribution becomes a time-bound source assertion linked to a landing record and a
resolved source identity. Assertions are append-only. A canonical decision selects one or more
supporting assertions for a typed field or relationship and records policy version, decision method,
LLM decision trace when used, confidence, rationale, and unresolved conflicts.

The current domain projection is reproducible from assertions and decisions. Recollection adds new
assertions; it never overwrites forensic or historical evidence. Publication of a new current value
does not erase the previous decision or its assertions.

Minimal temporal semantics apply: every assertion has observation/fetch time and optional source
publication/event time; inherently changing facts may have valid-from/valid-to. Full bitemporal
storage is not imposed on static identifiers or fields without a time-dependent product meaning.

### 3. Resolve identity reversibly and separate identity from source records

Strong identifiers and deterministic composite matches resolve automatically. Ambiguous
cross-format or semantic cases use a structured LLM decision, with human review reserved for
high-impact unresolved cases. Every merge/split retains source identities, evidence, decision run,
and reversal lineage.

Canonical V2 may assign new primary IDs. Historical IDs are source identities and lookup lineage,
not compatibility obligations. All rebuilt cross-domain references use the accepted canonical
identity graph.

### 4. Use an extensible typed relationship catalog

Each canonical relationship type defines source/target entity types, direction, role semantics,
required evidence, time semantics, allowed states, and path eligibility behavior. The catalog covers
identity/lifecycle, organization/role, scholarly output, intellectual property, Company
business/product/event, taxonomy/topic/geography, and evidence/lineage families.

Relationship assertions and canonical relationship decisions follow the same retained-evidence and
conflict model as fields. Derived similarity/ranking/trend relations are release-scoped computations,
not source-grounded canonical facts. Session referents and result sets remain conversation state.

### 5. Replace global readiness with versioned path eligibility

Inclusion answers whether an identity-resolved object belongs in a PRD domain. Path eligibility
answers whether its present evidence/content can support a specific path: exact lookup, verified
relationship traversal, semantic recall, recommendation, ranking, or another named path.

Policies are versioned and return an admission/limitation result, not only a Boolean. Ordinary
incompleteness lowers score, adds a limitation, or creates an enrichment gap. Hard exclusion is
limited to named invariants such as wrong identity, terminal merge/rejection, unsafe exposure,
broken references, or no usable source-grounded facts.

### 6. Put the main complexity behind five deep modules

The external seams are deliberately small:

```python
class EvidenceLanding:
    def ingest(self, request: IngestEvidenceRequest) -> LandingReceipt: ...
    def stream(self, source_batch_id: str) -> SourceRecordStream: ...

class KnowledgeBuild:
    def build(self, request: BuildCandidateRequest) -> CandidateRelease: ...

class KnowledgeRead:
    def execute(self, plan: RetrievalPlan) -> EvidenceSet: ...

class KnowledgeAnswer:
    def answer(self, turn: TurnRequest) -> TurnResult: ...

class ReleasePublication:
    def verify(self, candidate_release_id: str) -> ReleaseVerification: ...
    def promote(self, accepted_release_id: str) -> PublishedRelease: ...
    def rollback(self, published_release_id: str) -> PublishedRelease: ...
```

`KnowledgeBuild` hides parsers, identity resolution, LLM adjudication, domain inclusion, typed
projection, relationship fusion, eligibility materialization, and gap creation. Callers receive a
candidate release and structured diagnostics, not per-table mutation methods.

`KnowledgeRead.execute` hides SQL, lexical, vector, relationship, and release adapters. Tests and
callers exercise the same plan/result interface. Domain-specific retrieval implementations remain
internal seams.

`KnowledgeAnswer.answer` hides A-G classification, session resolution, protected rewrites, plan
validation, concurrent lane execution, deduplication, fusion, rerank, sufficiency retry, claim
selection, citation, and progressive followups. HTTP is an adapter, not the module.

`ReleasePublication` is the only interface allowed to change the active release pointers. It does
not own canonical building or acceptance policy; it consumes an already accepted release.

### 7. Preserve A-G effects while using a validated LLM-assisted plan

A-G remains the behavior and evaluation taxonomy, not a fixed handler switch. Deterministic parsing
extracts and protects exact identifiers, time, geography, negation, relation direction, and other
explicit constraints. Structured LLM output resolves conversational context, proposes semantic and
domain intent, and produces a typed plan that the server validates against supported operations and
budgets.

Multi-view rewrites retain the original query and protected slots. Views may target context,
canonical aliases, semantic expansion, individual local domains, or current Web. Every candidate is
traceable to query, rewrite, lane, attempt, release, and source evidence.

### 8. Retrieve broadly, fuse late, and retry only for material evidence gaps

Independent exact/structured, lexical, vector, relationship, and Web lanes execute concurrently and
return bounded recall-oriented candidates. Identity deduplication and evidence aggregation happen
before deterministic constraints and LLM-assisted late reranking.

After fusion, a structured LLM sufficiency decision evaluates the material parts of the question.
Only a material gap can trigger a targeted supplemental attempt, and wall-time/provider/cost budgets
bound it. Budget exhaustion returns the best supported partial answer plus explicit limitations.

Web runs for every information-retrieval request (A/B/C/D/E/G). Refusal, clarification-only, and UI
control turns do not search. Web failure degrades to available local evidence. Search results remain
live-Web evidence unless a later offline gap/recollection run promotes supported assertions through
the full build process.

### 9. Ground every material answer claim and keep assessment explicit

The answer module first builds a validated claim-evidence map. Concrete identity, relationship,
capability, role, date, and numeric claims require local or current-Web evidence. LLM world knowledge
may guide interpretation, relevance, plausibility, comparison, and language, but model confidence is
not a source.

Web claims show Web provenance to users. High-confidence local claims may use grouped card/source
affordances while retaining internal claim-level mapping. Conflicts and model-only inference are
disclosed at the affected claim.

Assessment questions use explicit dimensions and sourced supporting facts. The final assessment is
labeled as synthesis with conditions and uncertainty; it is not stored as a canonical objective
field.

Answers use progressive disclosure: answer the current question, provide necessary evidence and
limitations, then suggest only actually available eligible next-hop relations. The user chooses the
next traversal; session state retains the displayed set, constraints, and path.

### 10. Treat LLM, Web, embedding, reranking, and Milvus as real seams

Each external dependency has a narrow injected port, a production adapter, and a deterministic
recorded fake adapter. All intermediate LLM tasks use versioned validated schemas and include
evidence IDs, confidence, rationale, and uncertainty. Schema-invalid output has a bounded retry and
named degradation path; it cannot control writes or execution silently.

Postgres is tested through real isolated databases because SQL constraints, transactions, and
release semantics are part of the behavior. The database target must be passed explicitly; tests
must fail closed when the target identity does not match the expected disposable database.

### 11. Publish one release across canonical, serving, and Milvus

A build produces an immutable candidate release manifest containing source batches, policy/model
versions, canonical object/relationship counts and hashes, eligibility counts, projection hashes,
and expected index manifests. Acceptance attaches verified results to that release.

Milvus builds versioned domain/intent projections from the candidate. Every point identifies the
canonical object, canonical release, projection policy/schema, embedding model, and content hash.
Promotion changes serving pointers/aliases only after DB/index parity passes. The prior accepted
release remains rollback-capable.

The initial Canonical V2 release and any schema, embedding, or eligibility-policy change require a
full index rebuild. Ordinary later updates may use versioned incremental refresh, with scheduled full
reconciliation.

### 12. Turn observed failures into reviewed knowledge gaps

No-result, insufficient-evidence, repeated live-Web dependence, relation absence, user feedback,
and benchmark failures produce typed gap records tied to the query/answer trace and release. LLM
classification may propose the owning lane and a recollection/enrichment action, but a reviewed
offline run performs any canonical mutation.

## Risks / Trade-offs

- **[Risk] The clean-slate scope is large and may stay half-finished.** → Deliver independently
  accepted vertical slices. No later slice may depend on an unaccepted predecessor. Keep the old
  implementation available only as a comparison oracle until the replacement reaches acceptance.
- **[Risk] A generic assertion layer can become EAV-heavy.** → Keep user/query-facing domain facts
  typed; use generic assertion metadata for provenance and decisions, not as the only query model.
- **[Risk] LLM-assisted fusion may be non-reproducible or wrong.** → Version prompts/models/schemas,
  retain inputs/outputs, validate structured results, use deterministic hard constraints, and route
  high-impact ambiguity to review.
- **[Risk] Soft quality policies may reduce precision.** → Use bounded wide recall, late evidence-
  aware ranking, visible limitations, and independent precision gates rather than early blanket
  exclusion.
- **[Risk] Universal Web increases false positives, latency, and cost.** → Execute concurrently,
  apply source/identity/fusion rules, use bounded budgets/cache, record lane provenance, and measure
  Web-specific precision and cost.
- **[Risk] New IDs may break hidden assumptions in callers.** → Migrate all repository consumers in
  the same accepted slices, retain historical IDs as lineage, and test cross-domain integrity through
  the new interfaces rather than preserve old IDs by default.
- **[Risk] Candidate DB and index can drift.** → Manifest every projection and block promotion on
  deterministic release/parity mismatch.
- **[Risk] Tests can again target a non-disposable database.** → Require explicit DSNs, assert
  database identity before migration/write tests, and prohibit environment fallback for destructive
  paths.
- **[Risk] Recovery completeness is physically limited.** → Report source/baseline coverage honestly,
  recollect missing PRD evidence, keep unresolved gaps, and never manufacture parent rows or facts.

## Migration Plan

1. Keep original `pgtest` paused and original Milvus unopened; verify forensic hashes before and
   after read-only inventory work.
2. Complete the source inventory and reviewed baseline in the isolated recovery lab. Freeze numeric
   acceptance thresholds without writing the original sources.
3. Create the new Canonical V2 database baseline and module interface contract tests.
4. Ingest forensic/historical sources into immutable landing through source adapters; checkpoint and
   verify chain-of-custody manifests.
5. Build typed domain identity/assertion/relationship projections into a candidate release; add
   targeted recollection/enrichment for measured PRD gaps.
6. Build versioned published projections and full Milvus indexes from the same candidate manifest.
7. Run domain/path retrieval, relation, grounded-answer, Web, parity, latency/cost, and rollback
   acceptance. Iterate only inside isolated candidate releases.
8. Migrate admin/chat/data consumers to the new module interfaces and run old/new scenario comparison
   as evidence, not as a compatibility promise.
9. Obtain explicit acceptance and separate cutover authorization. Promotion to any production-like
   target is outside this plan until then.

Rollback during development discards or deactivates the rejected candidate and restores the prior
accepted release pointers. It never rewrites forensic landing evidence.

## Open Questions

- Exact numeric thresholds not already fixed by PRD will be frozen after the authorized read-only
  candidate/source baseline and reviewed labels.
- Exact model/provider choices and per-route call budgets remain configuration decisions subject to
  the accepted quality, latency, and cost gates.
- Physical table names and internal ID format remain implementation choices as long as the typed
  domain, lineage, reversibility, and interface contracts are met.
