# Verification — 1b.1a/1b.1b (G7 enumeration recall + fallback coverage), 2026-09-13

Serving worktree `codex/canonical-v2-s12a-ready` (uncommitted). Offline
probe + rank tables: this runs dir. Live replay evidence: serving worktree
`.agents/runs/retrieval-v2-derived-index-and-fusion/replay-{g7-family,
full-g7fix,full-g7fix-r2}-20260913/`.

## Baseline (before the slice)

- Offline F1 rank for 优必选, query 深圳有哪些做具身智能的公司 + planner
  view variants (`g7-f1-rank-baseline-20260913.json`): 926/3037 on the
  primary view; the marker-less views 深圳 具身智能 公司 / 深圳 人形机器人
  企业 returned **0 candidates** (no trigger); the 人形机器人 view (when
  triggered) ranked 优必选 24.
- Archive of 26 live enumeration turns: recall 6/26 (rank ~37), commit
  0/26; today's 3 runs recall 0/3; the occasional passes were web-prose
  mentions with 0 优必选 citations.

## Fix

1. `_category_query_terms` (knowledge_read_isolated): declared-category-term
   trigger extension (marker-less view variants fire the F1 fallback).
2. `anchoring-declaration-v1.json`: family under the extracted head 具身 —
   members 智能机器人(2) / 人形机器人(2) / 人形(1) (PCB precedent shape).
3. `_degraded_fallback_text(result, request=...)` (knowledge_answer): the
   deterministic fallback appends the AQ-S2c member coverage sentence at
   all four call sites.

## Evidence

### Offline (after)

`g7-f1-rank-after-family-20260913.json` vs baseline:

| view | 优必选 | 乐聚 | notes |
|---|---|---|---|
| 深圳有哪些做具身智能的公司 | 926 → **15** | 264 → **3** | top64 ✓ |
| 深圳 具身智能 公司 | 0 → **15** | 0 → **3** | trigger fixed |
| 深圳 人形机器人 企业 | 0 → **24** | 0 → **5** | trigger fixed |
| 深圳 具身智能 厂商 产业链 | 933 → **15** | 273 → **3** | top64 ✓ |
| 深圳有哪些做人形机器人的公司 | 24 = 24 | 5 = 5 | family inert ✓ |

Residual: 越疆 ~800 (tech_tag 智能机械臂解决方案提供商 — build-side
vocabulary case, C1 rebuild decision); 众擎/智平方/自变量/星尘 inside the
128 window but outside the 64 cut (fusion window still admits them).

### Unit

- `test_knowledge_read_isolated.py`: 3 new tests (trigger, family, tie-mass
  behavioural RED), file 38/38; the PCB-family declaration test scoped to
  `expands == "PCB"` (a second family now exists).
- `test_coverage_presentation.py`: 1 new test (fallback names recalled
  members), file 5/5; answer suites implementation-closure + multiturn +
  grounding 87/87. Ruff: changed files clean (knowledge_answer.py keeps its
  4 pre-existing E402s, identical at HEAD).

### Live (18188, both restarts)

- G7-only replay after recall fix: **3/3 PASS**; turn-debug recall 优必选@12,
  commit @5/5/2, official-source citation `official-source-00c4bd4a40424540`
  (ubtrobot.com) bound to 优必选 in all three answers.
- Full gate after recall fix: 6/7 — G7 r1 rendered
  `deterministic_fallback` and dropped 优必选 (committed@15 in the same
  turn) → drove fix 3.
- Full gate after fallback fix (`replay-full-g7fix-r2-20260913/`):
  **7/7 ALL PASS** (G1–G7); G7 3/3 prose_renderer, recall @12, commit @5
  each; diagnose totals now recall 15/35, commit 9/35 (all 9 = the nine
  post-fix turns; zero before).

## Status

Acceptance met: replay 7/7; recall in-window 3/3; commit 3/3; answer names
优必选 with local official-source evidence (web-luck path no longer needed).
Backlog carried: tie-break richness + whole-term extraction (not needed for
this acceptance), wide pool (1b.1 remainder), 越疆-class tag vocabulary (C1).
