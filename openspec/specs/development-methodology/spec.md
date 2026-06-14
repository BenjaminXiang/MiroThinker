# Development Methodology Specification

## Purpose

Define how this repository combines OpenSpec and Superpowers during development. OpenSpec defines behavior, scope, and verification contracts. Superpowers provides execution discipline within those contracts.

TDD is treated as a local implementation discipline, not a universal best practice for vibe coding. It is valuable when the behavior boundary is deterministic and already specified. It is unsafe as the primary driver for agentic behavior, systemic defects, or broad badcase repair because a narrow red test can be made green by overfitting the visible example.

## Requirements

### Requirement: OpenSpec owns behavior and verification intent

For behavior-affecting work, the active OpenSpec change MUST define the intended behavior, non-behavior, acceptance criteria, and verification intent before production-code edits.

Superpowers MUST NOT independently define product behavior, agent behavior, data contracts, or acceptance criteria.

#### Scenario: Behavior change starts from OpenSpec

- **GIVEN** a task changes user-visible behavior, public API or data contract, Agentic RAG/chat behavior, routing, tool choice, policy, memory behavior, storage semantics, or acceptance criteria
- **WHEN** implementation starts
- **THEN** an OpenSpec change exists and is read first
- **AND** the change defines the behavior and verification intent needed for the implementation

### Requirement: Verification contract selects RED before implementation

Behavior-affecting work MUST create or update `.agents/runs/<change-id>/verification-contract.md` before production-code edits.

The verification contract MUST classify the change, choose the allowed Superpowers mode, name the RED artifact, define GREEN criteria, identify affected behavior/test context, state oracle strength, and list forbidden shortcuts.

#### Scenario: RED is selected before Superpowers TDD

- **GIVEN** an implementation slice will use Superpowers TDD, debugging, or planning
- **WHEN** the slice is behavior-affecting
- **THEN** `.agents/runs/<change-id>/verification-contract.md` selects the RED artifact first
- **AND** Superpowers follows that RED artifact instead of inventing a new one

### Requirement: RED artifacts use strong oracles

A RED artifact MUST validate the behavior class and observable contract, not only a single string, DOM node, snapshot, or visible example.

For user-facing web behavior, GREEN evidence MUST include the relevant deployed/API/browser workflow, state transition, or persisted data check. Static source inspection, terminal-only output, DOM existence, or snapshot-only checks MUST NOT be the sole oracle.

#### Scenario: Web workflow uses browser or API-state oracle

- **GIVEN** a change affects an admin UI, chat surface, or browser-visible workflow
- **WHEN** verification is selected
- **THEN** the verification contract identifies the user workflow and expected state change
- **AND** completion evidence includes browser interaction, API response/state verification, or another end-to-end workflow check beyond DOM existence

#### Scenario: Snapshot-only RED is rejected

- **GIVEN** a proposed RED artifact only checks a snapshot, one rendered node, or one exact string
- **WHEN** the change is behavior-affecting
- **THEN** the verification contract is incomplete
- **AND** implementation is deferred until the oracle checks the underlying behavior class

### Requirement: Deterministic work may use full TDD

Full Superpowers TDD MAY be used only when the verification contract classifies the change as `deterministic_module` or `tool_contract`. The selected RED artifact MUST validate the specified deterministic behavior or tool contract.

Allowed RED artifacts include unit tests and contract tests for parsers, schemas, validators, serializers, storage adapters, tool wrappers, permission checks, state transitions, retrieval filters, and output formatters.

#### Scenario: Parser change uses unit RED

- **GIVEN** a parser behavior is deterministic and specified
- **WHEN** the verification contract classifies the change as `deterministic_module`
- **THEN** a failing unit or contract test MAY be the RED artifact
- **AND** Superpowers TDD MAY execute RED-GREEN-REFACTOR against that artifact

### Requirement: Systemic or ambiguous defects require diagnosis before TDD

When a defect may be systemic, recurring, escaped, cross-domain, or caused by unclear behavior boundaries, implementation MUST start with diagnosis, sibling-pattern search, trace analysis, or eval design before any TDD loop.

TDD MAY be used later for deterministic helper extraction or regression coverage, but it MUST NOT replace root-cause analysis.

#### Scenario: Recurring defect uses debugging and pattern repair first

- **GIVEN** a similar issue has appeared before or the reported symptom may exist in sibling paths
- **WHEN** repair starts
- **THEN** the workflow identifies the defect class and searches for sibling patterns before coding
- **AND** any RED artifact covers the behavior class rather than only the visible example

### Requirement: Shared blind spots require independent context and review

