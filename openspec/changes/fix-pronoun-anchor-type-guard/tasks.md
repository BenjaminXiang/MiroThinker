# Tasks: fix-pronoun-anchor-type-guard

- [x] 1. Verification contract written before edits
       (`.agents/runs/fix-pronoun-anchor-type-guard/verification-contract.md`).
- [x] 2. `has_personal_pronoun()` in `followup_referents.py` (他/她 under
       the singular-pattern boundary rules; 它/这家/该 excluded).
- [x] 3. Guard branch in `_referent_clarification_needed`: personal pronoun
       over a non-professor anchor clarifies, unless explicit subject or a
       person binding in referent history.
- [x] 4. Unit tests 9/9 (company/paper/patent anchors clarify; professor
       and org-referent bindings unaffected; explicit subject; history
       person). Referent-history suite unchanged (11 failures pre-existing
       at HEAD, stash-verified).
- [x] 5. Live replay gate: G3 GREEN; 18/19 overall — the single failure
       moved to G7 answer-completeness variance (P8 family, see
       verification.md), not this slice.
