## ADDED Requirements

### Requirement: Every accepted turn has a machine-readable case contract

Each accepted evaluation turn SHALL identify a versioned contract containing applicable
required/forbidden claims, required/forbidden entities, allowed variants, source snapshots, as-of,
enumeration policy, and expected observable stage outcomes. Claim constraints SHALL identify subject,
predicate, object/value constraints, materiality, and evidence obligation where applicable.

#### Scenario: Known-bad prose contains a forbidden Company
- **WHEN** historical reference prose mentions a Company that the reviewed requirement forbids
- **THEN** the case contract records the Company under `forbidden_entities`
- **AND** the prose does not make that Company an accepted expected fact

### Requirement: Reference prose is explanatory rather than normative

The system SHALL use the structured case contract as the normative acceptance oracle. Reference-
answer prose and free-text key points MAY be retained for reviewers and test authors but SHALL NOT
own pass/fail semantics, establish external truth, or require wording imitation. Known-bad responses
SHALL be retained only as negative evidence or historical context.

#### Scenario: Supported answer uses a valid paraphrase
- **WHEN** the answer satisfies the structured claims/entities/evidence contract with different prose
- **THEN** it is not rejected solely for failing to match the reference wording

### Requirement: Dynamic facts are evaluated against frozen evidence context

Every dynamic or current-fact expectation SHALL identify an as-of boundary and content-addressed
source snapshot(s) or an explicit unavailable-evidence outcome. Enumeration cases SHALL identify
their mode, scope/universe or required members, and expected coverage accounting.

#### Scenario: Market fact changes after corpus review
- **WHEN** a later live source differs from the accepted snapshot after the case as-of
- **THEN** replay evaluates the accepted case against its named snapshot/as-of
- **AND** any refreshed case requires a new reviewed contract version

### Requirement: Stage oracles localize failures without coupling implementation order

The system SHALL report applicable stage-oracle outcomes separately. A case MAY define observable
expectations for query understanding/protected slots, candidate recall, fusion/sufficiency, claim-
evidence mapping, rendered answer behavior, and session transition. Stage oracles SHALL validate
public/trace contracts rather than private call order or helper invocations.

#### Scenario: Required entity was recalled but omitted from the answer
- **WHEN** the candidate-stage oracle passes and the rendered required-entity oracle fails
- **THEN** the failure is classified downstream of recall rather than as data coverage

### Requirement: Hard case requirements cannot be averaged away

The system SHALL preserve each hard case outcome independently of aggregate scoring. A required/
forbidden identity, unsupported material claim, false exhaustiveness statement, protected-slot loss,
or invalid session transition SHALL fail its applicable case regardless of aggregate corpus score.
Aggregate metrics MAY measure quality but SHALL NOT mask a failed hard requirement.

#### Scenario: One forbidden entity appears in an otherwise fluent answer
- **WHEN** all soft quality metrics pass but a forbidden identity is rendered
- **THEN** the applicable case fails

### Requirement: LLM judging is evidence-bounded and human-calibrated

The system SHALL bind every LLM-judge decision to the evaluated contract and snapshot identities. An
LLM judge MAY compare semantic variants or evidence entailment only against the structured case
contract and supplied snapshots. It SHALL NOT establish external truth from model memory or reference
prose alone. Scaled LLM judging SHALL require reviewed human-agreement evidence by relevant family.

#### Scenario: Judge remembers a newer financing event
- **WHEN** the event is absent from the accepted case snapshots/as-of
- **THEN** the judge does not require or reward that event as accepted case truth
