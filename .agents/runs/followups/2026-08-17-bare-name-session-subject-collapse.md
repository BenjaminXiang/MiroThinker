# Follow-up: bare-entity-name sessions collapse (no subject stored → refusal T1 + clarification T2)

Status: **Open — recorded only, not fixed this round** (user in test-and-record mode
2026-08-17; same instruction pattern as the group-1 register).
Date: 2026-08-17, user test at 17:07 via public UI (journal: POST /api/chat/stream
17:07:20 and 17:07:47).
Related: `.agents/runs/followups/2026-08-17-followup-subject-framed-one-level-up.md`
(group 1, framing drift);
`.agents/runs/followups/2026-08-13-subject-consistency-phase2-residuals.md` §3
(web-lane telemetry gap — this register supplies its first hard evidence).

## Problem (user-reported, verbatim session)

- T1 `国际先进技术应用推进中心（深圳）`（裸机构名，无"介绍一下"前缀）→
  refusal-shaped answer: "公开信息中未找到关于…的具体实体描述或详细背景资料" + 对
  "类似名称机构"的泛泛推测（"暂无公开的详细运营信息或官方介绍可供确认"）。
  The org IS findable — the same subject answered correctly earlier the same day
  (group 1) and at deploy-day probes.
- T2 `这个中心的企业培育情况怎么样` → referent clarification
  （"您的问题里使用了'他/她/它/这家'等指代词…请补充您想了解的对象"）。

User verdict: 问题更严重了 — the whole multi-turn experience collapses for this
session shape.

## Two defects, both root-caused (verified, not fixed)

### D1 — never-refuse violated on an empty-evidence T1

Phase-1's never-refuse invariant (prompt v15) is broken in spirit: the fallback
answer reads as a refusal ("未找到…暂无…可供确认") plus speculation about
similar-sounding institutions. Why the evidence was empty is **undeterminable from
logs**: the production journal around the 17:07 turns contains ONLY HTTP access
lines — zero web-lane/provider/gate lines in the entire 2h window (verified 2026-08-17).
Candidate causes, indistinguishable today: web lane outage (the §3 `unavailable`
episode class), or subject-gate filtering everything to zero (observed 16→0 on
deploy day). This is register §3's telemetry gap made concrete.

### D2 — soft-subject derivation rejects the bare entity name (VERIFIED)

`_soft_subject_candidate_ok`'s query-echo guard (`candidate == query.strip()`) was
meant to reject garbage echoes of long questions, but it also rejects the CLEANEST
case: a query that IS exactly the subject name. Verified live (2026-08-17):

- `介绍一下 国际先进技术应用推进中心（深圳）` → derives
  `国际先进技术应用推进中心（深圳）` ✓ (group 1 shape — works)
- `国际先进技术应用推进中心（深圳）` → **None** (group 2 shape — rejected)

With T1 also returning no single web handle (empty evidence, D1), BOTH derivation
paths die → committed session stores `soft_subject_name=None` and no anchor →
T2's anaphoric reference correctly (per current code) falls to the clarification
gate. The accepted change's Task-10 test set only covered the prefixed form — the
bare-name branch was never tested.

Compounding chain: D1 (empty evidence) × D2 (echo guard) = session with no subject
at all → every follow-up clarifies → multi-turn unusable for this session shape.

## Proposed directions (NOT executed — awaiting user decision)

- **D2 fix candidate (small, deterministic)**: accept the candidate when the query
  itself is a bare subject shape — e.g., relax the echo guard when the candidate
  equals the query AND the query carries no question markers and is within subject
  length (the guard's real target is long question echoes, not noun-phrase queries).
  Add the bare-name case to the Task-10 derivation test set (RED first).
- **D1**: telemetry FIRST (§3 — provider/reason/duration lines for the web lane),
  then either outage retry/degradation or gate-recall tuning; separately, the
  template fallback must answer from whatever is confirmed rather than "未找到"
  phrasing (never-refuse applies to fallbacks too).
- Both are also in scope for `contextual-query-interpretation` (research doc
  `docs/plans/2026-08-17-contextual-query-interpretation-research.md`): the
  interpretation layer resolves the subject from the query itself on turn 1.

## Evidence

- Derivation verification output (above, run against worktree HEAD `4079bbf`).
- Journal excerpt: only access lines around the two turns; zero provider/telemetry
  lines in 2h (`journalctl --user -u canonical-v2-backend --since "2 hours ago"`).
- User transcripts (verbatim above; UI also showed the 国先 subject chip on both
  turns — chip present even when no session subject is stored; UI indicator
  semantics worth confirming too).
