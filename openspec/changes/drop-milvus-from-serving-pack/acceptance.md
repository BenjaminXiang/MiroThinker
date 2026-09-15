# Acceptance: drop-milvus-from-serving-pack

| # | Criterion (counts as fixed) | Evidence required | Status |
|---|---|---|---|
| A1 | New packs contain no `milvus.db`, and boot does not open it | v2 pack dir listing from the sealer; boot log with zero Milvus steps; unit R1/R4/R8 | pending |
| A2 | The 1.03GB material is gone from the serving index and pack; the point authority is named and carried | size table (v1 vs v2 index root and pack); `index_point` row count in the zipped-audit script | pending |
| A3 | v1 packs (run14/run15) still boot unchanged on the new code | unit R5; scratch v1 boot + replay smoke on the run15 copy | pending |
| A4 | Every v2 failure is fail-closed (missing store, stray Milvus copy, point-set drift) | unit R3/R4/R6 | pending |
| A5 | npz anchor keeps proving the point set in both directions under the new store | unit R6 | pending |
| A6 | F1's mount receipt + process-scoped cache still work under v2 | unit R7; boot log shows `verification: receipt` on the second mount | pending |
| A7 | No retrieval semantic change | replay gate 7/7; the two verbatim probes; the user case with `web_items=[]` | pending |
| A8 | Boot does not regress | v2 boot-to-health seconds vs the 721s baseline (v1) | pending |
| A9 | The warn-only placeholder census is either a gate or deleted | design §5 decision + unit R11 + the sealer no longer writing the side-car report | pending |
| A10 | No new start-up failure class; rollback assets exist | single-writer Milvus lock failure mode removed by construction on v2; rollback = revert branch (no data surgery needed) | pending |

## Out of scope (explicitly not accepted here)

Deployment to 18188 and the run16 pack switch (separate window with the rollback
drill), the data-line build-side emitter, and the non-pack envelope serve path.
