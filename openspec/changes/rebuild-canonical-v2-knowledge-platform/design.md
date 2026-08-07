## Context

The system is pre-launch. Its current V042 database, canonical writers, retrieval implementation,
and chat route are implementation evidence, not compatibility constraints. The current chat module
combines query classification, direct SQL, vector retrieval, Web search, relationship traversal,
session behavior, LLM calls, and response rendering. Provenance, identity, relationship, and quality
semantics are split between domain tables, JSON fields, scripts, and caller-specific rules. This
shape makes the confirmed outcomes—broad but precise retrieval, evidence-driven Web augmentation,
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
- Prove that every original Postgres/Milvus/recovery/historical source family has a content-addressed
  backup and independently verified restore before the first Canonical V2 or landing write.
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
- Align the real chat experience with the 17 conversations and 25 query turns in the customer-
  provided `docs/测试集答案.xlsx`, while retaining broader PRD behavior and avoiding answer hardcoding.

**Non-Goals:**

- Preserve V042 physical tables, pre-launch internal IDs, old collection names, old chat handlers,
  or implementation-coupled tests for compatibility.
- Turn the four-domain platform into an unbounded national knowledge base.
- Model every field as a generic graph property or apply full bitemporal storage to every value.
- Let online Web results write directly to active canonical or Milvus state.
- Let query-time reference resolution, Web results, or LLM output mutate the canonical identity
  graph or source-identity mappings.
- Generate exhaustive graph dumps or long-form research reports in one query.
- Write to or cut over the original `pgtest` database or original Milvus file in this change without
  a separate explicit promotion authorization.
- Require contract-review, exclusion-review, blind-calibration, or scaled human-labeling work before
  the customer can use and evaluate the real system.
- Treat workbook answer text as product data, a prompt template, or a wording-matching oracle.

## Decisions

### 0. Gate every rebuild write on complete backup and independent restore evidence

The source inventory is not itself a backup. Before the first Canonical V2 schema, landing,
canonical, publication, or index-rebuild write, a separate accepted S2B checkpoint must cover the
original PostgreSQL volume or restorable database backup, original Milvus bytes, WAL/FPI and salvage
artifacts, and all inventoried historical SQLite/JSONL/XLSX/PDF/cache/raw-source families.

The backup manifest records source and backup identities, sizes, SHA-256 hashes, copy run/time, and
storage location. Copies cannot be hard links to source bytes. Original Postgres remains quiesced;
any volume copy mounts it read-only. Original Milvus is copied byte-for-byte without opening a
client. Canonical V2 consumes only verified backup/restore outputs or immutable landing artifacts,
never original paths.

Hash equality alone is necessary but not sufficient. A second isolated restore target, distinct
from source and backup locations, proves recoverability: PostgreSQL starts from the backup in a
network-none lab and passes database/revision/schema/count probes; Milvus opens only the verified
copy and passes schema/collection/count probes; file families are re-materialized and pass SHA-256
plus bounded format/readability or replay checks. Missing coverage, mismatch, insufficient storage,
or a failed recovery probe blocks all rebuild writes.

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
Temporal precision is retained: a source calendar date remains a date and a known timezone-aware
instant remains an instant. Precision participates in canonical equality, hashes, persistence, and
restart reconstruction. Date-only values are never coerced to UTC midnight; any cross-precision
ordering or overlap uses `explicit-calendar-v1`. The caller must provide an explicit Gregorian
calendar/timezone context; a date becomes a half-open civil-day interval only inside that comparison
operation and is never rewritten. An instant may be before, after, or overlap that interval, but is
never exactly equal to the date. Missing context returns `indeterminate`; ambient/system timezone
defaults are forbidden.

### 3. Resolve identity reversibly and separate identity from source records

Strong identifiers and deterministic composite matches resolve automatically. Ambiguous
cross-format or semantic cases use a structured LLM decision, with human review reserved for
high-impact unresolved cases. Every merge/split retains source identities, evidence, decision run,
and reversal lineage.

Canonical V2 may assign new primary IDs. Historical IDs are source identities and lookup lineage,
not compatibility obligations. All rebuilt cross-domain references use the accepted canonical
identity graph.

Identity construction is exclusively offline: normalization, candidate generation, deterministic
rules, structured LLM adjudication, human review, and merge/split publication occur inside a
versioned `KnowledgeBuild`. `KnowledgeRead` and `KnowledgeAnswer` may resolve aliases, session
referents, and user ambiguity against an accepted identity release, but they are read-only. A
query-time Web/LLM identity hypothesis can support the current answer or create an offline review
gap; it cannot mutate canonical identity or source-identity mappings.

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

Every normal information request runs bounded Web search alongside its applicable local lanes so
current-Web evidence can corroborate, refresh, or supplement local evidence before final LLM
synthesis. Refusal, clarification-only, safety, and UI-control turns do not run general Web search.
Web failure degrades to available local evidence. Search results remain live-Web evidence unless a
later offline gap/recollection run promotes supported assertions through the full build process.

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

