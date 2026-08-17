# Verification: deepening-turn-anchor-carryover

## Status

Candidate — implementation shipped, deployed, and production-probed.
Commits `438300a` (code+tests) + `0e2d247` (change artifacts) on
`codex/canonical-v2-s12a-ready`; deployed 2026-08-17 by TERM + systemd respawn
(`canonical-v2-backend.service`, user unit; health OK ~80 s).

## Production smoke (2026-08-17, port 18188, HEAD `438300a`)

- **Trigger B (register §1 probe3 shape)** — `evidence/prod_deepen_t1/t2.sse`:
  T2 `这个中心的企业培育情况怎么样` → deterministic view pinned with the carried
  subject (`河套数学与…国际先进技术应用推进中心（深圳）揭牌 这个中心的企业培育情况怎么样`),
  answer on-subject with an honest no-detailed-data disclosure; **no 微众银行
  drift, no junk web list** (web lane returned 16 candidates, the subject gate
  filtered them all — aggressive but fail-safe). PASS.
- **Trigger A (register §1 probe1 shape)** — `evidence/prod_pronoun_t1/t2/t3.sse`:
  T3 `它有哪些布局和进展` → views pinned (deterministic view + 百度百科/官网
  authority views fired — both require a carried anchor), answer fully on-subject
  (国先中心 揭牌/具身智能试验场/光源资本 合作, multi-region note), **not 张天尧, no
  off-topic web_items, no clarification, no correction**. PASS.
- Honest notes: on production both deepening turns bound via the web-handle anchor
  path (T1's single on-subject web handle), not the soft-subject injection path —
  anchor binding outranks the soft subject by design, and the adapter tests cover
  the soft path where no anchor exists. Rewrite views stay unpinned on
  anchor-path turns (no soft slot); earliest-view-wins merge keeps the pinned
  deterministic view leading, and the gate filtered the junk they would have
  fetched. The web-lane filter-to-zero behavior deserves a follow-up look
  (register §3 telemetry would have shown the cause directly).

## RED evidence

- Behavioral RED (production, pre-change): the register §1 probes
  `phase2_fix_probe1_badcase_t3.sse` (trigger A: `它有哪些布局和进展` → unpinned views,
  张天尧 answer subject, 10/10 off-topic web) and `phase2_fix_probe3_deepen_t2.sse`
  (trigger B: `这个中心的企业培育情况怎么样` → unpinned views, 微众银行 answer subject,
  8/8 junk web); both reproduced on pre-fix production
  (`phase2_prefix_prod_probe1_r2_t3.sse`, `phase2_prefix_prod_probe3_t2.sse`).
- Adapter RED (this change, before implementation): 5 of the 10 new adapter tests
  failed exactly at the carryover/sanitize assertions —
  `test_deepening_reference_carries_soft_subject_into_planning`,
  `test_deepening_reference_keeps_soft_subject_after_commit`,
  `test_bare_pronoun_deepening_answers_about_soft_subject`,
  `test_anaphoric_reference_binds_canonical_anchor`,
  `test_leaked_canonical_anchor_dropped_on_soft_turn`
  (`5 failed, 5 passed, 118 deselected`). The 5 passing were the guard tests
  (person pronoun clarification, explicit subject, matching/web anchor kept,
  planned-ids untouched) pinning behavior that must not change.
- Predicate RED: `test_anaphoric_subject_reference_*` /
  `test_subject_carryover_reference_classification` failed at collection
  (predicates absent) before `followup_referents.py` gained them.
- Serving RED: `test_rewrite_views_repin_soft_subject_and_log_marker` failed on the
  missing journal marker before the `_serving_query_views` change.

## GREEN evidence

- Predicates: `tests/canonical_v2/test_followup_referents.py` — **146 passed**
  (140 pre-existing + 6 new… count as suite total).
- Adapter: `tests/test_canonical_v2_chat_http_adapter.py` — **128 passed**
  (118 pre-existing + 10 new), including the two trigger replays:
  trigger B (`这个中心的企业培育情况怎么样` carries and keeps the org subject in planning
  and commit) and trigger A (after the badcase pair + a leaked 张天尧 receipt anchor,
  `它有哪些布局和进展` answers about the carried subject with no junk binding).
- Behavioral trigger replays are exactly the adapter tests above (scripted web-only
  evidence, honest and leaked receipts); PASS criteria match acceptance §1/§2.
- Serving: `test_knowledge_serving_isolated.py` view-pin subset — **12 passed**
  including the new invariant (every rewrite view contains the subject; marker logged).
- Admin-console regression: adapter + `test_canonical_v2_referent_history.py` +
  `test_chat_anchor_clarification.py` — **151 passed**.
- Chat UI node tests: **87 pass / 0 fail**.
- Full `tests/canonical_v2/` suite (`--ignore=test_knowledge_build_isolated.py`,
  see Honest scope): **1 failed, 1038 passed, 149 skipped** in 6:05 — the single
  failure is the known pre-existing baseline
  `test_consumer_migration_boundary.py::test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers`
  (documented as failing on pre-work HEAD in the phase-2 verification).
- Ruff: all touched files clean.

## Implementation summary

- `followup_referents.py`: `has_anaphoric_subject_reference`,
  `is_subject_carryover_reference` (+ exports).
- `canonical_v2_chat.py`: carryover legs (injection / commit-keep / clarification
  exemption / anchor binding incl. the `not displayed_ids` early-guard relaxation to
  `not displayed_ids and active_anchor_id is None`), `_subject_names_overlap`,
  `_sanitize_soft_turn_anchor` applied to the committed receipt (journal line on drop).
- `knowledge_serving_isolated.py`: `serving view repin` journal marker when the
  soft-subject protected-slot append restores a dropped subject.

## Honest scope

- The 8/13 register's related observation (disclaimed professor paragraph leaking into
  synthesis text) is reduced by the anchor-capture guard but not eliminated; the
  register item stays open pending production smoke after deploy.
- Full `tests/canonical_v2/` suite: one pre-existing stalled test FILE —
  `test_knowledge_build_isolated.py` — whose heavy tests
  (`test_complete_build_uses_verified_copies…` and at least one neighbor) time out
  (>7 min, standalone) on this machine BOTH with and without this change's diff
  (stash-verified attribution); additionally the build module's only import from a
  changed file is `load_recorded_serving_inputs`, untouched by this diff. The file was
  ignored in the regression run (~106 tests not executed); the suite otherwise runs to
  completion in ~6 minutes. Re-running that file on an idle machine or in CI remains
  outstanding evidence.
