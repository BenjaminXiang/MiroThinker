# Verification: followup-subject-consistency

## Status

Candidate as of 2026-08-13. All implementation shipped and deployed (production 18188
serves HEAD `6af3715`; production smoke PASS). This document records the RED/GREEN
evidence references for the backfilled OpenSpec change
`openspec/changes/followup-subject-consistency/`. The SDD per-task reports
(`.superpowers/sdd/2026-08-12-web-answer-subject-consistency-phase2/task-*-report.md`)
are git-ignored scratch — this file references evidence by commit, test name, and
committed file path only.

## RED evidence

### Phase 1 (behavioral RED — production badcase)

- `.agents/runs/followups/2026-08-11-web-lane-subject-consistency.md`: production smoke
  2026-08-11 — turn-2 answers locked onto 南开国际先进研究院（深圳福田） / SIAT fragments
  instead of the anchor; direct provider probes showed Bocha top-5 uniformly off-entity.
  Follow-up context loss on elaboration turns fixed by `27d0231`; gate/correction/
  never-refuse shipped in `50c4f3a`; disclosure in `a9b695b`.

### Phase 2 (per-task TDD RED — failing tests before implementation)

Each plan task wrote failing tests first (plan Steps 1-2; failure modes recorded per task
in the plan). RED test sets per task (all in
`apps/miroflow-agent/tests/canonical_v2/test_knowledge_serving_isolated.py` unless noted):

- Task 1 (`7cad141`): `test_tier_t1_branch_qualified_hit`,
  `test_tier_t2_same_org_unqualified`, `test_tier_t3_other_branch_content`,
  `test_tier_t4_loose_alias_only`, `test_tier_t0_corroborated_trumps_everything`,
  `test_tier_t5_no_match`, `test_company_truncation_stays_full_name_form`,
  `test_anchor_location_qualifier_from_parens_and_query`,
  `test_evidence_branch_qualifiers_excludes_anchor_and_non_locations`
  (T3/T5 fixture strings repaired per the 2026-08-13 amendment).
- Task 2 (`6fda6b6`): `test_gate_drops_loose_alias_and_miss_when_kept_meets_floor`,
  `test_gate_backfills_in_tier_order_below_floor`,
  `test_gate_soft_subject_still_binds_and_qualifier_comes_from_soft_name`,
  `test_gate_without_bound_names_is_passthrough`.
- Task 3 (`9afe730`): `test_mentions_anchor_with_qualifier_requires_branch_cooccurrence`,
  `test_correction_message_mentions_branch_when_qualified` + renderer-level correction
  test in the `test_openai_prose_renderer_corrects_against_soft_subject_over_lookalike`
  shape.
- Task 4 (`2686804`): `test_stream_correction_replaces_final_answer_on_drift`,
  `test_stream_correction_failure_returns_original_streamed_answer`,
  `test_stream_on_anchor_single_call` (the phase-1 "stream makes a single provider call"
  pin was deliberately replaced: single STREAM call plus one bounded non-stream
  correction call — behavior-contract change called out in the commit).
- Task 5 (`fdb3e26`): `test_multi_branch_guidance_injected_with_detected_branches`,
  `test_multi_branch_guidance_absent_without_branch_evidence`,
  `test_multi_branch_guidance_absent_when_user_named_a_city`,
  `test_multi_branch_guidance_chat_request_appends_block_and_bumps_version`.
- Task 6 (`d8b0da5`): `test_authority_views_added_for_org_level_soft_subject`,
  `test_authority_views_absent_when_city_named`,
  `test_authority_views_absent_without_any_anchor`,
  `test_serving_query_views_appends_authority_views_deduped`.
- Task 7 (`377f249`): `test_reference_material_fetched_from_domain_matched_url`,
  `test_reference_material_rejected_by_anti_echo_guard`,
  `test_reference_material_fail_open_on_fetch_error`,
  `test_correction_message_carries_reference_material`.
- Task 10 (`d3c8ff0`, admin-console `tests/test_canonical_v2_chat_http_adapter.py`):
  `test_fresh_turn_org_query_soft_subject_derivation`,
  `test_fresh_turn_qualified_org_query_soft_subject_derivation`,
  `test_continuation_anchor_still_wins_over_derivation`,
  `test_explicit_subject_turn_keeps_topic_switch_directive`,
  `test_question_echo_and_negation_queries_do_not_derive_soft_subject`.
  (Existing tests pinning turn-1 `soft_context_subject is None` were the intentionally
  changed behavior; fixtures updated, called out in the commit.)
- Task 11 (`6af3715`): `test_mentions_anchor_qualified_rejects_lookalike_organized_answer`,
  `test_mentions_anchor_qualified_accepts_lead_with_stem`,
  `test_mentions_anchor_qualified_accepts_framing_opener_with_repeated_stem`,
  `test_mentions_anchor_unqualified_path_unchanged`.

### Phase 2 (behavioral RED — first Task-8 e2e run)

