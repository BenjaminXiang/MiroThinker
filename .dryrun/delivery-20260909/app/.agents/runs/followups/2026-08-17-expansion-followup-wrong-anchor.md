# Follow-up: expansion follow-up ("还有哪些类似的公司") anchors on the wrong entity (微众银行, not 优必选)

Status: **Open — recorded only, attribution deferred** (user test-and-record mode,
2026-08-17).
Date: 2026-08-17. Found by: user hands-on test on production (HEAD ≥ `438300a`).
Related: user-testing round-1 findings P6 + `transcripts.md` group 5; likely same
family as P3 (bare/echo-guard subject loss — `2026-08-17-bare-name-session-subject-
collapse.md` D2) and P4 (synthesis resolving unbound follow-ups against the
inherited session anchor); register §3 (no telemetry to attribute). NOTE: 微众银行
is the SAME substitution entity as the 8/13 register trigger B.

## Problem (verbatim in transcripts.md group 5)

- T1 `优必选科技怎么样` → correct, richer-than-group-4 UBTECH profile (subject right).
- T2 `还有哪些类似的公司` → answer opens "类似**深圳前海微众银行股份有限公司
  （互联网银行与金融科技）**的公司包括：" and lists banks/insurers (招商银行,
  微民保险). Expected: companies similar to UBTECH (robotics industry).

## Observed-behavior notes (no attribution claims)

- The expansion's reference entity was not the turn-1 subject; it was a different
  company from a different industry.
- The expansion wording is BY DESIGN not a referent (followup_referents docstring:
  expansion requests "还有哪些/有没有类似的" intentionally match neither referent
  family "until a real expansion operation exists") — so no referent binding fired;
  whatever supplied the "similar to X" X came from elsewhere in the chain.
- Same-question-different-answer variance also observed: group 4 T1 vs group 5 T1
  (same query, different detail level) — evidence composition varies per session.

## Attribution questions parked for the chain audit (NOT investigated)

1. What anchor did T1 commit this time (canonical UBTECH, web handle, or a
   vector-lane capture such as 微众银行)?
2. Did the anchor-capture sanitize get skipped because T1's soft-subject derivation
   failed the echo guard (`优必选科技怎么样` derives None — same D2 shape as
   `国际先进技术应用推进中心（深圳）`)?  [hypothesis, unverified]
3. Did the T2 synthesis resolve "类似" against the inherited answer-session anchor
   (P4 mechanism)? [hypothesis, unverified]
4. Is there ANY path today that gives an expansion turn its reference entity
   (displayed set, soft subject, anchor), or is expansion semantics simply absent?

None answerable from today's logs (§3).

## Expected behavior (for the future fix contract)

An expansion follow-up over a single-subject session expands around THAT subject
(优必选 → robotics peers), or asks which aspect to expand on — never silently
substitutes a different industry's entity.
