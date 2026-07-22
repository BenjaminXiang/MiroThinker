## ADDED Requirements

### Requirement: Every material answer claim maps to evidence

Before rendering, the system SHALL construct a validated map from every material identity,
relationship, capability, role, date, numeric, or consequential conclusion claim to one or more
local or current-Web evidence items. An unstructured bibliography alone SHALL NOT satisfy this
requirement.

#### Scenario: Answer states a Professor founded a Company
- **WHEN** the answer asserts a founder relationship
- **THEN** the claim-evidence map identifies the supporting relationship evidence
- **AND** the answer does not rely only on model memory or an unrelated profile summary

### Requirement: Product capability claims require direct Product binding

A Product capability claim SHALL remain answer-scoped and SHALL map to evidence that directly binds
the named Product and capability. Company-level capability, another Product, a Technology route, or
model feasibility SHALL NOT support the claim. Missing status evidence SHALL be disclosed rather than
silently treating claimed, demonstrated, and commercially available behavior as equivalent.

#### Scenario: Requested Product feature is not directly evidenced
- **WHEN** only general Company capability evidence is available
- **THEN** the answer marks the Product capability unsupported or qualified
- **AND** it does not create or imply a canonical Product-capability relationship

### Requirement: LLM world knowledge guides judgment but is not provenance

The system SHALL permit LLM world knowledge to guide query interpretation, ambiguity resolution,
relevance, plausibility, comparison, evidence selection, and language without treating it as
provenance. A material factual claim SHALL require local or current-Web evidence. An unverified
useful conclusion SHALL be labeled as model synthesis or inference and SHALL NOT be presented as a
confirmed fact.

#### Scenario: Model remembers a recent Company event
- **WHEN** the model recalls a recent financing event that is absent from retrieved evidence
- **THEN** it cannot present the event as confirmed
- **AND** it may only omit it or identify it as unverified synthesis within the accepted answer
  policy

### Requirement: Source lane and conflicts are disclosed proportionally

Current-Web claims SHALL expose Web source nature and citation. High-confidence local claims MAY use
grouped card/source affordances while retaining internal claim-level mapping. Material source
conflicts and model-only inference SHALL be disclosed at the affected claim.

#### Scenario: Local and Web evidence disagree on a current role
- **WHEN** the disagreement changes the answer to the user's question
- **THEN** the answer identifies the conflict and cites the relevant evidence lanes
- **AND** it does not silently choose a value without the recorded fusion decision

### Requirement: Evaluation questions use evidence-based assessment

The system SHALL answer questions about strength, competitiveness, maturity, expert standing, or
similar judgment through a compact per-turn assessment frame. Explicit user criteria SHALL take
precedence; otherwise the LLM MAY select a small relevant dimension set from the question and
evidence. Each material dimension SHALL identify supporting evidence, a conclusion or
`insufficient_evidence`, and uncertainty. No global dimension registry, fixed weighting, or numeric
score is required. Such conclusions SHALL remain conditional synthesis and SHALL NOT become objective
canonical fields solely because the LLM generated them.

#### Scenario: User asks whether a Professor is a leading expert
- **WHEN** the system answers using career, publication, award, and leadership evidence
- **THEN** it explains the dimensions supporting its assessment
- **AND** it presents the conclusion as an evidence-based judgment rather than an objective stored
  label

### Requirement: Industry briefs are scoped derived answers

The system SHALL generate an Industry Brief that compares Technology routes or maps representative
Companies, Products, Papers, or Patents as a release-scoped answer over accepted internal Technology
reference knowledge plus cited current-Web evidence where used. It SHALL expose scope, as-of,
enumeration mode/coverage, route definitions, relationship semantics, material evidence, conflicts,
and limitations. Brief prose and conclusions SHALL remain derived output and SHALL NOT be written as
canonical Technology, Company, Product, Paper, or Patent facts.

#### Scenario: Route landscape brief mixes local and current-Web evidence
- **WHEN** a user asks for a current comparison of two routes and representative Shenzhen Companies
- **THEN** the answer distinguishes accepted local route/adoption evidence from current-Web evidence,
  states scope/as-of and representative coverage, and cites each material conclusion
- **AND** the synthesized brief is not persisted as a canonical fact or used to infer unsupported
  Product capability

### Requirement: List answers expose enumeration coverage

A list answer SHALL state its enumeration mode, scope, as-of, and evidence-backed accounting for
checked/eligible/retrieved/displayed members, omissions, unknowns, and continuation where applicable.
It SHALL NOT claim exhaustive coverage unless the plan used `exhaustive_bounded` and accounted for the
named finite universe. Required-member omissions SHALL be explicit per member.

#### Scenario: Open-world supplier landscape returns ten results
- **WHEN** the plan used `representative`
- **THEN** the answer labels the list representative and explains material omissions/unknown scope
- **AND** it does not present ten displayed suppliers as every supplier in the market

### Requirement: Answers use progressive disclosure

Each answer SHALL address the current question first, include the evidence and limitations needed to
interpret it, and avoid exhaustively expanding unrelated facts or relationship paths.

#### Scenario: User asks for a Company's patents
- **WHEN** the system returns the directly related Patent result set
- **THEN** it does not also automatically expand every inventor, Professor, Paper, product, and
  financing relationship in the same answer

### Requirement: Relationship exploration is user-directed and multi-turn

