# Trace-based stage attribution — 1.2 evidence (2026-08-18)

Replay: seven sessions against the fix-branch serve (port 18188, code with
turn-trace). Journal: `/var/tmp/turn-trace-fixline/`. Every attribution below
was read from the journal via `scripts/read_turn_trace.py` / raw JSONL only —
no source inspection needed.

## Replay outcome parity vs frozen baseline (2026-08-17)

| Session | Baseline | This run | Parity |
|---|---|---|---|
| G1 framing | FAIL | FAIL (2 asserts) | ✓ stable RED preserved |
| G2 bare name | PASS | PASS | ✓ |
| G3 person pronoun | FAIL | FAIL (3 asserts) | ✓ stable RED preserved |
| G4 patents | PASS (variance line) | **FAIL** (国知局 + 未找到) | variance line — defect form identical to user transcript (P5); channel healthy |
| G5 expansion | FAIL | FAIL (2 asserts) | ✓ stable RED preserved |
| G6 anaphoric opener | PASS | PASS | ✓ |
| G7 enumeration | FAIL (1/3) | PASS (3/3) | variance line — 优必选 present in all 3 today |

Conclusion: tracing did not change outcomes; stable RED/GREEN lines are
identical; G4/G7 moved within their documented variance envelopes.

## Failure-stage attribution from the trace alone

- **G1 (P1 anchor lift-up), failing turn `它有哪些布局和进展`** —
  `session_snapshot.active_anchor_name = "河套深圳园区打造深港科技创新聚集地 - 香港中联办"`
  and `answer_subject` = the same string; lanes all-zero except web (42/42, no
  gate drops). Diverging stage: **anchor binding** — a news headline became the
  canonical subject of a web-only session (Phase 3 target: news-headline guard).
- **G3 (P4 title-as-institution), failing turn `他有哪些论文`** — same
  poisoned headline anchor persists; person-domain answer expected. Diverging
  stage: **anchor binding + referent type check** (Phase 3).
- **G4 (P5 patent deflection), failing turn `该公司的专利有哪些`** — anchor is
  CORRECT (`深圳市优必选科技股份有限公司`), but `lanes.relationship = (0, 0)` while
  web = (34, 34): the patent relationship lane returned zero candidates.
  Diverging stage: **data** — company↔patent relations absent from the serving
  pack (Phase 4 rebuild target). Note `degradation=none`: the lane ran and
  legitimately found nothing; this is a data gap, not a channel failure.
- **G5 (P6 expansion base), failing turn `还有哪些类似的公司`** —
  `active_anchor_name = 优必选` but `answer_subject = 深圳前海微众银行股份有限公司`
  with web lane (0,0) and vector (48,48). Diverging stage: **expansion-base
  selection** — the expansion query drifted off the session subject (Phase 3).

## Healthy-path check (1.2.2)

G6 anaphoric-opener session turns carry `degradation=none` and PASS assertions
unchanged; smoke turn `介绍云迹科技有限公司` traces `status=ok,
degradation=none, subject=北京云迹科技有限公司` with lane counts populated.