### 13. Make list completeness and continuation explicit

Every list plan declares one enumeration mode: `exhaustive_bounded` over a named finite universe,
`required_members` over accepted required entities, or `representative`. Open-world lists default to
`representative`; Top-K or a non-empty result never implies exhaustiveness. The answer carries scope,
as-of, checked/eligible/retrieved/displayed accounting, omissions, unknowns, and continuation state.

Answers may end with a structured `ContinuationOffer` only for broad scope, ambiguity, partial
coverage, evidence gaps, budget exhaustion, or an actually available eligible next hop. It contains
at most three validated operations bound to the current handles/result set/constraints. Blocking
ambiguity uses the same structure as clarification choices instead of producing an unsupported
primary answer.

### 14. Keep Person and Technology internal to the four-domain product

Professor, Company, Paper, and Patent remain the only public inclusion domains. A role-neutral
internal Person identity/projection may connect resolved Professor, Company-personnel, author, and
inventor evidence without forcing unresolved names into one identity. Internal versioned Technology
concepts/routes provide alias, hierarchy, definition, and typed discussion/adoption semantics.
Release-scoped Industry Briefs synthesize local and current-Web evidence but are not canonical facts.

These internal projections are not storage-only conveniences. S8 uses accepted Person projections
for bounded evidence-backed filters such as education, Company role, and geography, and resolves
Technology aliases/routes for typed comparison and representative cross-domain retrieval. S9 renders
scoped/as-of Industry Briefs with evidence and enumeration coverage. The internal surfaces remain
auxiliaries: they add no public inclusion population or independently promoted business domain.

Company capability and Product remain separate canonical surfaces in this change. A product
capability may appear only as an answer-scoped material claim when evidence directly binds the named
product and capability; Company capability or technical plausibility is insufficient.

### 15. Preserve Web-only continuity without creating online identity

A displayed Web-only entity enters session state only through a typed, session-scoped
`WebEntityHandle` bound to bounded content-addressed evidence snapshots, retrieval/provider trace,
claimed domain, display identity, and resolution state. A URL is evidence metadata, not an entity ID.
An unresolved handle may support displayed-set coreference and Web-evidence narrowing but cannot
perform canonical traversal or structured filtering. Later read-only resolution retains handle
lineage and never mutates canonical identity.

### 16. Use lightweight explicit interaction and acceptance policies

Entity ambiguity uses a versioned evidence/confidence/margin gate. One clearly dominant candidate may
be answered with an interpretation notice and switch option; otherwise the turn is clarification-
only. Local safety/compliance questions use a narrow safety-guidance policy rather than ordinary F
refusal: brief lawful risk advice is allowed, while venue allegations, discovery, evasion assistance,
and general Web search are forbidden.

S8 records assessment intent and any explicit user criteria but does not finalize evidence-dependent
dimensions. After retrieval, S9 may select dimensions per turn from the question and returned
evidence, with explicit user criteria taking precedence. A compact structured frame binds each
dimension to evidence, conclusion/insufficiency, and uncertainty; no global policy registry, fixed
weighting, or canonical score is required.

Acceptance uses the versioned customer workbook as case-specific semantic Ground Truth. Each row's
query, answer, and key points are interpreted together; an explicit correction in key points
overrides the incorrect part of historical answer prose. Valid paraphrases are allowed. Newer
official evidence may supplement or supersede a time-sensitive fact only when the answer discloses
the newer as-of/source context. An LLM comparison may assist triage but cannot replace direct user
acceptance or establish truth from model memory.

### 17. Finish through one lean vertical milestone

The remaining work is one product path rather than separate query, answer, review, and evidence
programs. It first builds a serviceable isolated Candidate containing all four public domains and
the relationship paths needed by the customer workbook. It then binds that Candidate to the real
read-only chat runtime and runs the workbook conversations through the same API the user will use.

During development, verification is limited to changed-module tests, one Candidate build smoke, and
approximately eight representative chat cases spanning single-turn, multi-turn, cross-domain,
same-name identity, conditional Web, and insufficient-evidence behavior. The complete 25-turn
workbook replay runs once at the final Candidate milestone. Original-source isolation and release/
index consistency remain mandatory safety checks. Independent slice reviews, blind calibration,
scaled human labels, duplicate aggregate gates, and repeated full-suite runs are not required.

### 18. Preserve recall by lane and let one final LLM judge bounded evidence

The serving path SHALL treat retrieval as candidate generation rather than answer adjudication.
Local and current-Web lanes each receive a bounded share of the final candidate window so one lane
cannot consume the complete global Top-K before semantic answer selection. Identity fusion still
deduplicates entities, but it retains complementary local and current-Web evidence on the fused
candidate.

