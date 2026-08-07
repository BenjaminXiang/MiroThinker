# Fresh Candidate content regression — 18188 (2026-08-07)

Final-code-state regression evidence for the "内容被修坏" systematic repair round.

## Service

- Fresh restart of `18188` from the worktree root (all uncommitted Candidate
  fixes + this round's four production fixes loaded; `reload=False`).
- Command: `.agents/runs/rebuild-canonical-v2-knowledge-platform/s12e/serve_s12e_port.py`
  with the S12F candidate bundle (same argv as the previous session's
  `bash-gqnd55gq`).
- The previous 18188 instance had already exited (killed with the old
  session), so the restart interrupted nothing.

## This round's production fixes (all in this worktree, uncommitted)

1. `knowledge_answer.py` — deterministic/fallback rendering never publishes
   raw search dumps: source-locator tails are stripped (kept only for
   link-seeking queries), content-farm/login-wall claim text is dropped, and
   each grounded point is capped at 200 chars. One shared renderer covers all
   four fallback branches plus the pure-deterministic path.
2. `knowledge_serving_isolated.py` — answer-side relevance guard for
   data-theme concept queries: claims carrying drifted off-theme content
   (traffic surveys, crawlers, crowdsourcing) are dropped before the prose
   prompt and the fallback.
3. `knowledge_serving_isolated.py` — the concept term-expansion view is
   promoted directly after the deterministic view so the earliest-view-wins
   merge no longer drowns it below the candidate cut (recovers 动作捕捉 etc.).
4. `knowledge_serving_isolated.py` — `_person_evidence_match` relaxed:
   education-constrained probes accept the person name plus the constraint in
   the same hit (founder marker no longer required in the same snippet; plain
   name containment instead of the brand-context rule). Fixes the T13
   "未找到" refusal for 早稻田 entrepreneurs.
5. `knowledge_serving_isolated.py` + `knowledge_answer.py` — content-farm /
   login-wall claims (`登录后查看更多`, `立即下载`, `开通VIP`, `上传人`,
   `文档编号`, `搜题` + doc-mill sites) are dropped at claim selection, so
   they never inflate the prose prompt or leak into answers.

## Results

Old online artifact (2026-08-06T120404Z, old instance + old evaluator):
formally 20/25, but T13 (refusal) and T15 (raw dump) were false passes —
not acceptable.

| Run | Mode | Result | Fails |
|---|---|---|---|
| 2026-08-06T1515Z (fixes 1-4, pre junk filter) | grouped | **24/25** | T3 (开普勒/九号, real recall gap) |
| 2026-08-07T0010Z (final code) | single-session | **23/25** | T3 (开普勒 only — 九号 recovered), T19 (真机实测 hard token) |
| 2026-08-07T0010Z (final code) | grouped | **23/25** | T3 (开普勒+九号), T19 (真机实测) |

Trend vs the old artifact: T13 拒答 → PASS with grounded 许晋诚/帕西尼;
T15 raw dump → PASS with integrated 原理 answer; T19 off-topic junk →
integrated embodied-AI data-collection answer (7/8 methods; 真机实测
missing in two of three runs — hard-token variance); T16/T22/T23 evaluator
misjudgments fixed by the evaluator repair.

## Remaining gaps (not this round's defect class)

- T3 上海开普勒机器人: no 酒店送餐 evidence on the data side (probe judge
  rejects; needs data backfill — long-term workstream).
- T3 九号机器人: provider-dependent recall (recovered in the single-session
  run, missed in grouped runs).
- T19 真机实测: answer covers 7/8 reference methods; single hard-token miss,
  present in one of three runs.
- T2 角色精度 ("创始人" vs "联合创始人兼首席科学家"): data-side role
  fidelity, noted previously.

## Checks

- `uv run pytest` canonical suites + workbook oracle: **235 passed**
  (baseline before this round: 216).
- `uv run ruff check` on all touched files: clean.
- `git diff --check`: clean.
- Offline re-judge of the old artifact with the repaired evaluator:
  20/25 → 21/25, remaining 4 fails all real (T3/T13/T15/T19).
- No git mutation performed; all changes remain uncommitted in the worktree.
