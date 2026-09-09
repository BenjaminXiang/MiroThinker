# Verification contract: deepening-turn-anchor-carryover

## RED artifact source

- Behavioral RED: the two production-evidenced triggers registered in
  `.agents/runs/followups/2026-08-13-subject-consistency-phase2-residuals.md` §1
  (evidence `phase2_fix_probe1_badcase_t3.sse`, `phase2_fix_probe3_deepen_t2.sse`,
  reproduced pre-fix in `phase2_prefix_prod_*`). The adapter-level replay of those
  sessions (scripted web-only evidence, honest receipts) is the RED baseline: current
  behavior loses the subject on the deepening turn (unpinned planning request, subject
  destroyed at commit, bare `它` clarifying, leaked anchor bound).
- Unit RED: per-task failing tests listed below, written before implementation.

## GREEN definition

Unit GREEN is necessary but NOT sufficient (AGENTS.md §11 — chat behavior). Full GREEN for
the behavior slice requires the adapter-level trigger replays passing the acceptance
criteria (subject carried into planning, no clarification, subject survives commit, leak
not bound) plus the regression oracle green.

## Allowed execution mode

Superpowers-style per-task TDD (RED → GREEN → refactor) inside this contract; no
independent RED/GREEN invention for behavior-affecting legs.

## RED test sets (planned)

- Task 1 (`tests/canonical_v2/test_followup_referents.py`):
  `test_anaphoric_subject_reference_wordings`,
  `test_anaphoric_subject_reference_negatives`,
  `test_subject_carryover_reference_classification`.
- Task 2 (`apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`):
  `test_deepening_reference_carries_soft_subject_into_planning`,
  `test_deepening_reference_keeps_soft_subject_after_commit`,
  `test_bare_pronoun_deepening_answers_about_soft_subject`,
  `test_anaphoric_reference_binds_canonical_anchor`,
  `test_person_pronoun_over_org_soft_subject_still_clarifies`,
  `test_explicit_subject_deepening_does_not_carry_soft_anchor`.
- Task 3 (same file):
  `test_leaked_canonical_anchor_dropped_on_soft_turn`,
  `test_matching_canonical_anchor_kept_on_soft_turn`,
  `test_web_handle_anchor_kept_on_soft_turn`,
  `test_planned_canonical_ids_never_sanitized`.
- Task 4 (`apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py`):
  `test_rewrite_views_repin_soft_subject_and_log_marker`.

## Regression oracle

- `apps/miroflow-agent`: `uv run pytest tests/canonical_v2/` (expect the single known
  pre-existing baseline failure `test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers`).
- `apps/admin-console`: `test_canonical_v2_chat_http_adapter.py`,
  `test_canonical_v2_referent_history.py`, `test_chat_anchor_clarification.py`.
- Chat UI: `tests/chat_ui_behavior_test.mjs` (87/87 baseline).
- `ruff check` on every touched file.

## Out of verification scope

- Production 18188 restart/smoke (user decision after review).
- Register §2 truncation and §3 telemetry items.
