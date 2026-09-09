# Verification Contract Examples

These examples calibrate what a strong verification contract looks like. They are examples only; copy the template from `.agents/runs/verification-contract.template.md` for real changes.

## Deterministic Parser Example

- Change type: `deterministic_module`
- Superpowers mode: `full_tdd_allowed`
- RED: unit test covering a parser behavior class with multiple representative rows.
- Strong oracle: structured parsed fields and rejected malformed rows, not one exact string.
- Mock policy: no mocks.
- GREEN: focused parser test, sibling parser regression, OpenSpec validation.

Use TDD here because the behavior is deterministic and the test can directly observe the contract.

## Agentic RAG / Chat Example

- Change type: `agentic_rag_or_chat_behavior`
- Superpowers mode: `eval_first_required`
- RED: scenario eval or integration test that exercises classification, retrieval, source traceability, and answer shape.
- Strong oracle: route class, retrieved source ids, evidence/citation fields, and persisted/session state.
- Mock policy: provider mocks may be used only if retrieval/session behavior remains real or is covered by a complementary integration check.
- GREEN: scenario eval, focused `/api/chat` tests, relevant prior chat regressions, OpenSpec validation.

Do not accept a single unit test over a classifier string as GREEN evidence for this class.

## Web / Admin UI Example

- Change type: `agent_behavior_or_policy` or nearest behavior type for the feature.
- Superpowers mode: `eval_first_required` or `contract_first`.
- RED: browser workflow or API-state integration test covering the user action and backend state transition.
- Strong oracle: action result, API payload, database state, and visible UI state.
- Mock policy: frontend mocks are allowed for component isolation only when paired with browser/API-state evidence.
- GREEN: backend API test, frontend test/build where relevant, browser walkthrough or Playwright check.

Do not accept DOM existence or snapshot-only tests as sufficient.

## Systemic / Recurring Defect Example

- Change type: `systemic_or_recurring_defect`
- Superpowers mode: `diagnosis_first_required`
- RED: parameterized regression matrix or trace replay that covers sibling cases.
- Strong oracle: invariant holds across the affected class, not only the reported example.
- Mock policy: no mocks for the defect boundary; mocks only for external providers outside the invariant.
- GREEN: reported case, sibling matrix, post-fix sibling search, OpenSpec validation.

Use `pattern-repair` or systematic debugging before any TDD loop.
