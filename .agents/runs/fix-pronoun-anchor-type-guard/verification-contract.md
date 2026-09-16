# Verification Contract: fix-pronoun-anchor-type-guard

Written BEFORE production edits. Slice: `fix-pronoun-anchor-type-guard`.

## RED (current code)

`_referent_clarification_needed(query="他有哪些论文", committed=<company
anchor>)` returns False — the org anchor is trusted for a personal
pronoun and the turn free-retrieves junk (G3 replay failure, live trace
2026-08-28 04:46).

## GREEN

1. 他有哪些论文 + company anchor → clarification needed.
2. 他有哪些论文 + paper/patent anchor → clarification needed (P4 family:
   title-as-anchor must not swallow personal pronouns).
3. 他的代表性论文有哪些 + professor anchor → NOT needed (binds today;
   matches existing history-binding test semantics).
4. 该公司的专利有哪些 + company anchor → NOT needed (G4 flow).
5. 这个中心的企业培育情况怎么样 + company anchor → NOT needed (G2 flow).
6. 他有哪些论文 + company anchor + explicit named subject in query → NOT
   needed.
7. Personal pronoun + company anchor + professor anchor in referent
   history → NOT needed (history supplies the person).
8. Replay gate on 18188: 19/19 (G3 GREEN; G1–G7 no regressions).