The existing final prose LLM is the only additional semantic judgment on the request critical path.
It receives a bounded set containing relevant local claims and current-Web snippets, including
source nature, authority, and locator, and decides relevance, comparison, qualification, and answer
organization in one call. Deterministic code continues to own protected constraints, budgets,
evidence-to-claim binding, public-source validation, internal-data redaction, and typed fallback.
This avoids both keyword-specific routing patches and a planner/reranker/sufficiency LLM chain that
would add latency before the user sees an answer.

Current-Web material may support an answer even when it is not eligible for public display. Public
`查看依据` remains fail-closed: a Web URL is displayed only when it is explicitly official or its
hostname is validated against an official URL already retained on the same canonical entity. Search
results, snippets, internal locators, and arbitrary third-party pages never become public citation
links merely because the final LLM used them for relevance judgment.

### S12G — Responsive streamed chat UX

When safe streamable content exists and provider output proceeds normally, S12G publishes at least one
safe answer chunk before the complete synthesis final result and `done`; it does not wait for completion
and then simulate progress. The successful final DOM remains consistent with that same complete result,
including its selected scope and citations. S12G adds no answer truncation, LLM call, query/retrieval
change, or public SSE/schema change.

The server reuses or extends deterministic public-output sanitization so internal identifiers and
structural fields are absent from raw SSE; the browser retains defense-in-depth handling. Focused tests
cover representative beginning, middle, and end cross-chunk boundaries together with ordinary Chinese
and Markdown, without prescribing a private buffering or parsing algorithm.

Existing bounded retry behavior remains available before text becomes public. After publication, a
failure preserves visible text without mixing in another attempt. When the server observes stop,
disconnect, or cancellation before commit, the unfinished turn stays out of successful session and
next-turn context while prior committed context remains unchanged. The contract makes no guarantee for
a client disconnection the server does not observe.

The framework-free page remains usable across the approved 13 viewports, safe areas, software-keyboard
and rotation changes. The message region owns scrolling, detached readers are not forced to the bottom,
IME composition does not submit, and `国先检索助手` retains the approved logo with a readable fallback.
Implementation details such as classes, method names, locks, and chunk-release algorithms remain local
to the implementation and are not part of this design contract.

## Risks / Trade-offs

- **[Risk] The clean-slate scope is large and may stay half-finished.** → Finish one end-to-end
  serving milestone before adding more framework or evaluation machinery.
- **[Risk] A generic assertion layer can become EAV-heavy.** → Keep user/query-facing domain facts
  typed; use generic assertion metadata for provenance and decisions, not as the only query model.
- **[Risk] LLM-assisted fusion may be non-reproducible or wrong.** → Version prompts/models/schemas,
  retain inputs/outputs, validate structured results, use deterministic hard constraints, and route
  high-impact ambiguity to review.
- **[Risk] Soft quality policies may reduce precision.** → Use bounded wide recall, late evidence-
  aware ranking, visible limitations, and independent precision gates rather than early blanket
  exclusion.
- **[Risk] Web augmentation increases false positives, latency, and cost.** → Invoke it only for
  current, missing, stale, or conflicting material evidence; retain bounded budgets and provenance.
- **[Risk] A benchmark-first implementation can overfit or hardcode answers.** → Ingest eligible
  source families and execute normal retrieval/answer paths; workbook prose is never runtime data.
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
- **[Risk] A hash-only copy can still be operationally unrestorable.** → Require a distinct restore
  target and format-appropriate recovery/readability probes for every required source family before
  accepting the backup gate.

## Migration Plan

1. Preserve the Accepted S1-S12A implementation history and immutable review artifacts. Retire the
   Task 2.8 human-review gate and its downstream dependencies without reinterpreting it as passed.
2. Extend the isolated build from its Company-only r12 population to serviceable Professor,
   Company, Paper, Patent, and customer-required relationship projections using inventoried copies
   or approved recollection, never original-source paths.
3. Build matching lookup/vector projections and a content-addressed read-only serving bundle, then
   bind it to the real chat API/UI without changing an active release pointer.
4. Run focused changed-module checks, one build/parity/source-isolation smoke, and approximately
   eight representative chat cases during implementation.
5. Run all 17 workbook conversations/25 turns through the real runtime and produce a human-readable
   query, Ground Truth, actual answer, sources, and limitation comparison report.
6. Let the user evaluate the running system and record the final acceptance decision. Any material
   mismatch becomes a concrete product gap and focused regression case.
7. Request separate explicit authorization before any production-like promotion or cleanup.

Rollback during development discards or deactivates the rejected candidate and restores the prior
accepted release pointers. It never rewrites forensic landing evidence.

## Open Questions

- Exact model/provider choices and per-route call budgets remain configuration decisions subject to
  usable answer latency and bounded cost in the real runtime.
- Physical table names and internal ID format remain implementation choices as long as the typed
  domain, lineage, reversibility, and interface contracts are met.