- `evidence/phase2_badcase_t1.sse` .. `phase2_badcase_t3.sse`: badcase session, commits
  `7cad141..377f249` — T1/T2 PASS; T3 first attempt FAIL (SIAT-organized answer passed
  the mention-level check) → Task 11.
- `evidence/phase2_unqualified_t1.sse`: unqualified session FAIL (deterministic 合肥-only
  answer; single plan view; no authority views — fresh turns carried no anchor) → Task 10.
- Verdicts: badcase PASS-with-concerns / unqualified FAIL / control PASS; regressions
  green except the known baseline (`evidence/regression_r1_tail.txt`: 1 failed /
  1134 passed; admin-console 135 passed; chat UI 87/87).

## GREEN evidence

### Per-task unit GREEN

- All RED test sets above pass at their respective commits; per-task regression commands
  (file-level suite + ruff, per plan Steps 4-5) green at each commit. Commit sequence:
  `7cad141` → `6fda6b6` → `9afe730` → `2686804` → `fdb3e26` → `d8b0da5` → `377f249` →
  `d3c8ff0` → `6af3715` (plan amendment `367fd96` interleaved).

### End-to-end GREEN (acceptance oracle — Task-8 re-run, HEAD `6af3715`, port 39878)

- `evidence/phase2_r2_badcase_t1.sse` .. `phase2_r2_badcase_t3.sse`: **3/3 turns PASS,
  first attempt** — answers stay on the 深圳 branch; no SIAT/南开 as subject; no refusal;
  `web_items` tops 切题 (河套/政府/百度百科), 南开 absent; prior SIAT drift did not recur.
- `evidence/phase2_r2_unqualified_t1.sse`: **PASS** — full org-level answer; 合肥 founding
  correctly attributed; natural in-prose city invitation; `plan_done.views` include the
  authority-seeking views (`… 百度百科`, `… 官网`) from turn 1.
- `evidence/phase2_r2_control_t1.sse`, `phase2_r2_control_t2.sse`: **PASS** — no
  regression, normal deepening.
- No retries needed anywhere in the re-run.

### Regression GREEN

- `evidence/regression_r2_tail.txt`: canonical_v2 suite **1 failed, 1138 passed, 149
  skipped** — the single failure is the known baseline
  `tests/canonical_v2/test_consumer_migration_boundary.py::test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers`
  (fails on pre-work HEAD; +4 passed vs the first run from the new Task 11 tests).
- Admin-console suites (`test_canonical_v2_chat_http_adapter.py`,
  `test_chat_anchor_clarification.py`, `test_canonical_v2_referent_history.py`):
  **140 passed**.
- Chat UI node tests (`tests/chat_ui_behavior_test.mjs`): **87 pass / 0 fail**.

### Production smoke GREEN (port 18188, 2026-08-13)

- `evidence/phase2_prod_badcase_t1.sse`, `phase2_prod_badcase_t2.sse`: both turns **PASS**
  first attempt (subject = 推进中心（深圳）; no SIAT/南开; no refusal; `web_items` tops 切题).
- `evidence/phase2_prod_unqualified_t1.sse`: **PASS** first attempt (org-level answer;
  branch attribution; in-prose city invitation; authority-seeking views live on
  production).
- Deploy: production restarted 2026-08-13; serves worktree HEAD `6af3715` via editable
  install; post-deploy `GET /api/health` → `{"status":"ok"}`.

## Final-review fix round (HEAD `45d39dd`, 2026-08-13)

The SDD final branch review (verdict "With fixes") found C1 + I1; both fixed with TDD
(`4c2bf80`, `45d39dd`), scoped re-review **Clean**, deployed. See `tasks.md` §6 for the
mechanisms.

### Fix-round RED → GREEN

- C1: adapter SSE test `http_stream_correction_supersedes…`
  (`apps/admin-console/tests/test_canonical_v2_chat_http_adapter.py`) failed pre-fix
  exactly as production did (streamed drifted draft → `ValueError: prose stream differs
  from its final answer` → SSE `error`, no `answer`/`done`, session rolled back); passes
  post-fix (corrected `answer` event, `["answer","done"]` tail, session committed).
  Closure pin `test_unacknowledged_stream_mismatch_rolls_back_session` amended
  (parametrized: unmarked mismatches still raise + roll back) — intentional contract
  change called out in the `4c2bf80` commit body.
- I1: 普渡 full-name query returned qualifier `深圳` pre-fix (RED: 2 failed); post-fix
  derives none, legit co-occurrence (`…在深圳的布局`) still derives `深圳`, two-city
  queries deterministic across `PYTHONHASHSEED=0,1,2,42`, lexicon members invariant
  under `_normalized_web_identity`.

### Fix-round behavioral evidence

- Retest service (39878): `phase2_fix_pudu_t1.sse` **PASS** (natural 普渡 prose,
  `llm_synthesized`, zero `off-anchor`/`correction` log lines); `phase2_fix_badcase_t1/t2.sse`
  **PASS** (0 hits for `中国科学院深圳先进技术研究院|南开`, streamed == final).
