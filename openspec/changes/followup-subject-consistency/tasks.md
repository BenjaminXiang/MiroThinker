# Tasks: followup-subject-consistency

> Backfill checklist (all implementation shipped and deployed). Phase-1 items are
> pre-checked against their deployed commits; phase-2 items mirror Tasks 1-8/10/11 of
> `docs/superpowers/plans/2026-08-12-web-answer-subject-consistency-phase2.md`
> (amended by `367fd96`). Per-task RED/GREEN evidence:
> `.agents/runs/followup-subject-consistency/verification.md`.

## 0. Verification contract
- [x] 0.1 `.agents/runs/followup-subject-consistency/verification-contract.md` +
      `verification.md` written (this backfill; RED = per-task failing tests + first
      Task-8 e2e run verdicts; GREEN = per-task passing tests + Task-8 re-run 3/3 PASS +
      production smoke PASS).

## 1. Phase 1 — follow-up binding + binary gate + never-refuse (DEPLOYED)
- [x] 1.1 Follow-up continuation semantics (elaboration intent recognition) — `27d0231`.
- [x] 1.2 Web-only soft subject anchor (persist/inject `soft_context_subject`,
      clarification yield, continuation not topic_switch) — `27d0231`.
- [x] 1.3 `retrieval_done.web_items` in the retrieval-process disclosure — `a9b695b`.
- [x] 1.4 Dual-provider corroboration boost + binary subject-consistency gate (FLOOR
      backfill, soft-subject binding) — `50c4f3a`.
- [x] 1.5 Sync-path off-anchor correction retry + never-refuse fallbacks
      (prompt_version v14→v15, refusal rewrite) — `50c4f3a`.
- [x] 1.6 Phase-1 production deploy to 18188 + follow-up record written —
      `.agents/runs/followups/2026-08-11-web-lane-subject-consistency.md`.

## 2. Phase 2 — tiered gate + pinning + guidance + fetch (DEPLOYED)
- [x] 2.1 Task 1: identity-form split + relevance tier classifier (T0–T5) — `7cad141`.
      Tests: `test_tier_t0_corroborated_trumps_everything` … `test_tier_t5_no_match`,
      `test_company_truncation_stays_full_name_form`,
      `test_anchor_location_qualifier_from_parens_and_query`,
      `test_evidence_branch_qualifiers_excludes_anchor_and_non_locations`.
- [x] 2.2 Task 2: three-tier subject-consistency gate (branch/org/wrong-org) — `6fda6b6`.
      Tests: `test_gate_drops_loose_alias_and_miss_when_kept_meets_floor`,
      `test_gate_backfills_in_tier_order_below_floor`,
      `test_gate_soft_subject_still_binds_and_qualifier_comes_from_soft_name`,
      `test_gate_without_bound_names_is_passthrough`.
- [x] 2.3 Task 3: qualifier pinning on the sync answer path — `9afe730`.
      Tests: `test_mentions_anchor_with_qualifier_requires_branch_cooccurrence`,
      `test_correction_message_mentions_branch_when_qualified`, renderer correction
      fixtures (`test_openai_prose_renderer_corrects_against_soft_subject_over_lookalike`
      shape).
- [x] 2.4 Task 4: stream final-answer off-anchor correction (fail-open) — `2686804`.
      Tests: `test_stream_correction_replaces_final_answer_on_drift`,
      `test_stream_correction_failure_returns_original_streamed_answer`,
      `test_stream_correction_provider_error_keeps_streamed_answer`,
      `test_stream_on_anchor_single_call`.
- [x] 2.5 Task 5: prompt-driven multi-branch guidance (prompt_version v16) — `fdb3e26`.
      Tests: `test_multi_branch_guidance_injected_with_detected_branches`,
      `test_multi_branch_guidance_absent_without_branch_evidence`,
      `test_multi_branch_guidance_absent_when_user_named_a_city`,
      `test_multi_branch_guidance_chat_request_appends_block_and_bumps_version`.
- [x] 2.6 Task 6: authority-seeking query views for org-level anchors — `d8b0da5`.
      Tests: `test_authority_views_added_for_org_level_soft_subject`,
      `test_authority_views_absent_when_city_named`,
      `test_authority_views_absent_without_any_anchor`,
      `test_authority_views_use_first_qualifying_anchor`,
      `test_serving_query_views_appends_authority_views_deduped`.
- [x] 2.7 Task 7: correction-triggered tiered fetch with anti-echo guard — `377f249`.
      Tests: `test_reference_material_fetched_from_domain_matched_url`,
      `test_reference_material_rejected_by_anti_echo_guard`,
      `test_reference_material_fail_open_on_fetch_error`,
      `test_correction_message_carries_reference_material`,
      `test_stream_correction_carries_reference_material`.

## 3. Phase 2 amendment — e2e-found defects (user-ruled, DEPLOYED)
- [x] 3.1 Task 10: turn-1 soft-subject derivation at the chat layer — `d3c8ff0`
      (admin-console). Tests: `test_fresh_turn_org_query_soft_subject_derivation`,
      `test_fresh_turn_qualified_org_query_soft_subject_derivation`,
      `test_continuation_anchor_still_wins_over_derivation`,
      `test_explicit_subject_turn_keeps_topic_switch_directive`,
      `test_question_echo_and_negation_queries_do_not_derive_soft_subject`.
- [x] 3.2 Task 11: subject-organization off-anchor check (qualified path) — `6af3715`.
      Tests: `test_mentions_anchor_qualified_rejects_lookalike_organized_answer`,
      `test_mentions_anchor_qualified_accepts_lead_with_stem`,
      `test_mentions_anchor_qualified_accepts_framing_opener_with_repeated_stem`,
      `test_mentions_anchor_unqualified_path_unchanged`.

## 4. End-to-end verification + deploy (plan Task 8)
- [x] 4.1 Local production-replica replay, first run (commits `7cad141..377f249`):
      badcase PASS-with-concerns / unqualified FAIL / control PASS → defects root-caused
      to Tasks 10/11 (plan amendment `367fd96`).
- [x] 4.2 Re-run after Tasks 10/11 (HEAD `6af3715`): 3/3 sessions PASS, first attempt, no
      retries. SSE dumps in `.agents/runs/followup-subject-consistency/evidence/`.
- [x] 4.3 Full regression: canonical_v2 suite green except the known baseline
      `test_s11b_sanctioned_entrypoints_classify_and_exclude_legacy_consumers` (fails on
      HEAD); admin-console suites 140/140; chat UI node tests 87/87. Tails in the
      evidence dir.
- [x] 4.4 Production deploy to 18188 (HEAD `6af3715`) + production smoke: badcase T1/T2
      PASS, unqualified PASS — first attempt. Dumps in the evidence dir.

## 5. This backfill
- [x] 5.1 OpenSpec artifacts (proposal/specs/design/tasks/acceptance) + runs artifacts
      (verification-contract/verification) written.
- [x] 5.2 Evidence files committed under
      `.agents/runs/followup-subject-consistency/evidence/` (15 files, all < 200 KB,
      no gzip needed).
- [x] 5.3 `openspec validate followup-subject-consistency --strict` exits 0.
- [ ] 5.4 Claude review against acceptance; accept / revise / reject.

## Out of scope (recorded, not claimed)
- Official-site fetch injection on the hot path (original R3) — deferred to a later phase.
- Residual e2e risks from the re-run report: single-sample sessions; cold-cache retrieval
  variance can still shift web tops (retest instance shares the production Postgres
  `web_search_cache`, 24 h TTL); the re-run unqualified answer enumerated only the 合肥
  branch (city invitation covered the criterion).
