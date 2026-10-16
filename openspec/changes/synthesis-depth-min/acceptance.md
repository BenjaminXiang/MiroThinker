# Acceptance: synthesis-depth-min (slice ①min)

## Acceptance criteria

| # | Criterion | Evidence type |
|---|---|---|
| AC1 | 「目前有哪几种主流的JEPA变体？」 cites **≥3 real sources** (JEPA/联合嵌入 pages or papers) and presents **≥4 categorised groups with per-item key points** — i.e. at least the quality the short form 「JEPA 有哪些变体？」 reaches today | live ask, dev line + site; before/after transcripts in `verification.md` |
| AC2 | The same question's answer still contains no fabricated entity, number or date beyond its sources (spot-check: every named variant traceable to an evidence item) | manual read against the evidence list |
| AC3 | List-shaped **entity** turns do not regress: 优必选 patents (relationship lane) and 深圳具身智能 companies keep their current answer shape and citation counts | live ask, dev + site (matrix) |
| AC4 | The 片② acceptance matrix still passes 6/6 and the negative control stays **Web-only** | live ask ×6 |
| AC5 | `replay_fix_round1.py` **7/7** on the dev line and the site | replay gate |
| AC6 | Recall gate: **0 fail-level** diffs vs the frozen baseline and the control | `eval_recall_canonical_v2.py --diff` |
| AC7 | TTFT does not regress: warm JEPA ask and the round-43 probe set stay inside the round-43 envelope (JEPA warm ≤ ~17 s; median of the 8-question probe not worse than the round-45 site numbers + noise band) | live ask timing, dev + site |
| AC8 | Kill switch: with `CANONICAL_V2_WEB_WIDE_WINDOW=0` the Web-only list turn keeps the pre-slice window (unit test + in-process probe) | unit test |
| AC9 | The reseal is manifest-only (three rebound fields, hardlinks, self-audit) on both lines, with the current pack kept byte-identical as the rollback asset | reseal log |

## Non-goals

- Matching the customer's 20+ variant, 7-category reference verbatim — that needs
  parametric knowledge and is explicitly a separate product decision (see
  proposal "Out of scope"). This slice's bar is AC1.
- Any change to local-lane behaviour, ranking, or the answer-renderer prompt.
- Multi-turn follow-ups ("还有哪些") — unchanged surfaces; measured for regression
  only (AC3/AC5).
