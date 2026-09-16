# Tasks: fix-exact-title-and-marker-strip (G6)

- [x] 1. Exact lane long-title containment for paper/patent (>= 20 chars,
       equality kept for short names) — the local canonical paper re-enters
       the exact lane instead of only web duplicates.
- [x] 2. Prose private-marker guard: strip an echoed protocol marker instead
       of raising (one echo killed the whole synthesis -> raw-candidate
       dump). Guard purpose (marker never reaches user) preserved.
- [x] 3. Tests: 4 exact-title unit tests; marker tests updated to the strip
       contract (16 cases); serving suite green except known pre-existing.
- [x] 4. Live: G6 answer is now a synthesized profile with the author list
       and AAAI venue (was raw dump). Residual: claim budget truncates the
       author list at 6/9 names (Wenbo Ding is 8th) — follow-up in the
       claim-budget slice.
