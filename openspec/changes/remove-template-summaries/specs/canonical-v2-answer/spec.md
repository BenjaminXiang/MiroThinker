## ADDED Requirements

### Requirement: Fallback summaries are not padded

A rule-based fallback summary MUST NOT append sentences solely to reach a length
target. Short factual text is published as-is.

#### Scenario: Sparse profile

- **WHEN** a professor has only a name, institution and title
- **THEN** the fallback summary contains that sentence only, with no
  `该教授在深圳科创领域有持续贡献` padding

### Requirement: Known padding sentences never reach a claim

Professor claim rendering MUST drop the known padding sentences before
deduplicating and truncating the summary.

#### Scenario: Legacy summary with padding

- **WHEN** a pack summary is `白冠华研究相分离。该教授在深圳科创领域有持续贡献。…`
- **THEN** the claim contains the factual sentence and no padding sentence
- **AND** the rest of the claim (fields, directions, papers) is unchanged