When the same agent proposes tests and implementation, the workflow MUST compensate by grounding the verification contract in OpenSpec requirements, source-of-truth docs, affected dependency/test context, and review criteria before coding.

For non-trivial behavior changes, completion MUST include a review step that checks whether the tests and implementation share the same mistaken assumption.

#### Scenario: Test and implementation share an assumption

- **GIVEN** an agent proposes a test from its own interpretation of the requirement
- **WHEN** the requirement is behavior-affecting
- **THEN** the verification contract cites the OpenSpec requirement or source-of-truth behavior that the test represents
- **AND** review checks whether the test would still pass if the real workflow were broken

### Requirement: Mocking remains bounded by real interaction checks

Tests MAY use mocks for deterministic boundaries, external failures, or speed, but mocks MUST NOT remove the behavior under validation.

Mock-heavy RED artifacts MUST be paired with a contract, integration, trace, browser, or live-adapter check when the behavior depends on cross-component interaction.

#### Scenario: Mock-heavy test is insufficient

- **GIVEN** a proposed RED artifact mocks retrieval, browser state, provider behavior, storage, or tool execution
- **WHEN** the change depends on that interaction
- **THEN** the verification contract identifies the complementary real-interaction check
- **AND** GREEN is not accepted from the mock-only test

### Requirement: Agentic behavior requires eval-first or trace-debug-first RED

Agentic RAG/chat, routing, prompt, memory, tool-choice, policy, and badcase-regression changes MUST NOT treat a single unit test as sufficient proof of behavior.

For these changes, the RED artifact MUST be a scenario eval, trace replay, integration test, policy eval, tool-contract eval, or regression badcase selected by the verification contract.

#### Scenario: Chat-routing change uses scenario RED

- **GIVEN** a change affects Agentic RAG/chat classification, routing, retrieval, fusion, rerank, answer generation, citation behavior, memory, or tool choice
- **WHEN** implementation starts
- **THEN** the RED artifact is an eval, trace, integration, policy, or contract artifact
- **AND** a unit test alone is not accepted as GREEN evidence

#### Scenario: Badcase fix starts from trace debugging

- **GIVEN** a production or dogfood badcase is reported
- **WHEN** the fix changes agent behavior or retrieval behavior
- **THEN** the verification contract marks `badcase_regression` or the nearest matching behavior type
- **AND** the RED artifact reproduces the badcase through a trace, scenario, integration path, or contract eval before implementation

### Requirement: GREEN requires regression and anti-shortcut review

A change MUST be considered GREEN only when the declared RED artifact passes, relevant prior regressions still pass, and no test, eval, schema, evidence check, or guardrail was weakened without an OpenSpec update.

The final self-review MUST check for hardcoded visible examples, test-only production branches, brittle one-case parsing, mocks that remove the behavior under validation, and exact-output assertions for open-ended LLM behavior unless the output is a structured schema.

#### Scenario: Completion rejects unit-only agent behavior proof

- **GIVEN** a change modifies Agentic RAG/chat or agent behavior
- **WHEN** only a unit test was added or updated
- **THEN** the change is not complete
- **AND** completion is blocked until the verification contract's eval, trace, integration, policy, or contract RED passes and relevant regressions are checked

### Requirement: Agent instructions include affected context

Process instructions such as "use TDD" MUST NOT be treated as sufficient context.

Before behavior-affecting implementation, the workflow MUST identify the affected behavior, source requirements, likely touched modules, relevant existing tests/evals, regression surface, and dependency boundaries.

#### Scenario: Context beats generic TDD instruction

- **GIVEN** an implementation request says to use TDD
- **WHEN** the impacted behavior or dependency surface is unclear
- **THEN** implementation pauses to fill the verification contract with affected requirements, tests/evals, and dependency context
- **AND** the agent does not proceed from the process instruction alone

### Requirement: Preferred skills match the defect type

The workflow MUST select skills according to the problem type rather than defaulting to TDD.

For unclear behavior, use brainstorming and OpenSpec exploration. For failures, use systematic debugging. For systemic or repeated defects, use pattern-repair. For implementation from a known contract, use writing-plans and targeted TDD only where allowed. For completion, use verification-before-completion and code review.

#### Scenario: Vibe coding does not default to TDD

- **GIVEN** a task is discovered through exploratory or vibe-coding work
- **WHEN** the behavior boundary is unclear, agentic, or systemic
- **THEN** the selected workflow is explore, debug, pattern repair, eval-first, or review-first as appropriate
- **AND** full TDD is deferred until a deterministic unit or contract boundary exists
