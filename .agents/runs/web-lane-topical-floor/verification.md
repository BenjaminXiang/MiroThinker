# Verification — web-lane topical floor

Branch `fix/web-lane-topical-floor`, baseline `10dd2bd1`.
Commits: `d0ef568e` (floor + tests) → `b6105337` (guard, superseded by `99e7f479`)
→ `99e7f479` (generic-token rule + empty-lane semantics + test updates).

## Layer ① — tests written in this slice

16 tests in `apps/miroflow-agent/tests/canonical_v2/test_web_lane_topical_floor.py`.
Fixtures: the reported turn's **real** titles/URLs, and its snippets captured
from the run15 pack on 2026-09-15 (`red-case.md` §real snippets) — no
hand-written approximations remain in the RED fixture.

| Test | Locks |
|---|---|
| `test_core_tokens_exclude_location_and_frame_words` | `详细介绍一下 国先中心（深圳）` → `("国先","先中")` (深圳 location, 中心 generic, 介绍… scaffold) |
| `test_core_tokens_fail_open_without_topic` | `介绍一下`, `请问深圳有哪些` → `()` |
| `test_reported_case_drops_diet_camp_page` | gate admits all 3 (H2+H3, the RED fact) → floor drops the sohu camp page and the 11467 page |
| `test_location_only_overlap_is_not_enough` | a page matching only 深圳 is not topical evidence |
| `test_floor_applies_to_refinement_results` | round-2 (榜单/名单) results pass the floor before the merge |
| `test_empty_floor_returns_nothing` | every-off-topic batch ⇒ empty lane (lane, not floor, owns the empty case) |
| `test_bound_entity_page_survives_without_core_token` | full-name identity exemption |
| `test_pinyin_brand_domain_survives_without_literal_overlap` | `深圳市智谱科技有限公司` + zhipuai.com |
| `test_soft_context_subject_identity_is_exempt` | web-only sessions (`soft_context_subject`) |
| `test_enumeration_regression_sample_kept` | `深圳有哪些做机器人的公司` keeps `人形机器人企业盘点` |
| `test_fail_open_without_core_tokens`, `test_fail_open_with_empty_text` | P4 fail-open |
| `test_kill_switch_restores_old_behavior` | `CANONICAL_V2_WEB_TOPICAL_FLOOR=0/false` ⇒ byte-identical old output |
| `test_floor_is_deterministic` | P5 determinism |
| `test_gate_drop_is_recorded_only_when_something_drops` | `record_gate_drop("web_topical_floor", n)`, silent when nothing drops |
| `test_floor_costs_under_five_ms_for_sixty_four_results` | ≤5 ms for 64 results |

Micro-benchmark (200 repetitions, 64 results, this machine):
**median 0.875 ms**, p95 0.895 ms, max 0.979 ms (`_web_query_core_tokens`
0.025 ms). Budget 5 ms.

## Layer ② — pre-existing suites

`cd apps/miroflow-agent && uv run pytest tests/canonical_v2/test_knowledge_serving_isolated.py tests/canonical_v2/test_web_lane_topical_floor.py tests/canonical_v2/test_turn_trace_reporting.py -q`
→ **317 passed, 0 failed**.

`uv run pytest tests/canonical_v2/ -q -k web` (excluding the file above)
→ 51 selected, **50 passed, 1 failed**:
`test_web_page_fetch.py::test_enumeration_lane_fetches_deeper_pages_for_recall`
(asserts 5 page fetches, gets 6). **Pre-existing**: reproduced with this
slice's source change stashed (`git stash push -- …knowledge_serving_isolated.py`
→ same failure), so it is not caused by this change and is left untouched.

Two lane-level tests were updated because they locked the old contract this
slice deliberately changes, and their gate-side coverage is preserved:

- `test_dual_web_lane_drops_off_subject_results_once_floor_is_met` — the
  corroborated off-subject URL now drops (that was H3);
- `test_dual_web_lane_backfills_off_subject_results_to_reach_floor` — the
  backfilled T4/T5 pages now drop (that was H2).
  The gate's own backfill/tier behaviour stays covered by the `_gate(...)`
  fixtures in the same file (`test_gate_backfills_in_tier_order_below_floor`,
  `test_gate_backfill_keeps_every_full_name_hit_above_floor`, …).

## Layer ③ — scratch line (port 18295, run15 pack)

