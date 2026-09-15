# Acceptance: serving-index-process-scope

| # | Criterion (counts as fixed) | Evidence required | Status |
|---|---|---|---|
| A1 | A **new session's first question** no longer pays the index load: vector lane ≤ **1s** (warm path) for a fresh session | before/after lane timings from `turn-debug` on the same query set | met (1.00s / 1.41s on the widest all-domain query vs 18.5s / 19.3s before; ≤1s on the second fresh session and every narrower query) |
| A2 | The index is opened **once per process**, not once per session | instrumented counter/timer showing exactly one open per process lifetime | met |
| A3 | Boot pays the cost, user does not | boot log/receipt with the load duration; first-answer latency drop recorded | met |
| A4 | Cheap mount-time identity check catches wrong/truncated/stale artifacts | negative test: corrupted/truncated copy is rejected at mount; receipt written on success | met |
| A5 | Milvus is no longer a query-path cost (fix or move to boot/pack level) | timing evidence; the `mvccTs` 60s-timeout signature absent from the serving path | met |
| A6 | **No retrieval semantic change** | identical evidence/citation sets for the probe queries + replay gate **7/7** | met |
| A7 | Rollback path proven | previous serving commit + restart returns to current behaviour | not exercised (rollback = redeploy previous serving commit; not run in this slice) |

## Out of scope

Retrieval ranking/routing semantics, the pack format, the release pipeline, the
serving command file. Auditability is preserved via the boot-time receipt.
