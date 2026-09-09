## ADDED Requirements

### Requirement: The customer workbook is the versioned case-specific Ground Truth

The system SHALL treat `docs/测试集答案.xlsx` as the normative customer benchmark for its 17
conversation groups and 25 query turns. For each row, the query, reference answer, and key points
SHALL be interpreted together. The benchmark defines the expected semantic outcome for that case;
it SHALL NOT be generalized into a product-wide answer template or loaded as runtime knowledge.

#### Scenario: Key points correct historical answer prose
- **WHEN** a workbook row states that part of its historical answer is inaccurate
- **THEN** the key-point correction governs the expected semantic outcome
- **AND** the inaccurate answer fragment is not treated as required Ground Truth

### Requirement: Alignment is semantic rather than wording-based

The actual answer SHALL preserve the benchmark's material identities, relationships, constraints,
and conclusions without requiring sentence-level or lexical imitation. A supported paraphrase or a
different readable structure SHALL be acceptable when it has the same material meaning.

#### Scenario: Actual answer uses a valid paraphrase
- **WHEN** the actual answer expresses the benchmark's material facts with different wording
- **THEN** it is not rejected solely because it differs from the reference prose

### Requirement: Time-sensitive updates retain benchmark context

The workbook SHALL govern facts at its version/as-of context. Newer official evidence MAY add or
supersede a time-sensitive fact only when the answer identifies the newer source/time context and
does not silently portray the benchmark as the current claim. Unsupported model memory SHALL NOT
override either the workbook or retrieved evidence.

#### Scenario: Official source contains a newer fact
- **WHEN** current official evidence postdates and differs from a workbook fact
- **THEN** the answer may present the newer fact with its source and as-of distinction
- **AND** the comparison report records the difference rather than treating it as an unexplained
  benchmark mismatch

### Requirement: Missing evidence remains a product gap

Failure to retrieve evidence supporting a benchmark expectation SHALL remain a visible coverage,
identity, relationship, retrieval, context, or synthesis gap. A case SHALL NOT be removed, excluded,
or declared non-normative merely because the current Candidate cannot answer it.

#### Scenario: Candidate lacks a benchmark entity
- **WHEN** the workbook expects an entity that the Candidate cannot retrieve
- **THEN** the run records a product gap and an honest user-facing limitation
- **AND** the case remains part of the benchmark

### Requirement: The benchmark executes through the real chat path

The final Candidate SHALL execute all 17 workbook conversations and 25 turns through the same chat
API, serving bundle, retrieval, Web, answer, and session path used by the user. Multi-turn groups
SHALL preserve workbook order and conversation state. The resulting report SHALL show the query,
Ground Truth, actual answer, material sources, limitations, and execution status in human-readable
form.

#### Scenario: Workbook follow-up depends on a prior answer
- **WHEN** a workbook turn refers to an entity or displayed set from the preceding turn
- **THEN** replay executes it in the same conversation after its predecessor
- **AND** it is not converted into a context-free single-turn fixture

### Requirement: User acceptance owns the final product decision

Automated checks or LLM comparison MAY identify likely mismatches for triage, but SHALL NOT replace
the user's direct evaluation of the running isolated system. Final acceptance SHALL require the
user's explicit decision after the Candidate and comparison report are available.

#### Scenario: Automated comparison is positive
- **WHEN** all mechanical and advisory comparison checks report success
- **THEN** the system remains a Candidate until the user accepts the real chat experience

### Requirement: Benchmark answers cannot be hardcoded

Production query, retrieval, and answer paths SHALL NOT select behavior by workbook row, benchmark
case ID, or exact benchmark query text, and SHALL NOT read workbook answer/key-point cells at
runtime. The Candidate SHALL answer from admitted local evidence, accepted relationships, and
bounded current-Web evidence invoked for every normal information request.

#### Scenario: User paraphrases a benchmark query
- **WHEN** a user asks the same question with different wording outside benchmark replay
- **THEN** the normal retrieval and answer path produces the response without benchmark-case lookup
