# Follow-up: anaphoric opener in a "new session" answers a full 微众银行 profile instead of clarifying

Status: **Open — recorded; attribution pinned to one user answer** (how was the
"new session" started?).
Date: 2026-08-17. Found by: user hands-on test on production (HEAD ≥ `438300a`).
Related: round-1 findings P7 + `transcripts.md` group 6; group 5 (P6 — the likely
anchor source under hypothesis A); register 2026-08-13 trigger B (same 微众银行
profile text family — third appearance of this substitution entity).

## Problem (verbatim in transcripts.md group 6)

- Session opening turn `这个中心是做什么的` (anaphoric expression, no context).
- Expected: referent clarification (the gate's design intent for anchor-less
  anaphora — "free retrieval in that state answers about an arbitrary entity").
- Actual: a complete 深圳前海微众银行 profile, content family identical to the
  8/13 trigger-B drift answer.

## Verified facts (read-only, 2026-08-17)

1. The UI "新对话" button calls `POST /api/chat/session/reset`
   (`frontend/src/pages/Chat.tsx` `startNewConversation` → `resetChatSession`),
   and the backend reset issues a fresh session cookie — clicking it IS a real
   backend reset.
2. On a genuinely fresh session (`committed=None`),
   `_referent_clarification_needed('这个中心是做什么的')` returns **True**
   (should clarify) — verified against worktree HEAD `4079bbf`.

## Two mutually exclusive hypotheses (pending one user answer)

- **A — session continuation (tab/cookie carryover)**: the "new session" was a new
  browser tab or page reload WITHOUT clicking 新对话; the `miroflow_chat_session`
  cookie carried group 5's committed session (whose anchor is plausibly 微众银行 —
  see P6). The anaphoric opener then binds that anchor and the profile answer is
  code-as-designed. Under A the DEFECT is a product/contract one: **the user's
  mental "new session" ≠ the system's cookie-scoped session** — an anaphoric
  opener in a "new" tab silently answers the previous tab's topic.
- **B — gate failure on true reset**: the user clicked 新对话 and still got the
  profile — then production behavior contradicts the verified unit behavior
  (implementation/wiring defect on the fresh path).

Distinguishing question (asked to user 2026-08-17): 新会话是怎么开的——点了
"新对话"按钮，还是新开了标签页/刷新了页面？

## Parked for the chain audit (either way)

- Under A: whether tab-scoped sessions are the right product contract (e.g., reset
  on new tab is impossible with cookies alone; UI hint when an anaphoric opener
  binds a stale anchor).
- Under B: capture SSE of a true-reset repro to find the divergence point.
- 微众银行 as recurring substitution entity (3 appearances across 5 days) — worth
  a data-side look at why this record is so salient in the company vector lane.
