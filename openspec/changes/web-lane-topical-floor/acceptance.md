# Acceptance: web-lane topical floor

Capability: `canonical-v2-chat` (web lane). Verification evidence:
`.agents/runs/web-lane-topical-floor/verification.md`.

## AC1 — the reported page does not survive the lane

**GIVEN** the reported turn (query `详细介绍一下 国先中心（深圳）`, anchor
`深圳国际先进技术应用推进中心`) and its three web items,
**WHEN** the lane runs the subject gate and then the topical floor,
**THEN** `多彩深圳——减肥达人训练营深圳国贸营地简介` (sohu.com) and
`百步先(深圳)信息技术有限公司` (11467.com) are not in the result, and
`record_gate_drop("web_topical_floor", n)` records the drop.

Evidence: `test_reported_case_drops_diet_camp_page` (fixture = live turn-debug
titles/URLs, reconstructed snippets); scratch run on port 18295 with the run15
pack (real snippets).

## AC2 — no false drop of identity pages

**GIVEN** a page naming the bound entity in full (`…（深圳）…)`, or a page on
the entity's pinyin brand domain,
**WHEN** it shares no core query token,
**THEN** it is kept.

Evidence: `test_bound_entity_page_survives_without_core_token`,
`test_pinyin_brand_domain_survives_without_literal_overlap`,
`test_soft_context_subject_identity_is_exempt`.

## AC3 — location-only overlap is not topical evidence

**GIVEN** a result whose only shared surface form with the query is the
location qualifier (深圳),
**WHEN** the floor runs,
**THEN** it is dropped.

Evidence: `test_location_only_overlap_is_not_enough`.

## AC4 — enumeration queries keep their recall

**GIVEN** `深圳有哪些做机器人的公司` / `深圳有哪些做具身智能的公司`,
**WHEN** the floor runs over listicle results,
**THEN** results sharing 机器/器人/智能 (etc.) survive and the replay suite's
G7 entity requirement is unchanged.

Evidence: `test_enumeration_regression_sample_kept`; scratch replay
`scripts/replay_fix_round1.py --base-url http://127.0.0.1:18295`.

## AC5 — fail-open, kill switch, cost

- no core query token (「介绍一下」) or empty text ⇒ nothing dropped
  (`test_fail_open_without_core_tokens`, `test_fail_open_with_empty_text`);
- `CANONICAL_V2_WEB_TOPICAL_FLOOR=0|false` ⇒ byte-identical old behavior
  (`test_kill_switch_restores_old_behavior`);
- deterministic (`test_floor_is_deterministic`);
- ≤5 ms for 64 results, no model/network
  (`test_floor_costs_under_five_ms_for_sixty_four_results`, measured 0.875 ms
  median);
- the lane is never emptied (`test_empty_floor_keeps_top_ranked_result`).

## AC6 — no regression outside the web lane

**GIVEN** the existing suites,
**WHEN** they run on this branch,
**THEN** the serving/chat suites pass and the pre-hot-update replay gate
(`replay_fix_round1.py`) passes 7/7 against the scratch line.