Each relationship turn SHALL follow a bounded typed path from a resolved entity or displayed result
set. The system SHALL retain referents, displayed IDs, active constraints, and traversed path in
session state. It SHALL execute another path only after the user requests or selects it.

#### Scenario: User follows Professor to Papers then Companies
- **WHEN** successive turns request a Professor's Papers and then Companies associated with the
  displayed result context
- **THEN** each turn uses the correct prior referent/result set and typed path
- **AND** the system does not silently substitute a retrieved-but-undisplayed candidate

### Requirement: Session state preserves typed Web entity handles

The system SHALL preserve handle type, evidence snapshot identity, resolution state, and display order
for displayed result sets containing accepted Canonical IDs or evidence-bound Web entity handles. It
SHALL validate each follow-up operation against the bound handle type and resolution state. An
unresolved Web handle MAY support coreference and evidence-based narrowing but SHALL NOT silently
become a canonical anchor or execute canonical relationship traversal.

#### Scenario: User refers to a displayed Web-only Company
- **WHEN** the user asks a follow-up about “the above Company”
- **THEN** the turn binds the Web entity handle and its retained evidence
- **AND** unsupported canonical traversal returns a limitation or read-only resolution path

### Requirement: Suggested followups reflect available eligible relations

Suggested next questions SHALL be generated from validated route/result metadata and relationship
availability for the current entity or displayed set. Suggestions SHALL NOT assert a relationship
that has not been retrieved or shown to be available.

#### Scenario: Professor has no eligible Patent relation
- **WHEN** the current release has no eligible Patent relation for the Professor
- **THEN** the answer does not claim or imply that Patent results are available as a followup

### Requirement: Continuation offers are conditional, structured, and executable

The answer SHALL include an optional ending `ContinuationOffer` only for broad scope, ambiguity,
partial coverage, evidence gaps, budget exhaustion, or an actually available eligible next hop. The
offer SHALL contain at most three validated options bound to current handles/result sets/constraints
and SHALL introduce no unsupported factual claim. A complete simple answer without a valid trigger
SHALL omit it. Blocking ambiguity SHALL render the offer as clarification choices instead of first
producing an unsupported primary answer.

#### Scenario: Representative landscape has several useful next steps
- **WHEN** the current answer is intentionally representative and has valid region and route filters
- **THEN** the ending offer may present up to three executable narrowing/continuation options
- **AND** selecting an option binds the next turn to the recorded result set and operation

### Requirement: Non-blocking ambiguity remains explicit and switchable

When one entity candidate clears the accepted ambiguity gate, the rendered answer SHALL identify the
interpretation used. If another viable candidate remains, the answer SHALL expose it only through a
validated bounded switch option. When no candidate clears the gate, the turn SHALL render
clarification choices without an unsupported primary answer.

#### Scenario: Dominant same-name candidate is answered
- **WHEN** the query result identifies exactly one dominant candidate and one viable alternative
- **THEN** the answer names the interpreted candidate and offers a validated switch to the viable
  alternative
- **AND** it does not present the interpretation as if no ambiguity existed

### Requirement: Safety guidance is conservative and bounded

A safety-guidance answer SHALL be brief, polite, and limited to lawful risk avoidance and official
help/reporting direction. It SHALL NOT identify/speculate about illegal venues, repeat unsupported
allegations, facilitate discovery/evasion, or expand into unrelated lifestyle assistance. Current
official claims SHALL map to bounded official-source snapshots when such a lookup was explicitly
requested.

#### Scenario: Local safety reminder needs no current official lookup
- **WHEN** conservative static guidance is sufficient
- **THEN** the answer provides that guidance without general Web search
- **AND** it does not name suspected venues or districts

### Requirement: Intermediate LLM decisions are structured and traceable

The system SHALL require LLM outputs that affect identity, evidence selection, assessment, claim
construction, citation, or followups to conform to versioned schemas and identify evidence IDs,
confidence, rationale, and uncertainty as applicable. Model, prompt/schema, input release, and
decision run SHALL be traceable.

#### Scenario: Claim-selection output is schema-invalid
- **WHEN** the claim-selection LLM repeatedly returns output that fails schema validation
- **THEN** the invalid claims are not rendered or written
- **AND** the module follows its named conservative degradation path

### Requirement: LLM failure degrades by stage

Failure of an LLM planning, reranking, conflict, assessment, or prose stage SHALL NOT automatically
erase deterministic exact/structured/relationship results. The system SHALL return a conservative
partial result or typed error with a visible limitation according to the failed stage. Offline
LLM-dependent mutations SHALL remain unpublished and retryable.

#### Scenario: Prose synthesis fails after claims are validated
- **WHEN** validated claims and evidence exist but final prose synthesis fails
- **THEN** the system returns a deterministic structured or templated answer from those claims
- **AND** it does not fabricate prose or lose the evidence trace

### Requirement: Online work obeys explicit budgets and progress behavior

Web, LLM, and supplemental retrieval SHALL obey route-specific wall-time, provider-call, retry, and
cost budgets. Complex cross-domain or supplemental work SHALL expose progress. Budget exhaustion
SHALL return the best supported partial answer and limitation instead of an unbounded wait.

#### Scenario: Complex cross-domain query reaches its budget
- **WHEN** some material parts are supported and another supplemental lane remains incomplete at
  budget exhaustion
- **THEN** the answer returns the supported parts, names the limitation, and stops further calls
