# Tasks: deepening-turn-anchor-carryover

## 1. Referent lexicon: carryover predicates

- [x] 1.1 Add `has_anaphoric_subject_reference` (generic referential institution nouns) and `is_subject_carryover_reference` (continuation OR anaphoric OR domain-unconstrained singular referent; never when the query names an explicit subject) to `followup_referents.py`, exported in `__all__`.
- [x] 1.2 RED→GREEN unit truth table in `tests/canonical_v2/test_followup_referents.py`: positives (`这个中心的企业培育情况怎么样`, `该机构有哪些布局`, `它有哪些布局和进展`, `有没有更详细的信息`), negatives (person pronoun `他有哪些论文`, typed markers `该公司的专利`, explicit named subject, expansion `还有哪些`, fresh topic, `其他中心`/`指定中心`).

## 2. Chat-layer carry-over (injection / keep / exemption / binding)

- [x] 2.1 Switch the soft-subject injection leg, the commit keep branch, and the clarification soft-exemption from continuation-only to `is_subject_carryover_reference`; add the anaphoric reference to the clarification gate's first condition.
- [x] 2.2 Treat `has_anaphoric_subject_reference` like the singular-referent branch in `_planning_displayed_ids` (bind active anchor, domain guard unchanged).
- [x] 2.3 RED→GREEN adapter tests: trigger-B wording carries the stored subject into planning and survives commit; bare-`它` trigger-A wording answers about the subject instead of clarifying; anaphoric reference binds a canonical anchor; person pronoun over org soft subject still clarifies; explicit subject still wins.

## 3. Anchor-capture guard at commit

- [x] 3.1 Add `_sanitize_soft_turn_anchor` (drop name-mismatched canonical anchors on soft-anchored turns that planned no canonical ids; containment/≥3-char-overlap match; journal line) and apply it to the committed `context_receipt`.
- [x] 3.2 RED→GREEN adapter tests: leaked canonical anchor (张天尧 vs 推进中心) dropped and not bound by the next referential turn; matching canonical anchor (优必选 ⊂ 优必选科技) kept; web handle kept; turn with planned canonical ids never sanitized.

## 4. View-pin invariant + tripwire marker (serving)

- [x] 4.1 Log the journal marker when the soft-subject protected-slot append re-pins a rewrite view; pin the plan-level invariant with a RED→GREEN test in `tests/canonical_v2/test_knowledge_serving_isolated.py` (rewriter returns subject-dropped views → final views all contain the subject; marker emitted).

## 5. Verification and evidence

- [x] 5.1 Behavioral replay of trigger A (3 turns) and trigger B (2 turns) through the real adapter with scripted web-only evidence; PASS criteria per design; record as the change's behavioral RED→GREEN evidence.
- [x] 5.2 Regression: miroflow-agent `tests/canonical_v2/` suite (known baseline failure excluded), admin-console adapter + referent-history + anchor-clarification suites, chat UI node tests; ruff on touched files.
- [x] 5.3 Update `.agents/runs/deepening-turn-anchor-carryover/verification.md` with RED/GREEN evidence and mark the followup register §1 item as addressed-by-change (register itself stays open until production smoke).