Scratch recipe (all paths outside the production tree):
`/var/tmp/webfloor-295/{pack,index,logs,turn-debug}`, index/bundle/marker
redirected from the sealed run15 artifacts (read-only copies of
`/var/tmp/mirothinker-data-v2/serving-pack-run15-sealed` and `index-v2`),
launcher `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12g/serve-18295-command-run15.sh`.
The production pack was verified byte-identical after the copies
(`cmp pack/milvus.db` OK) and 18188 was never touched.

### Revision 1 (commits `d0ef568e`+`b6105337`): reported query still leaked

`probe_scratch.py --query "详细介绍一下 国先中心（深圳）"` on 18295 returned the
reported sohu page, one item dropped (百步先). Diagnosis with the **real**
provider text captured from the pack:

```
sohu  : "深圳国贸营地简介 深圳国贸营地位于深圳传统商业中心区,紧邻香港特区。…"
         → matches the core token 中心 (from 商业中心区), nothing else
gov   : "国际先进技术应用推进中心（深圳）依托粤港澳大湾区数字经济研究院建设，…"
         → matches 中心 too; the entity appears reordered (名（城市）)
```

That is the design-vs-fact conflict recorded in `design.md`: with the frozen
token set `{国先, 先中, 中心}` the reported page cannot be filtered. Revision 2
drops generic nouns from the core set.

External calls used: bocha ×2, serper ×1 for the diagnosis; the scratch turns
below are additional calls.

### Revision 2 (commit `99e7f479`): final build

Booted 12:15 → healthy 12:25:56 (second boot on the same scratch dirs).

- [x] **reported query** `详细介绍一下 国先中心（深圳）`
  → `web_items: []` — the weight-loss-camp page, the sz.gov.cn round-up and
  the 11467 page are all gone; the answer is unchanged in substance and
  grounded in the local company evidence
  (`.agents/runs/web-lane-topical-floor/scratch/user-case-final.json`, raw SSE
  next to it). No degradation: the turn completed and answered.
- [x] **enumeration** `深圳有哪些做机器人的公司`
  → 8 web items (知乎汇总 / b2bname 排行榜 / 70+ 人形机器人产业链企业一览 /
  21财经 / 职友集名录 …, all containing 机器人), answer lists 20+ named
  companies across humanoid, service, medical and industrial segments — the
  floor did not cost enumeration recall
  (`scratch/enumeration-final.json`).
- [ ] probes verbatim: `字节跳动` answer starts with `字节跳动（ByteDance Ltd.）`;
  `优必选有哪些专利` → ≥30 CN numbers — **not run** (2 h budget)
- [x] **`replay_fix_round1.py --base-url http://127.0.0.1:18295` → RESULT: ALL
  PASS** (G1_framing, G2_bare_name ×3, G3_person_pronoun, G4_patents,
  G5_expansion, G6_anaphoric_opener, G7_enumeration ×3); raw SSE per turn and
  the run report in `.agents/runs/web-lane-topical-floor/replay-18295/`
- [x] `lane_timings.web` for the reported query on the final build: **0.219 s**
  (`/var/tmp/webfloor-295/turn-debug/turn-debug-2Dkl5z-Wju66-01.json`) vs the
  live 18188 baseline 4.159 s — not a like-for-like comparison (the scratch
  turn answered from provider cache and filtered every result), so it is
  reported as "no measurable regression", not as an improvement

External calls consumed by this slice: bocha ×2 + serper ×1 (diagnosis),
6 scratch turns (1 revision-1 probe with 2 view queries, 2 revision-2 probes,
plus replay turns).

## Gaps and follow-ups (explicit)

1. `replay_fix_round1.py` on the final build — the pre-hot-update gate — was
   started but may not have finished inside the 2 h budget; it must be green
   before any hot update.
2. `字节跳动` / `优必选有哪些专利` probes and the `lane_timings.web` comparison
   are not captured for revision 2.
3. Known false drop: the sz.gov.cn round-up for the reported query (see
   design.md §"Design-vs-fact conflict").
4. H1 (unanchored requests) stays unfiltered by decision (same section).

## Scratch teardown

`serve_s12e_port.py 18295` and its `uv run` parent were stopped at 12:32;
`http://127.0.0.1:18188/api/health` still answers 200 and was never sent a
request. Scratch dirs `/var/tmp/webfloor-295/{pack,index,logs,turn-debug}` are
left in place for the record; the production pack was verified byte-identical
after the copies.
