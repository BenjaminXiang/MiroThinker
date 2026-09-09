# Verification Contract

## Change

- Change ID:
- OpenSpec path: `openspec/changes/<change-id>/`
- Run workspace: `.agents/runs/<change-id>/`

## Change Type

Choose one and delete the rest:

- `deterministic_module`
- `tool_contract`
- `data_contract_or_storage`
- `agentic_rag_or_chat_behavior`
- `agent_behavior_or_policy`
- `systemic_or_recurring_defect`
- `badcase_regression`
- `refactor_behavior_preserving`

## Superpowers Mode

Choose one and delete the rest:

- `full_tdd_allowed`
- `contract_first`
- `eval_first_required`
- `trace_debug_required`
- `diagnosis_first_required`
- `baseline_required`

## RED Artifact

Name the artifact before production-code edits:

- Type: unit test | contract test | integration test | scenario eval | trace replay | policy eval | golden baseline
- Path:
- Expected failing reason:
- Behavior class covered:

## Oracle Strength

- Observable behavior checked:
- Why this is stronger than a single string, DOM node, snapshot, or visible example:
- For web/UI changes, browser/API/state workflow to verify:
- For LLM/agentic changes, scenario/eval/trace contract to verify:

## Diagnosis / Anti-Overfit Check

- Root-cause hypothesis:
- Sibling patterns searched:
- Why this RED covers a behavior class rather than one visible example:
- Why the implementation cannot pass by hardcoding or bypassing the case:

## Context / Dependency Surface

- Source OpenSpec requirement(s):
- Legacy/source-of-truth docs consulted:
- Affected modules:
- Existing tests/evals likely affected:
- Regression surface:
- External/provider/browser/storage dependencies:

## Mock Policy

- Mocks used:
- Behavior not mocked away:
- Complementary real interaction / contract / trace / browser check:

## GREEN Criteria

- The declared RED artifact passes.
- Relevant prior regression tests/evals still pass.
- No test, eval, schema, or guardrail is weakened without an OpenSpec update.
- Implementation generalizes beyond the visible example.
- Source traceability, evidence shape, public APIs, and data contracts remain intact unless the OpenSpec change explicitly modifies them.
- For web/UI behavior, the relevant browser/API/state workflow passes or a blocker is recorded.
- For mock-heavy tests, the complementary real-interaction check passes or a blocker is recorded.

## Forbidden Shortcuts

- No hardcoded visible input/output cases.
- No test-only production branches.
- No brittle one-case parsing unless the behavior is explicitly specified.
- No mock that removes the behavior under validation.
- No exact-output assertion for open-ended LLM behavior unless the output is a structured schema.

## Verification Plan

- RED command:
- Focused GREEN command:
- Regression command:
- Browser/API/state workflow command:
- Real interaction / contract / trace command:
- OpenSpec validation command:

## Notes

- Assumptions:
- Out of scope:
- Rollback note:
