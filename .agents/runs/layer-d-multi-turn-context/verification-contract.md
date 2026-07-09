# Verification Contract — layer-d-multi-turn-context

> CLAUDE.md §8. Eval-first (multi-turn chat routing/coreference — unit tests alone are NOT
> sufficient GREEN). Behavior contract: `openspec/changes/layer-d-multi-turn-context/`
> (capability `chat-multi-turn-context`). Decision record: ADR-011.

## Change

- **change-id:** `layer-d-multi-turn-context` (OpenSpec; behavior-affecting multi-turn chat
  context: set coreference, routing, traversal, narrowing, anchors).

## Classification

- **Routing rule layer, chip predicates, projection renderers, anchor discipline,
  displayed-set capture:** deterministic → unit/contract tests allowed as RED for those
  units (Superpowers TDD ok), but they do NOT constitute acceptance.
- **End-to-end multi-turn behavior (set coref + traversal + narrowing + clarification +
  classifier referent):** LLM-branched, session-stateful → **eval-first**; the multi-turn
  runner is the oracle.

## RED (to be produced by task group 1 — BEFORE any production-code edit)

- Runner: `apps/admin-console/scripts/eval_multi_turn.py` (session-sticky HTTP replay of
  `turn_group` conversations; fixed `miroflow_chat_session` cookie per group; proxy vars
  unset; backend live).
- Golden set = **14 scorable multi-turn cases**:
  - 8 existing follow-up cases in `test_cases.yaml` (turn_groups 问题1/2/4/5/6/8/17 →
    follow-up qids 2, 4, 5, 8, 10, 12, 15, 25);
  - ~6 synthesized dialogs: R2×O3 traversal (上述教授参与的企业), bare 他们,
    list-then-他 clarification, empty-set/domain-mismatch clarification, 3-turn chain
    (教授→上述教授的企业→这些公司的专利), chip-string routing rows.
- Baseline JSON archived at `.agents/runs/layer-d-multi-turn-context/red-baseline-<date>.json`
  + per-case failure-mode notes. Expected RED shape (from code reading, to be confirmed by
  the run): traversal cases degrade to single-entity or global re-search; 上述-filter cases
  route wrong or filter the wrong set; clarification cases silently guess.

## GREEN

- **≥12/14** multi-turn cases pass on the same runner, full-on env
  (`CHAT_QUERY_CLASSIFIER=on`, `CHAT_LLM_SYNTHESIS=on`).
  - Case mapping (fixture ships 18 scored follow-ups): the **14** = 8 yaml follow-ups
    (qids 2,4,5,8,10,12,15,25) + S1-F, S2-F, S3-F, S4-F, S5-F1, S5-F2. The 4 S6 chip rows
    are NOT in the 14 — they belong to the chip-matrix clause below (must be 4/4).
- **Zero single-turn regression**: `eval_full_testset.py` 19-case set — every case that
  passed at RED time still passes (esp. qid14/17).
- **Chip routing matrix fully green**: every `_suggested_followups` chip string routes to
  its expected path (unit test + eval rows).
- Pass criteria per case type: traversal → answer entities are set-derived (membership
  check against `structured_payload` mapping; no global re-search), coverage statement
  present; narrowing → correct member subset with per-member basis; clarification →
  clarification response (not a guess/global search); chain → turn-3 operates on turn-2's
  displayed set.
- Existing chat unit tests green; `openspec validate --strict` clean.

## Allowed Superpowers mode

- Deterministic units (routing table, predicates, renderers, anchors): TDD.
- Behavior slices: implement → re-run `eval_multi_turn.py` → adversarial no-regression
  check → iterate. Acceptance = the eval line above, decided by Claude review.
- Do not tune thresholds/prompts against the golden set beyond the documented mechanisms
  (no overfitting to case wording).

## Environment invariants

- Backend must be UP; runner is read-only (Milvus single-writer safe — no index refresh).
- `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY; export no_proxy=localhost,127.0.0.1,::1`
  before any localhost HTTP (project memory: proxy hijacks loopback).

## Honest scope (not claimed)

- R3 (constraint re-query 那广东的呢) and R4 (answer-text deixis 第二个是谁) are out of
  scope — runner may record them as unsupported if encountered, never scored.
- qid5-style open predicates depend on member data richness (products/scenarios ingested);
  if the data lacks the fields, the correct answer is 信息缺失-style honesty, and the case
  is scored on honesty + coverage statement, not on magic recall.
- Multi-turn coverage metric inherits the coarse term-overlap oracle from the single-turn
  runner — routing/membership assertions are the strong oracle; coverage is advisory.
