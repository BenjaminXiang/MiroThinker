# F2 verification — commit-union for prose scope (close-workbook-gaps B3)

Locked shape (design.md §B3 / D0.5 phase-1 fix set): the prose commit scope is
the union of the selector-chosen handles and the displayed entities the final
answer text still names. Root evidence: run14 g5-t1 displayed four PCB
suppliers, the selector committed only 嘉立创, and the answer tail still named
深南电路 — under selection-only commit the named member left the session
universe, so turn-2 follow-ups lost it.

## Implementation

- `knowledge_answer.py` `_commit_prose_scope` gains `answer_text: str` (the
  pre-append prose text; `_append_required_sentences` gap sentences never
  widen the union). Call site `_apply_prose_synthesis` passes
  `synthesis.answer_text`.
- Union = selected first, then mentioned-but-unselected displayed members in
  displayed order (deterministic result-set hash). Scan universe =
  `context.displayed_result_set` only — mentions of never-displayed entities
  never join.
- Name forms per handle: full display name + company legal-suffix-stripped
  stem (`有限责任公司/股份有限公司/有限公司/公司`), casefold substring match;
  forms shorter than 2 characters never match. Local helper
  `_prose_mention_name_forms` — `knowledge_read.py` has no reusable
  equivalent (`_without_company_legal_suffix` is private to
  `knowledge_read_isolated.py`, and answer must not depend on the serving
  module).
- Anchor takeover now measures the union: one selected handle that names
  further displayed members is a multi-entity answer and does not re-anchor.
- Empty-selection guard unchanged: union applies only when the selector
  committed at least one handle.

## Tests (tests/canonical_v2/test_knowledge_answer_multiturn_contract.py)

RED (before the fix, at 7a65fb4a): 2 failed / 3 passed —
- FAIL test_prose_commit_unions_displayed_entities_named_in_answer
  (displayed narrowed to the single selected handle)
- FAIL test_prose_commit_union_drives_anchor_takeover (multi-mention answer
  still re-anchored to the single selection)
- PASS the three neutral locks (non-displayed mention ignored, sub-2-char
  stem never matches, empty selection keeps the whole displayed set)

GREEN (after the fix): 5 passed.

Regression with the fix in place:
- multiturn contract file: 18 passed + 1 pre-existing failure
  (`test_off_anchor_correction_exhaustion_falls_back_without_refusal` — fails
  identically at 7a65fb4a without this change; not part of the four
  regression suites)
- implementation_closure: 3 pre-existing failures, identical at HEAD
- suite 1 (serving-isolated + trace-reporting): 291 passed
- suite 2 (pack loader + fast_boot + index projection): 36 passed
- suite 3 (B1 focused relationship-or-patent): 96 passed / 26 skipped
- ruff: 3 pre-existing E402 both sides; format drift hunk counts identical
  to HEAD (answer 3, test 1)
