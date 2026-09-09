# Verification Contract

## Change

- Change ID: harden-serving-test-harness
- OpenSpec path: `openspec/changes/harden-serving-test-harness/`
- Run workspace: `.agents/runs/harden-serving-test-harness/`

## Change Type

- `agentic_rag_or_chat_behavior` (acceptance-criteria / instrument side only;
  no serving-path behavior changes)

## Superpowers Mode

- `contract_first`

## RED Artifact

- Type: golden baseline (offline re-scoring of archived result JSONs)
- Path: `.agents/runs/testset-baseline-20260909/results-ds-flash-systemd.json`
  re-scored by the rewritten `run_testset.py --offline`
- Expected failing reason: current keyword-only scoring cannot express
  stance or completeness, so g2-t2 / g2-t3 / g4-t2 pass while their answers
  contradict or incompletely cover the workbook GT.
- Behavior class covered: judgment correctness for the whole workbook turn
  population, not one visible example.

## Oracle Strength

- Observable behavior checked: per-turn pass/fail under three layers
  (entity coverage / stance / completeness ≥80%), plus citation counts.
- Why stronger: the oracle is the curated workbook GT (17 groups / 25
  turns), applied uniformly; a turn can no longer pass on a single keyword.
- For LLM/agentic changes: the runner is the scenario eval; live runs hit
  the real `/api/chat/stream` end to end.

## Diagnosis / Anti-Overfit Check

- Root-cause hypothesis: keyword-only checks are necessary-but-not-
  sufficient conditions; wrong-stance and partial-coverage answers still
  contain the keywords.
- Sibling patterns searched: all 25 turns reviewed for "PASS but wrong"
  (found: g2-t2, g2-t3, g4-t2; GAP-11 lists 5 unanchored turns).
- Why this covers a behavior class: layers are generic (entities / stance /
  completeness), not per-turn string matches.
- Anti-hardcode: anchors live in a curated data module, not in production
  code; production serving code is untouched by this change.

## Context / Dependency Surface

- Source OpenSpec requirement(s): none (instrument change); supports
  `close-workbook-gaps` acceptance.
- Legacy/source-of-truth docs consulted:
  `docs/plans/2026-09-09-testset-baseline-and-repair-plan.md` §九/§十,
  `docs/测试集答案.xlsx`.
- Affected modules: `.agents/runs/testset-baseline-20260909/` harness,
  test configuration in `apps/miroflow-agent` and `apps/admin-console`.
- Existing tests/evals likely affected: replay gate unchanged; pytest
  suites gain environment fixes only.
- Regression surface: none on the serving path.
- External dependencies: live 18188 endpoint for live runs; none for
  offline re-scoring.

## Mock Policy

- Mocks used: none for judgment; offline mode replays archived JSONs.
- Behavior not mocked away: scoring runs against real recorded answers.
- Complementary check: live full-set run after B-stage fixes.

## GREEN Criteria

- Archived re-score: g2-t2, g2-t3, g4-t2 = FAIL; previously-correct turns
  stay PASS.
- Gap registry complete (16/16 with executable assertions, RED recorded).
- All 25 turns anchored.
- Zero environment-class failures in canonical_v2 + admin-console suites.
- No test weakened to pass.

## Forbidden Shortcuts

- No per-turn special-casing that only fixes the three known-bad turns.
- No exact-output assertion for open-ended LLM answers.
- No lowering the completeness threshold below 80% without an OpenSpec
  update.

## Verification Plan

- RED command:
  `python .agents/runs/testset-baseline-20260909/run_testset.py --offline .agents/runs/testset-baseline-20260909/results-ds-flash-systemd.json`
  (before scoring rewrite: flips not possible; after: 3 turns flip to FAIL)
- Focused GREEN command: same command; expect flip table as specified.
- Regression command:
  `cd apps/admin-console && uv run python scripts/replay_fix_round1.py`
  (must stay 7/7)
- Real interaction command: live full-set run
  `python run_testset.py --base-url http://127.0.0.1:18188`
- OpenSpec validation command: `openspec validate harden-serving-test-harness`

## Notes

- Assumptions: workbook GT is the accepted acceptance baseline (user
  decision 2026-09).
- Out of scope: serving-path behavior changes (owned by
  `close-workbook-gaps`); LLM-judge integration (may be added later for
  stance; v1 uses curated stance anchors).
- Rollback note: harness-only; revert the runner commit.
