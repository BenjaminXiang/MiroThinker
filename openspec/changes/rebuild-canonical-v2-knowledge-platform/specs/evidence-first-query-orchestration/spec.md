## ADDED Requirements

### Requirement: A-G remains the product behavior taxonomy

The system SHALL classify and evaluate exact lookup, semantic narrowing, conversational traversal,
panoramic aggregation, knowledge synthesis, refusal, and ambiguity under the existing A-G behavior
semantics. A-G SHALL guide interaction policy but SHALL NOT restrict execution to one hard-coded
retrieval handler.

#### Scenario: Cross-domain query needs several lanes
- **WHEN** an A-G-classified query requires structured local facts, a relationship traversal, and
  current Web evidence
- **THEN** the validated plan may execute all required lanes
- **AND** the response still satisfies the classified A-G interaction behavior

### Requirement: Explicit constraints are parsed and protected deterministically

The system SHALL deterministically extract exact identifiers, quoted or explicit names/titles,
dates/years, geography, negation, requested relationship direction, and other supported hard
constraints before LLM planning. No query rewrite or LLM plan SHALL silently alter or omit a
protected constraint.

#### Scenario: Patent number survives rewriting
- **WHEN** a user asks for details of patent `CN117873146A`
- **THEN** every applicable plan/rewrite preserves `CN117873146A` as an exact protected identifier
- **AND** semantic expansion cannot replace it with a merely similar patent

### Requirement: Query rewriting produces traceable lane-specific views

The system SHALL retain the original query and MAY produce validated views for conversational
resolution, canonical names/aliases, semantic expansion, domain retrieval, relationship traversal,
and current Web search. Each view SHALL identify the original query, rewrite kind, protected slots,
and producing model/policy version.

#### Scenario: Follow-up refers to a displayed Company set
- **WHEN** the user asks “which of the above Companies are in Shenzhen” after a displayed Company
  result set
- **THEN** the contextual rewrite binds “the above Companies” to the displayed IDs
- **AND** it preserves the Shenzhen filter and set membership constraint

### Requirement: LLM-assisted retrieval plans are structured and validated

The LLM planner SHALL emit a versioned typed plan containing behavior class, target domains, query
views, structured constraints, relationship paths, retrieval lanes, budgets, and expected material
answer parts. The server SHALL reject unsupported operations, malformed paths, lost protected slots,
or excessive budgets before execution.

#### Scenario: Planner invents an unsupported relationship
- **WHEN** an LLM plan requests an unregistered relationship type or invalid source/target direction
- **THEN** the plan is rejected or repaired within the bounded planning retry
- **AND** the unsupported traversal is not executed

### Requirement: Recall combines exact, structured, lexical, vector, relationship, and Web lanes

For an information-retrieval request, the system SHALL execute all validated independent lanes
concurrently where possible. Each lane SHALL return a bounded recall-oriented candidate set with
query-view, lane, attempt, release, source, and score traceability.

#### Scenario: Topic query has lexical and semantic signals
- **WHEN** a topic query contains a rare exact technical phrase and broader semantic intent
- **THEN** the plan may combine lexical and vector candidates
- **AND** exact lexical coverage is not discarded merely because its vector rank is lower

### Requirement: Web augmentation runs for every information-retrieval request

All A/B/C/D/E/G information-retrieval requests SHALL invoke current Web search as an augmentation
lane regardless of local result count. Out-of-scope refusal, clarification-only input, and interface
control input SHALL NOT invoke Web search.

#### Scenario: Exact local object is found
- **WHEN** an information-retrieval request exactly resolves a high-confidence local object
- **THEN** current Web search still runs within the route budget for freshness and corroboration
- **AND** local and Web evidence remain distinguishable during fusion and answer generation

#### Scenario: Refusal request is out of scope
- **WHEN** a request is classified as an ordinary out-of-scope refusal
- **THEN** the system returns the refusal behavior without calling Web search

### Requirement: Web failure degrades without losing local evidence

Web provider failure, timeout, or invalid output SHALL NOT remove or invalidate usable local
evidence. The trace SHALL record the unavailable lane, and the answer SHALL disclose a freshness or
coverage limitation when material.

#### Scenario: Web times out after local retrieval succeeds
- **WHEN** current Web search exceeds its route budget and local evidence is usable
- **THEN** the system proceeds with the supported local evidence
- **AND** it does not present the result as current-Web-verified

### Requirement: Candidate fusion is identity-aware and selection happens late

The system SHALL resolve/deduplicate candidate identities and aggregate their evidence before final
filtering/reranking. Ordinary quality gaps SHALL affect ranking or limitations rather than broad
early exclusion. Deterministic constraints and schema-validated LLM judgment SHALL perform final
evidence-aware selection.

#### Scenario: Local and Web candidates name the same Company
- **WHEN** local and current-Web lanes return the same real-world Company under different names
- **THEN** fusion presents one candidate identity with both evidence lanes
- **AND** it does not consume two result positions as unrelated Companies

### Requirement: Evidence sufficiency is assessed against material question parts

After initial fusion, a structured LLM decision SHALL identify which material question parts are
supported, conflicting, or missing. A non-empty candidate list SHALL NOT by itself mean the evidence
is sufficient.

#### Scenario: Company exists but requested product capability is unsupported
- **WHEN** retrieval finds the requested Company but no evidence for the requested product capability
- **THEN** sufficiency marks that material part as missing
- **AND** the answer cannot infer the capability merely from the Company's general business

### Requirement: Supplemental retrieval is targeted and bounded

The system SHALL permit a material evidence gap to trigger targeted query views and one or more
supplemental lanes only within explicit wall-time, provider-call, retry, and cost budgets. Budget
exhaustion SHALL return the best supported result and unresolved limitations; execution SHALL NOT
loop indefinitely.

#### Scenario: Targeted Web query still cannot verify a claim
- **WHEN** supplemental retrieval exhausts its route budget without supporting the missing claim
- **THEN** the final evidence set marks the claim unsupported
- **AND** the answer omits it or states the limitation rather than inventing detail

### Requirement: Query execution remains traceable across attempts

The final evidence set SHALL retain the original query, session referents, protected constraints,
plan version, each rewrite, each lane/attempt, provider/model versions, candidate decisions, and
release IDs needed to reproduce or diagnose the answer.

#### Scenario: Benchmark case fails after a model change
- **WHEN** a previously accepted query fails after a planner or reranker model update
- **THEN** its trace identifies the changed model/version and affected decisions
- **AND** the failure can be classified without guessing which query path ran