- Drift probes (`phase2_fix_probe1_badcase_t3.sse`, `phase2_fix_probe2_fresh_t1.sse`,
  `phase2_fix_probe3_deepen_t1/t2.sse`): no stream drift on any probe → the C1 stream
  path did not fire; it is covered by the deterministic adapter SSE test above.
- Probe-observed subject substitutions (张天尧/HIT(深圳); 深圳前海微众银行 + truncated
  prose) **reproduced on PRE-FIX production** (`phase2_prefix_prod_probe1_r2_t3.sse`,
  `phase2_prefix_prod_probe3_t2.sse` — the latter byte-identical, md5 `141ee7a1…`) →
  pre-existing deepening-turn anchor-loss class, registered in
  `.agents/runs/followups/2026-08-13-subject-consistency-phase2-residuals.md`.
- C1 caught **live on pre-fix production** during triage: web lane `unavailable`
  14:15-14:17 → T2 streamed off-anchor boilerplate → journal `canonical v2 stream turn
  failed: prose stream differs from its final answer` → SSE `error`
  (`phase2_prefix_prod_probe1_t1/t2.sse`). Post-fix, the same badcase T2 wording serves
  cleanly.

### Fix-round regression

- `evidence/regression_fix_tail.txt`: canonical_v2 suite **1 failed, 1144 passed, 149
  skipped** (same single known-baseline failure; +6 passed from the new fix tests).
- Admin-console 3 suites: **141 passed**; chat UI node tests: **87 pass / 0 fail**.

### Fix-round production smoke (HEAD `45d39dd`, port 18188)

- `phase2_final_prod_badcase_t1/t2.sse`: **PASS** — T2 is the exact wording that crashed
  pre-fix production earlier the same day; 0 substitution hits; journal clean.
- `phase2_final_prod_pudu_t1.sse`: **PASS** — natural 普渡 answer, no correction lines.
- `phase2_final_prod_unqualified_t1.sse`: **PASS** — org-level answer, 合肥 founding
  correctly attributed, multi-region presentation. One observation registered in the
  followups register (professor-record leak into synthesis, explicitly disclaimed by the
  model — same noise family as the anchor-loss class).
- Deploy: systemd auto-respawn ~6 s after TERM (no manual launch, no milvus-lock race);
  health ~87 s; env verified via `/proc/<pid>/environ`.

## Evidence inventory (`.agents/runs/followup-subject-consistency/evidence/`)

| File | Content |
|---|---|
| `phase2_badcase_t1..t3.sse` | First-run badcase session (SSE dumps) |
| `phase2_unqualified_t1.sse` | First-run unqualified session |
| `phase2_r2_badcase_t1..t3.sse` | Re-run badcase session (3/3 PASS) |
| `phase2_r2_unqualified_t1.sse` | Re-run unqualified session (PASS) |
| `phase2_r2_control_t1..t2.sse` | Re-run control session (PASS) |
| `phase2_prod_badcase_t1..t2.sse` | Production smoke badcase (PASS) |
| `phase2_prod_unqualified_t1.sse` | Production smoke unqualified (PASS) |
| `regression_r1_tail.txt` | First-run canonical_v2 tail (1 known-baseline fail / 1134 passed) |
| `regression_r2_tail.txt` | Re-run canonical_v2 tail (1 known-baseline fail / 1138 passed) |
| `phase2_fix_pudu_t1.sse` | Fix-round retest 普渡 control (I1 PASS) |
| `phase2_fix_badcase_t1..t2.sse` | Fix-round retest badcase (PASS) |
| `phase2_fix_probe1_badcase_t3.sse` | Drift probe: T3 anchor loss (followups §1) |
| `phase2_fix_probe2_fresh_t1.sse` | Drift probe: clean on-subject |
| `phase2_fix_probe3_deepen_t1..t2.sse` | Drift probe: T2 anchor loss + truncation (followups §1/§2) |
| `phase2_fix_sse_parse.py` | SSE delta-vs-final comparison parser |
| `phase2_prefix_prod_probe1_t1..t3.sse` | Pre-fix production probe 1, attempt 1 (incl. live C1 crash at T2) |
| `phase2_prefix_prod_probe1_r2_t1..t3.sse` | Pre-fix production probe 1, retry (T3 substitution reproduced) |
| `phase2_prefix_prod_probe3_t1..t2.sse` | Pre-fix production probe 3 (T2 byte-identical reproduction) |
| `phase2_final_prod_badcase_t1..t2.sse` | Fix-round production smoke badcase (PASS, HEAD `45d39dd`) |
| `phase2_final_prod_pudu_t1.sse` | Fix-round production smoke 普渡 (PASS) |
| `phase2_final_prod_unqualified_t1.sse` | Fix-round production smoke unqualified (PASS) |
| `regression_fix_tail.txt` | Fix-round canonical_v2 tail (1 known-baseline fail / 1144 passed) |

36 files, all < 200 KB — committed as-is (no gzip). First-run control SSE dumps were not
preserved (see verification-contract §Honest scope).
