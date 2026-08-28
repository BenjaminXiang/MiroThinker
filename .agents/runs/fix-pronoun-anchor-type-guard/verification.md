# Verification Evidence: fix-pronoun-anchor-type-guard

Contract: `verification-contract.md` (written before edits).

## Unit (GREEN)

- `tests/test_canonical_v2_pronoun_anchor_type_guard.py` — 9/9:
  company/paper/patent anchors + 他/她 → clarify; professor anchor → binds
  (existing semantics); 该公司/这个中心 → bind (G4/G2 flows); explicit named
  subject → no clarify; professor in referent history → binds.
- `tests/test_subject_layer_bare_name.py` — 6/6 green alongside.
- `tests/test_canonical_v2_referent_history.py` — 11 failed / 8 passed,
  IDENTICAL at HEAD (stash roundtrip) — pre-existing drift, not this slice.

## Live replay gate (18188 restarted with the guard)

- **G3 person-pronoun: PASS** (was FAIL) — 「他有哪些论文」 over the
  organization anchor now returns the clarification
  (canonical_v2:G:clarification_only).
- Overall 18/19: G1/G2/G4/G5/G6 green; the single failure this run was
  G7#2 (优必选 missing from the enumeration answer).

## G7 residual characterization (post lane fixes — new failure surface)

The G7 lane layer is now consistently healthy (web `succeeded/48`,
supplemental 3–6, zero errors across all turns today). The remaining
flakiness is at ANSWER level: failing turns deliver the same
优必选-bearing listicles to the answer layer (职友集排名 / 深圳70+人形机器人
产业链企业一览 / OFweek 爆单) but the synthesized list fills its entry
budget with local vector-noise companies (钟表/建筑/传播) instead. Gate
observations today: ~2/3 per-turn pass rate. This is the P8
enumeration-completeness family (answer-synthesis quality tuning — entry
budgeting/headline-player priority), not a lane defect; needs its own
slice (prompt/fusion work), deliberately not a drive-by.
