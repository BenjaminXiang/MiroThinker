# Canonical V2 Logical Rebuild — Requirements Grill

## Status

In discovery. This document records user-confirmed product requirements before an OpenSpec
change and implementation plan are written. It does not authorize implementation or cutover.

Every decision in this grill SHALL start from the required user or operator effect and its
acceptance evidence. Technical alternatives such as IDs, schemas, aliases, indexes, and publication
mechanisms MAY then be compared and selected, but only by how well they deliver that effect under
the relevant correctness, continuity, cost, risk, and reversibility constraints. Mechanism-first
questions without an effect comparison are out of scope.

## Source-of-truth order

1. Explicit user decisions in this grill
2. `docs/Data-Agent-Shared-Spec.md`
3. Domain PRDs, with the current Professor requirements audit replacing the legacy Professor PRD
4. Active OpenSpec requirements
5. `docs/测试集答案.xlsx` as seed scenarios, not as a database-content checklist or answer template

## Confirmed north star

Canonical V2 SHALL be a trustworthy, traceable, continuously maintainable knowledge and
retrieval foundation for the Shenzhen innovation ecosystem. It SHALL support factual lookup,
semantic discovery, relationship exploration, and evidence-grounded analysis across the
Professor, Company, Paper, and Patent domains.

The target is organized into six requirement families:

1. **Knowledge coverage** — cover the four PRD domains and their business-required
   relationships, rather than every proper noun appearing in a fixed answer set.
2. **Trustworthy data** — deduplication, identity resolution, field-level provenance, retained
   conflicts, freshness, and quality status.
3. **Retrievability** — exact lookup, semantic retrieval, structured filtering, relationship
   traversal, and cross-domain composition can reach the correct data.
4. **Synthesis fidelity** — answers are grounded in retrieved evidence and distinguish known
   facts, synthesized judgments, and external augmentation.
5. **Continuous operation** — incremental collection, recollection, enrichment, review,
   publishing, full Milvus rebuild, and rollback.
6. **Scenario acceptance** — validate with scenario families, metrics, and an extensible test
   set; the workbook is a seed set, not an answer template.

## Confirmed architecture boundary

- Canonical V2 may redesign internal schemas.
- The system is pre-launch. Existing internal schemas, IDs, APIs, migrations, handlers, retrieval
  flows, admin flows, and tests MAY be replaced or broadly refactored when doing so better serves
  the confirmed product effects.
- All in-repository consumers and tests MAY be migrated together; backward compatibility with
  pre-launch implementation details is not a product requirement.
- PRD behavior, evidence traceability, accepted business semantics, recovery chain of custody, and
  the final acceptance contract remain mandatory even when old code is replaced.
- Compatibility adapters SHOULD exist only when they materially reduce migration risk or preserve
  useful data lineage; they are not a default architectural constraint.
- Production cutover is not authorized by this discovery document.

## Confirmed relationship model

Relationships SHALL be separated into three layers:

1. **Canonical facts** — source-grounded entity relationships with explicit semantics,
   evidence, confidence, and validity state.
2. **Derived relations** — reproducible similarity, ranking, trend, aggregation, and other
   computed relationships that are not asserted as source-grounded truth.
3. **Session relations** — referents, displayed result sets, active constraints, and the
   user's current exploration path.

Relationship exploration SHALL be progressive and multi-turn. A single query is not expected
to exhaustively traverse or explain all available relationships; each answer follows a bounded
path and guides the user toward useful next steps.

## Confirmed Web augmentation scope

- Every information-retrieval request SHALL invoke Web search in parallel with applicable local
  retrieval. This covers A/B/C/D/E/G routes.
- Out-of-scope refusal requests, clarification-only replies, and interface control commands SHALL
  NOT invoke Web search.
- Web is a routine augmentation lane for freshness, corroboration, and coverage, not merely a
  fallback after local failure.
- Invoking Web search does not automatically make every returned claim accepted evidence.
- Provider failure SHALL degrade to the available local result rather than fail the whole request.
- This decision supersedes the older PRD wording that invokes Web only when local results are
  insufficient or the query is explicitly time-sensitive.
- The active `add-web-augment` proposal mentions universal augmentation, but its delta spec still
  contracts only optional absent-entity rescue; the formal OpenSpec must reconcile that drift
  before implementation.

## Confirmed canonical inclusion boundary

- Each domain SHALL apply its own PRD-defined inclusion policy; there is no single blanket
  geographic filter shared by Professor, Company, Paper, and Patent.
- Recovery artifacts, WAL salvage, historical files, Milvus records, and live Web results are
  evidence inputs, not automatically canonical objects.
- An object is promoted from landing/evidence input to Canonical V2 only after identity resolution
  and satisfaction of the target domain's inclusion policy.
- Web evidence that does not qualify for canonical inclusion may still support the current answer
  in the separately provenanced live-Web lane.

## Confirmed path-specific eligibility

- Canonical inclusion and retrieval eligibility are distinct decisions.
- Exact identifier/title lookup and verified relation traversal MAY return an incomplete canonical
  object when the available facts are source-grounded and the response discloses material gaps.
- Semantic recall, recommendation, ranking, and other comparison-sensitive paths SHALL use
  path-appropriate quality signals, ranking, limitations, and index-version checks without
  imposing unnecessary completeness gates.
- Eligibility SHALL be versioned by query path rather than collapsed into a single global `ready`
  boolean or status interpretation.
- Coverage and precision have equal product importance. Missing enrichment, partial summaries, or
  ordinary uncertainty SHOULD trigger lower rank, visible limitations, enrichment, or review—not
  automatic invisibility.
- Hard exclusion SHALL be limited to named invariants such as wrong identity, terminal merge or
  rejection, unsafe exposure, or absence of usable source-grounded facts.

## Confirmed Company inclusion policy

- Approved Company skeleton batches SHALL enter the normalization and identity-resolution flow.
- A newly discovered Shenzhen innovation company MAY also enter Canonical V2 after basic identity,
  geography, business relevance, and source validation.
- A live-Web hit is not automatically promoted merely because it was returned by search.

## Confirmed LLM direction

- LLM usage SHOULD increase for query understanding, entity disambiguation, relevance judgment,
  candidate filtering/reranking, conflict assessment, and final answer organization.
- The LLM's world knowledge is explicitly valuable as a prior for judgment and selection.
- LLM world knowledge MAY inform plausibility, relevance, ambiguity resolution, evidence selection,
  conflict analysis, and synthesis.
- Concrete entity, relationship, capability, role, date, and numeric claims in the final answer
  SHALL be supported by local or current-Web evidence.
- If a useful conclusion cannot be verified, it MAY be included only as an explicitly labeled model
  synthesis or inference and SHALL NOT masquerade as a confirmed fact.
- Model confidence alone is not provenance.

## Confirmed source fusion and conflict handling

- Every source contribution SHALL be retained as a time-bound source assertion rather than
  destructively overwriting earlier evidence.
- Deterministic constraints SHALL first evaluate identity match, source type, publication/event
  time, fetch time, and other field-specific hard facts.
- LLM judgment MAY then compare semantic context, completeness, plausibility, and cross-source
  consistency among the surviving assertions.
- A selected canonical value SHALL retain its supporting assertion(s), selection rationale,
  confidence, and validity time where applicable.
- An unresolved conflict SHALL remain visible as a conflict, support user-safe disclosure when
  material to an answer, and enter review rather than being silently flattened.

## Confirmed identity resolution

- Strong stable identifiers and high-confidence composite signals MAY resolve and merge identities
  automatically.
- LLM judgment SHOULD assist ambiguous semantic and cross-format identity comparisons.
- Human review SHOULD be reserved for high-impact or genuinely ambiguous cases rather than every
  incomplete record.
- A merge SHALL preserve a canonical survivor, all source identities, aliases, supporting evidence,
  decision provenance, and a reversible split path.
- Source records SHALL NOT be destroyed as a side effect of canonical identity resolution.

### Required identity effect

- One real-world object SHALL not appear as multiple independent results merely because sources,
  names, formats, or historical IDs differ.
- Incorrect historical merges and relations SHALL be correctable rather than preserved for
  implementation convenience.
- Cross-domain references within the rebuilt system SHALL resolve to the correct real-world object.
- Pre-launch historical IDs and references SHALL remain traceable as recovery lineage where useful,
  but they do not need to remain the public/internal primary IDs of the rebuilt system.
- Identity corrections SHALL remain auditable.
- ID, alias, and redirect behavior SHALL be selected by comparing how well each option preserves
  identity correctness, future release stability, cross-domain integrity, recovery lineage,
  auditability, and repairability—not pre-launch code compatibility.

## Confirmed temporal semantics

- Every source assertion SHALL record fetch/observation time and SHOULD retain source publication
  or event time when available.
