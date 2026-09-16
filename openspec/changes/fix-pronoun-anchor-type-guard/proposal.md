# Proposal: fix-pronoun-anchor-type-guard

> G3 replay-gate closure (18/19 → 19/19 target). Human docs:
> `docs/plans/2026-08-28-web-lane-timeout-utf8-fix-log.md` (G3 遗留节).

## Why

G3 person-pronoun replay turn: T1 anchors an ORGANIZATION
(深圳国际先进技术应用推进中心), T2 「他有哪些论文」 answers junk
(papers like 《"做"与"揍"》) instead of clarifying. Live evidence
(2026-08-28 turn trace): the session snapshot is CORRECT — org anchor +
referent hint present — but `_referent_clarification_needed` only fires
when `active_anchor is None`. A present anchor is trusted regardless of
type, so a PERSONAL pronoun binds to an organization and the turn
free-retrieves in the paper domain. The clarification rule
(`canonical_v2_chat.py` `_REFERENT_CLARIFICATION_PROMPT`) never gets a
chance.

## What Changes

- `followup_referents.py`: NEW `has_personal_pronoun(query)` — 他/她
  (NOT 它/这家/该) under the same clause-boundary rules as the existing
  singular-referent pattern.
- `canonical_v2_chat.py` `_referent_clarification_needed`: NEW guard — a
  personal pronoun over a non-person active anchor (domain not in
  {"professor"}) clarifies, unless the query names an explicit subject or
  the referent history holds a person-domain binding.

## Impact

- Affected code: one predicate + one branch + tests.
- Behavior: 他/她 over company/paper/patent anchors → clarification
  (never free-retrieve); 他/她 over professor anchors binds as today
  (existing test `test_referent_clarification_respects_history_binding`
  must stay green); 该公司/这家/它 anchors unaffected (G4/G2 replay).
- Non-goals: anchor-type-aware retrieval for org-affiliated papers
  (product question, separate).
