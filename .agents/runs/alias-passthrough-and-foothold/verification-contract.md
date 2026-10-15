# Verification Contract

## Change

- Change ID: `alias-passthrough-and-foothold`
- OpenSpec path: `openspec/changes/alias-passthrough-and-foothold/`
- Run workspace: `.agents/runs/alias-passthrough-and-foothold/`

## Change Type

- `agentic_rag_or_chat_behavior`

## Superpowers Mode

- `eval_first_required`

## RED Artifact

- Type: scenario eval (live asks on scratch) + unit test over the routing
  function
- Path: `.agents/runs/alias-passthrough-and-foothold/red-case.md` (round-47
  verbatim turns) + failing unit cases in `tests/canonical_v2/`
- Expected failing reason: `_has_local_scope_foothold("国先中心（深圳）的详细信息")`
  is `False` → the turn executes Web-only and reports 0 web results as
  "暂未找到", while the pack holds the entity
- Behavior class covered: any pack-known entity asked by a short or
  bracket-reordered name form — not the single visible example

## Oracle Strength

- Observable behavior checked: lane engagement (local lanes fire) and answer
  content against the official-points checklist — not one string match
- Why stronger than a single visible example: the unit RED parameterizes name
  forms over the pack index (short form, bracket reorder, full name); the
  scenario RED carries the verbatim round-47 turns as fixtures
- For LLM/agentic changes, scenario/eval/trace contract: 4-form matrix +
  wrong-entity probes (大湾区 / 合肥) + route A/B on the round-41 concept set

## Diagnosis / Anti-Overfit Check

- Root-cause hypothesis: routing depends on lexical name-shape extractors; a
  pack-known entity in an unrecognized shape holds no foothold → Web-only
- Sibling patterns searched: `_infer_domains`, `_explicit_organization_name`,
  `extract_leading_company_name`, `extract_institution_person_name`,
  `_matched_bound_entity` (the same four round-42 lanes re-checked here)
- Why this RED covers a behavior class: the match is data-driven (pack name /
  alias index), so every entity whose alias form the pack knows is covered
- Why the implementation cannot hardcode: fixtures include non-entity negative
  controls and a second entity from a different domain; the matcher reads the
  pack index, not a case list

## Context / Dependency Surface

- Source OpenSpec requirement(s): this change (round-47 acceptance wording:
  4 forms answer with official points; never 大湾区/合肥; replay 7/7)
- Legacy/source-of-truth docs consulted: `docs/国先中心（深圳）-官方简介.md`,
  migration-log round 47
- Affected modules: `canonical_v2/knowledge_serving_isolated.py` (sealed pack),
  possibly the chat layer for fallback plumbing
- Existing tests/evals likely affected: `test_knowledge_serving_isolated.py`,
  `test_followup_domain_carryover.py`
- Regression surface: routing for concept questions (round-41 class), web-only
  quick answers, enumeration queries
- External dependencies: none (offline decision; web lane unchanged)

## Mock Policy

- Mocks used: unit fixtures construct result sets; no mock of the pack index
- Behavior not mocked away: the real pack index (name/alias accessor) is read
  from the mounted pack in scratch E2E
- Complementary real interaction: live asks on scratch, then 18188 + field

## GREEN Criteria

- The declared RED artifact passes.
- Relevant prior regression tests/evals still pass.
- No test, eval, schema, or guardrail is weakened without an OpenSpec update.
- Implementation generalizes beyond the visible example.
- Source traceability, evidence shape, public APIs, and data contracts remain
  intact unless the OpenSpec change explicitly modifies them.
- Browser/API/state workflow (live ask on scratch + 18188) passes or a blocker
  is recorded.

## Forbidden Shortcuts

- No hardcoded visible input/output cases (no literal `国先中心` branch).
- No test-only production branches.
- No brittle one-case parsing unless the behavior is explicitly specified.
- No mock that removes the behavior under validation.
- No exact-output assertion for open-ended answers; the checklist is
  point-presence, read by a human and quoted verbatim.

## Verification Plan

- RED command: `pytest tests/canonical_v2/ -k foothold` (failing) + scratch live ask
- Focused GREEN command: same
- Regression command: `pytest tests/canonical_v2/test_knowledge_serving_isolated.py test_followup_domain_carryover.py`
- Browser/API/state workflow command: scratch `1829x` live ask ×4 forms, then 18188 + field
- Real interaction / contract / trace command: `replay_fix_round1.py` (7/7) + recall-gate `--diff`
- OpenSpec validation command: `openspec validate alias-passthrough-and-foothold --strict` (or repo equivalent)

## Notes

- Assumptions: the serving layer can reach the pack's name/alias index without
  a rebuild; alias data for the target entity exists in the pack
- Out of scope: data-side alias completeness; answer synthesis policy
- Rollback note: keep the current sealed pack byte-identical before reseal;
  cutover rollback = restore previous pack + command file