- Naturally time-varying facts such as affiliation, employment/role, organization status, and
  lifecycle SHALL retain validity intervals or equivalent start/end semantics when known.
- Canonical V2 SHALL expose a current projection while preserving historical assertions.
- Full bitemporal modeling is NOT required for every field; time semantics SHALL be added where
  they affect correctness, conflict resolution, freshness, or historical interpretation.

## Confirmed retrieval planning

- Exact identifiers and explicit structured constraints SHALL have deterministic parsing and
  preservation so LLM interpretation cannot silently drop them.
- LLM judgment SHALL interpret intent, semantic constraints, target domains, and bounded relation
  paths, and propose a typed retrieval plan.
- The service SHALL validate the plan's schema, supported operations, and execution bounds before
  executing it.
- Independent SQL/structured, lexical, vector, relation, and Web lanes SHOULD execute concurrently.
- LLM judgment SHOULD participate again after retrieval for evidence-aware filtering and reranking.
- A completely free-form tool loop and a regex-only route system are both outside the target.

## Confirmed recall and late-selection strategy

- Structured/exact, lexical, vector, relation, and Web lanes SHALL each produce bounded but
  recall-oriented candidate sets appropriate to the plan.
- Candidate identities SHALL be resolved/deduplicated and their evidence aggregated before final
  selection.
- Deterministic constraints plus LLM judgment SHALL perform late filtering and reranking.
- Ordinary incompleteness and uncertainty SHOULD affect score, disclosure, and enrichment rather
  than causing broad early exclusion.
- Query rewriting is a required stage before lane execution. The original query and explicit hard
  constraints SHALL remain available and SHALL NOT be silently replaced by a rewrite.

## Confirmed query-rewrite contract

- A turn MAY produce multiple lane-specific rewrites rather than one replacement query.
- Rewrite views SHOULD include resolved conversational context, canonical entity/alias forms,
  semantic or synonym expansion, domain-oriented retrieval expressions, and freshness-oriented
  Web search expressions where relevant.
- Exact identifiers, date/year constraints, geography, negation, requested relation direction,
  and other explicit hard constraints SHALL be protected slots that no rewrite may alter or omit.
- Each retrieved candidate SHALL remain traceable to the original query, rewrite view, retrieval
  lane, and execution attempt that produced it.

## Confirmed bounded reflection and retrieval retry

- After initial fusion, LLM judgment SHALL assess evidence sufficiency against the material parts
  of the current question rather than a result-count heuristic alone.
- Missing material support MAY generate targeted rewrites and a bounded supplemental retrieval
  attempt.
- Retry behavior SHALL be bounded by explicit time, provider-call, and cost budgets; an unbounded
  autonomous tool loop is outside the target.
- If the budget is exhausted with unresolved gaps, the answer SHALL state the material limitation
  instead of filling it with unsupported detail.

## Confirmed answer provenance

- Every material answer claim SHALL have an internal claim-to-evidence mapping.
- Current-Web claims SHALL expose their Web source nature and citation to the user.
- High-confidence local claims MAY use a grouped card/source affordance instead of cluttering every
  sentence, but their internal claim-to-evidence mapping remains mandatory.
- Material conflicts and model-only synthesis/inference SHALL be disclosed at the point where they
  affect the answer.
- An unstructured bibliography at the end is not sufficient provenance by itself.

## Confirmed evidence-based assessment

- Evaluation questions such as technical strength, market competitiveness, maturity, or expert
  standing MAY receive an LLM-synthesized judgment.
- The answer SHALL make the evaluation dimensions explicit and ground each material supporting
  point in retrieved evidence.
- The conclusion SHALL be presented as a conditional synthesis with relevant uncertainty, not as
  an objective canonical field or an unsupported categorical verdict.

## Confirmed progressive answer interaction

- Each turn SHALL answer the current question directly before presenting supporting detail.
- The answer SHALL include material evidence, conflicts, and limitations needed to interpret the
  conclusion, without exhaustively expanding every available relationship.
- Suggested next steps SHALL be generated only from relation paths that are actually available and
  eligible for the current entity or displayed result set.
- The user chooses whether to traverse a suggested path; the system SHALL NOT silently execute the
  next hop.
- Session state SHALL retain the relevant entity, displayed result set, constraints, and traversed
  path for subsequent turns.

## Confirmed versioned publication

- Every collection/recollection run SHALL build a traceable candidate release before affecting the
  active serving version.
- Canonical, published projections, and vector indexes SHALL identify the release/version they were
  built from.
- Promotion SHALL switch an accepted, internally consistent release atomically rather than expose
  a partially updated pipeline.
- The previous accepted release and its verification manifest SHALL remain available for rollback.
- Ordinary completeness/quality gaps SHOULD be reported as soft signals; only named hard invariants
  such as identity corruption, broken references, invalid contracts, or DB/index version mismatch
  SHALL block promotion.
- This discovery does not authorize promotion to the original or production-like database.

## Confirmed Milvus publication strategy

- The Canonical V2 recovery/rebuild SHALL produce a full Milvus build in new versioned
  collections/indexes; it SHALL NOT mutate the original index in place.
- Each index point/chunk SHALL identify its canonical object, canonical release, index policy or
  schema version, and the content version used to produce its embedding.
- Entity, chunk, eligibility, and deterministic manifest/hash parity SHALL be verified before an
  alias or serving pointer can switch to the new index release.
- Routine small updates MAY use versioned incremental refresh; schema changes, embedding-model
  changes, eligibility-policy changes, and scheduled reconciliation SHALL trigger a full rebuild.
- A previous accepted index release SHALL remain available for rollback.
- Milvus is a reproducible index projection, never an independent fact source.

## Confirmed scenario corpus

- `docs/测试集答案.xlsx` SHALL remain a seed scenario source, not the sole acceptance suite or an
  answer-content template.
- PRD-derived scenario families, reviewed real-user badcases, and controlled variations of entity,
  alias, constraint, relation path, and multi-turn expression SHALL extend the corpus.
- Gold expectations SHALL receive human review before they become acceptance or regression truth.
- A frozen regression set SHALL protect accepted behavior; a separately versioned challenge set
  SHALL continue to measure generalization and new gaps.
- LLM generation and judging MAY assist corpus development and qualitative evaluation, but the same
  model's unreviewed generation plus judgment SHALL NOT establish its own gold truth.

## Confirmed acceptance dimensions

- Acceptance SHALL report results by domain and query-path family rather than only an aggregate.
- Coverage/reach, Recall@K, Precision@K, ranking quality, relation traversal, multi-turn context,
  material-claim support, answer completeness, Web provenance, DB/index parity, latency, provider
  calls, and cost SHALL be independently visible where applicable.
- Coverage and precision SHALL each have their own minimum acceptance thresholds and SHALL NOT
  compensate for one another through an average score.
- Named hard invariants such as wrong-identity joins, unsupported material claims, broken
  references, or canonical/index release mismatch SHALL require zero occurrences in the accepted
  validation scope.
- LLM judge scores MAY complement but SHALL NOT replace deterministic retrieval, provenance,
  relation, and parity checks.

## Confirmed threshold calibration

- Existing contractual/PRD minima remain lower bounds, including intent accuracy, Top-K relevance,
  latency, import success, and human-rated summary quality where applicable.
- Missing thresholds for coverage, reach, relation correctness, claim support, and other dimensions
  SHALL be calibrated from a read-only candidate baseline plus reviewed labels and business risk.
- Calibrated thresholds SHALL be written into the formal spec before implementation acceptance and
  then frozen for the change.
- Implementation SHALL NOT lower a threshold, weaken a gold set, or reclassify a hard invariant in
  order to pass.
- Named hard invariants remain zero-tolerance and do not wait for statistical calibration.

## Confirmed A-G semantics

- A-G SHALL remain the product-behavior and evaluation taxonomy for exact lookup, semantic
  narrowing, conversational traversal, panoramic aggregation, knowledge synthesis, refusal, and
  ambiguity handling.
- A-G SHALL guide policy and expected interaction behavior, but SHALL NOT rigidly bind a request to
  one fixed retrieval handler.
- The validated retrieval plan MAY combine supported local and Web lanes while preserving the
  classified behavior semantics and protected user constraints.
- Removing A-G or using it as a brittle single-handler router are both outside the target.

## Confirmed operational feedback loop

- Each domain SHALL retain its PRD-defined scheduled full or incremental collection cadence.
- No-result, insufficient-evidence, repeated Web rescue, missing-relation, user-feedback, and
  benchmark-badcase signals SHALL be recordable as structured knowledge gaps.
- LLM judgment SHOULD assist gap classification, root-cause hypotheses, retrieval formulation, and
  targeted recollection/enrichment task proposals.
