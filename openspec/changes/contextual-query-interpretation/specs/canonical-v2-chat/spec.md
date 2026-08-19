## ADDED Requirements

### Requirement: Contextual Query Interpreter

A contextual query interpretation layer SHALL resolve follow-up queries to
their session subjects and intents using an LLM call with a hard 1.5s
timeout, gated by the env `CHAT_CONTEXTUAL_INTERPRETATION` (default off).
When enabled, valid, and passing all deterministic validations, the
interpretation informs the four binding/clarification/expansion decision
points; when absent, timeout, or rejected, the deterministic Phase 3 path
runs unchanged.

#### Scenario: G1-T3 deep follow-up resolves "它" to the session subject

- **WHEN** the session subject is 国际先进技术应用推进中心（深圳） and
  the query is 「它有哪些布局和进展」
- **AND** the interpretation layer is enabled and returns subject_ref with
  confidence >= 0.7 passing all validations
- **THEN** the answer's first sentence contains the resolved subject name

#### Scenario: disabled or timed-out interpretation is transparent

- **WHEN** the env switch is off or the LLM call exceeds 1.5s
- **THEN** the deterministic path produces the same behavior as Phase 3
  (no change in answers, no extra latency beyond the timeout budget)

### Requirement: Deterministic Validation of Interpretations

Every interpretation SHALL pass: ① subject_ref.name hits the session
manifest (anchor/displayed/history/soft); ② explicit-named-subject veto;
③ domain-mismatch rejection; ④ headline-shaped name rejection; ⑤ protected
constraints preserved; ⑥ enumeration turns never single-subject;
⑦ confidence >= 0.7. Any failure → interpretation discarded (None).

#### Scenario: hallucinated subject binding is rejected

- **WHEN** the LLM resolves "他" to a person not in the session manifest
- **THEN** the interpretation is rejected and the deterministic path runs

### Requirement: Interpretation Trace

Interpretation outcomes SHALL be visible in the turn trace:
degradation tokens interpretation-off / interpretation-timeout /
interpretation-rejected; accepted interpretations record the resolved
subject and intent.

#### Scenario: timeout is traceable

- **WHEN** the interpreter exceeds 1.5s
- **THEN** the turn trace carries degradation token interpretation-timeout
