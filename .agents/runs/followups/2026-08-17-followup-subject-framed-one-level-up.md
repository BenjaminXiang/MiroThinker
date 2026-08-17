# Follow-up: follow-up answers frame the subject one level up (container/park instead of the anchored org)

Status: **Open — recorded only, deliberately not fixed this round** (user instruction
2026-08-17: "这一轮先不修但是要记录清楚").
Date: 2026-08-17. Found by: user hands-on test on production (port 18188, serving
HEAD ≥ `438300a`, after `deepening-turn-anchor-carryover` deploy).
Related: `.agents/runs/followups/2026-08-13-subject-consistency-phase2-residuals.md` §1
(closed); `.agents/runs/deepening-turn-anchor-carryover/` (accepted change whose
behavior this register qualifies).

## Problem (user-reported, verbatim session)

Turn 1 `介绍一下 国际先进技术应用推进中心（深圳）` → answer correct, subject = 国先中心.

Turn 2 `有没有更详细的信息` → answer LEADS with and is organized around
**河套深港科技创新合作区深圳园区**（园区近期在平台建设与产业生态方面取得多项进展，核心
围绕"国先中心"…的揭牌与运营展开…）。国先中心 becomes content inside a park-framed answer.

Turn 3 `它有哪些布局和进展` → same shape: lead sentence
"河套深港科技创新合作区深圳园区正加速打造深港科技创新聚集地…"；国先中心 secondary.

User's verdict: 回答的重点都在【河套园区】，指代错了 — the follow-up answer's subject
is the CONTAINER (park), not the anchored org. Also observed in the UI: after each
follow-up, a "国先" chip/text appears (likely the UI subject indicator; capture in the
evidence below before interpreting).

Classification: **subject-grain / framing drift one level UP** — distinct from the
8/13 class (wrong-entity substitution), which remains fixed: no 张天尧/微众银行, facts
are mostly about the center, and the carryover machinery engaged (no clarification,
subject memory held).

## Evidence already on file (matches this report)

My deploy-day probes recorded the same shape and I scored it PASS under the accepted
change's criteria — in hindsight those criteria were too lenient about FRAMING:

- `.agents/runs/deepening-turn-anchor-carryover/evidence/prod_pronoun_t3.sse`:
  view[0] = `河套深圳园区打造深港科技创新聚集地 - 香港中联办 布局和进展` — the carried
  "subject name" is the ARTICLE TITLE about the park; final answer lead is park-framed.
- `evidence/prod_deepen_t2.sse`: view[0] =
  `河套数学与交叉学科研究院、国际先进技术应用推进中心（深圳）揭牌 这个中心的企业培育情况怎么样`
  — anchor name is a two-institution news headline.

## Likely root cause (hypothesis, code-anchored, unverified this round)

1. On a web-only org turn, the committed session anchor is a `WebEntityHandle` whose
   `display_name` is the source article's TITLE (park-framed, sometimes co-listing
   河套数学研究院 + 国先中心), not the org name.
2. Follow-up turns prefix/bind retrieval and synthesis with that anchor name
   (`_contextual_web_search_view` / displayed-names prefix in
   `knowledge_serving_isolated.py`), and the prose organizer adopts the same frame →
   park-framed lead sentences.
3. `_sanitize_soft_turn_anchor` deliberately never drops WEB handles ("web handles are
   the soft subject's own shape" — design note in the accepted change). That assumption
   is falsified for article-title-shaped handles. `_soft_subject_name` HAS
   news-headline guards (、-joins and 揭牌/挂牌/成立… suffixes) but they apply only to
   soft-subject derivation, not to web-handle anchors.
4. Aggravator: the subject-consistency gate can filter the web lane to zero on
   follow-ups (16→0 observed, register §1 closure note), so carried park-framed
   evidence dominates synthesis and no fresh org-framed evidence rebalances it.

## Proposed directions (NOT executed)

- Near-term deterministic option: extend the `_soft_subject_name` headline guards to
  web-handle display names before they become session anchors (or prefer the stored
  `soft_subject_name` for view prefixing when both exist). Small, testable.
- Principal fix in the planned `contextual-query-interpretation` change (research doc
  `docs/plans/2026-08-17-contextual-query-interpretation-research.md`): the
  context-aware rewrite resolves "它/更详细" to the org NAME (validated against the
  session subject list), which is exactly the subject-grain this defect is about.
- Evaluation lesson to carry into that change's acceptance line: PASS criteria must
  include "answer LEAD/subject = the anchored org", not only "no wrong-entity
  substitution + on-topic facts". The accepted change's probe scoring missed this bar.

## Open questions

- Is the "国先" UI chip the displayed subject indicator, and does it show the org name
  while the answer frame is the park? (Confirms anchor-vs-name split.)
- Does turn-2 (`有没有更详细的信息`) drift arise from the same anchor-name prefixing,
  or also from carried prior-web-evidence framing? Both turns share the anchor;
  distinguishing needs the SSE dumps of THIS user session (not captured — the UI
  session is live; next repro should save 查看检索过程 output or re-run via curl).