- Online live-Web augmentation SHALL NOT write directly into active canonical or Milvus state.
- Gap-driven updates SHALL still pass through landing, identity/fusion, candidate release,
  verification, and promotion.

## Confirmed canonical relationship scope

- Canonical relationships SHALL use an extensible typed catalog rather than a fixed list of the
  three or eight most visible cross-domain paths.
- Required semantic families include identity/lifecycle, organization/role, scholarly output,
  intellectual property, company business/product/event, taxonomy/topic/geography, and
  evidence/lineage relationships.
- Each type SHALL define direction, role semantics, evidence obligations, time semantics where
  applicable, and lifecycle/review state.
- A relationship MAY be added to the catalog without redesigning the whole model, but a free-form
  LLM inference SHALL NOT become a canonical fact without external evidence and fusion.
- Derived similarity/ranking/aggregation and session exploration state remain outside the canonical
  relationship catalog.

## Confirmed structured LLM contracts

- LLM-assisted identity, extraction, fusion, planning, rewriting, reranking, sufficiency, and
  assessment stages SHALL use explicit validated schemas.
- Outputs SHALL identify selected items or assertions, supporting evidence IDs, confidence,
  rationale, and unresolved uncertainty as appropriate to the task.
- Schema validation failure SHALL trigger a bounded retry or a named degradation path; an
  unvalidated free-form object SHALL NOT silently enter canonical state or control execution.
- Model, prompt/schema version, input evidence or release version, and run/decision identity SHALL
  be traceable for material offline and online decisions.
- Free-form prose is reserved for the final user-facing expression after validated claims and
  evidence have been selected.

## Confirmed LLM degradation behavior

- Failure, timeout, or repeated schema-invalid output in one LLM stage SHALL NOT automatically fail
  deterministic exact lookup, structured filtering, or available verified relation traversal.
- The online path MAY return a conservative partial answer with an explicit capability/evidence
  limitation when semantic planning, conflict adjudication, or deep assessment cannot complete.
- Offline identity, fusion, relation extraction, or enrichment work SHALL remain retryable and
  SHALL NOT publish an unvalidated result.
- Silently accepting schema-invalid LLM output is forbidden.

## Confirmed online latency and cost discipline

- Independent local, relation, vector, and Web retrieval lanes SHOULD execute concurrently.
- Compatible LLM judgments SHOULD be batched or consolidated where this does not blur task
  boundaries or evidence traceability.
- Ordinary queries SHALL remain within applicable PRD latency targets; complex cross-domain or
  supplemental-retrieval queries MAY take longer but SHALL expose progress.
- Explicit wall-time, provider-call, retry, and cost budgets SHALL terminate online work with the
  best supported partial answer plus limitations rather than an unbounded search loop.
- Exact p95 and call/cost budgets SHALL be measured in the read-only baseline and frozen in the
  formal spec before implementation acceptance.

## Confirmed recovery landing

- Forensic WAL/FPI salvage, Milvus copies, SQLite/JSONL/XLSX and other historical artifacts, and
  newly collected source responses SHALL enter an immutable content-addressed landing layer.
- Landing records SHALL retain source identity, content hash, acquisition/copy time, parser and
  schema version, and processing lineage sufficient to reproduce downstream outputs.
- Normalized assertions, canonical projections, and indexes MAY be regenerated; landing evidence
  SHALL NOT be overwritten or discarded by downstream processing.
- Recovered or indexed content is evidence input and SHALL NOT become canonical solely because it
  exists in landing.
- The original `pgtest` and original Milvus file remain frozen; recovery work uses isolated copies.

## Remaining specification work

The following are specification/design derivations from confirmed outcomes, not unresolved product
direction questions:

- Derive the complete per-domain field, relationship, inclusion, and path-eligibility catalog from
  the authoritative shared/domain PRDs and active accepted behavior.
- Define source-quality, current-Web fusion, freshness, conflict-disclosure, and claim-citation
  rules that implement the confirmed trust outcomes.
- Compare clean-slate, deep-evolution, and transitional architectures by final effect, delivery
  risk, reversibility, and verification cost; pre-launch compatibility carries no default weight.
- Run the authorized read-only source/candidate baseline and use reviewed labels to freeze missing
  numeric acceptance thresholds.
- Define deterministic canonical/index parity, rollback, and recovery-chain acceptance checks.
- Reconcile the universal-Web directive and other superseding decisions into a strict-valid formal
  OpenSpec before implementation.
