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
similar judgment by stating or making clear the evaluation dimensions, grounding material
supporting points, and labeling the conclusion as a conditional synthesis with relevant uncertainty.
Such conclusions SHALL NOT become objective canonical fields solely because the LLM generated them.

#### Scenario: User asks whether a Professor is a leading expert
- **WHEN** the system answers using career, publication, award, and leadership evidence
- **THEN** it explains the dimensions supporting its assessment
- **AND** it presents the conclusion as an evidence-based judgment rather than an objective stored
  label

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

### Requirement: Suggested followups reflect available eligible relations

Suggested next questions SHALL be generated from validated route/result metadata and relationship
availability for the current entity or displayed set. Suggestions SHALL NOT assert a relationship
that has not been retrieved or shown to be available.

#### Scenario: Professor has no eligible Patent relation
- **WHEN** the current release has no eligible Patent relation for the Professor
- **THEN** the answer does not claim or imply that Patent results are available as a followup

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
