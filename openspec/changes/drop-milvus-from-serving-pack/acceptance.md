# Acceptance: drop-milvus-from-serving-pack

| # | Criterion (counts as fixed) | Evidence required | Status |
|---|---|---|---|
| A1 | New packs contain no `milvus.db`, and boot does not open it | v2 pack dir listing from the sealer (no `milvus.db`); v2 server log `grep -ci milvus` = **0**; unit R1/R4/R8 | met |
| A2 | The 1.03GB material is gone from the serving index and pack; the point authority is named and carried | index root 3.42GB→2.57GB, pack 5.15GB→4.30GB (−811 MiB each); `index_point` = 51,026 rows; lookup +218MB | met |
| A3 | v1 packs (run14/run15) still boot unchanged on the new code | unit R5 (`test_v1_pack_still_boots_through_milvus`), plus scratch v1 boot (receipt `files` still carry `milvus.db`) + replay smoke G1/G4 ALL PASS | met |
| A4 | Every v2 failure is fail-closed (missing store, stray Milvus copy, point-set drift) | unit R3/R4/R6 (three refusal tests) | met |
| A5 | npz anchor keeps proving the point set in both directions under the new store | unit R6 (extra point and missing point both raise); the v2 boot rebuilds `index_result_content_sha256` = `690946f3…`, identical to run15 | met |
| A6 | F1's mount receipt + process-scoped cache still work under v2 | unit R7; the v2 server boot wrote `verification: receipt` (mount 289.1s) | met |
| A7 | No retrieval semantic change | replay gate **7/7 ALL PASS** on 18296; `字节跳动`→`ByteDance Ltd.`; `优必选有哪些专利`→32 CN; `国先中心` answer complete with `web_items=[]` | met |
| A8 | Boot does not regress | v2 mount phase **289.1s vs 340.7s** for the same-machine v1 boot (and 320s in the R9 baseline); total boot-to-health ≈12–15 min vs the 721s baseline — no regression, the mount is 51.6s faster | met |
| A9 | The warn-only placeholder census is either a gate or deleted | **deleted** (design §5): census code + its test + the sealer phase and side-car report are gone; the read-side matcher and its 9 tests stay (unit R11) | met |
| A10 | No new start-up failure class; rollback assets exist | the v2 boot never opens Milvus, so the single-writer lock failure mode cannot occur on v2; rollback = revert `f1184bd4` + restart, data-level rollback = point the command file back at the v1 pack (both index roots untouched) | met (rollback not drilled here — it belongs to the switch window) |

## Out of scope (explicitly not accepted here)

Deployment to 18188 and the run16 pack switch (separate window with the rollback
drill), the data-line build-side emitter, and the non-pack envelope serve path.
