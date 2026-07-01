# Verification — perf-retrieval-keepalive-parallel

> Run 2026-07-01, current HEAD, synthesis off, Serper 403 (web fails fast).

## GOAWAY (keepalive)
- Post-fix: 0 GOAWAY. The latency oracle (3 runs × 12 cases) ran clean with no Milvus connection
  errors; consistent with commit c4fa382's "0 GOAWAY post-fix". Keepalive part = behavior-preserving, ACCEPT.

## Latency SLO
- Retrieval wall-clock p95 = **5.71s** (latency-baseline.json, synthesis off, no web) — SLO ≤ 6s **PASS**.
- Slowest case: #26 D-path 5.71s. Caveat: Serper 403 fails fast (no web latency); with a live
  Serper, D-path adds ~1.8s → ~7.5s, which would BREACH the 6s retrieval SLO. Web must run
  concurrently with DB recall (see add-web-augment directive) to stay under SLO.

## Golden-order / set-stability (parallel) — FAILED
Empirical: ran /api/chat for D-path case #26 ("爱博合创...") three times, extracted candidate
label sets (sorted):
```
run0 (cold cache): n=33
run1 (warm):        n=35
run2 (warm):        n=35
set stable across 3 runs: False
```
- **Order**: preserved by construction (`for f in futures` submission-order + `f.result()` per
  future → merged professor→paper→company, same as serial). Not the issue.
- **Set**: non-deterministic (33 vs 35). Cold-vs-warm pattern (run0=33, run1+2=35) consistent
  with a shared-cache write race (professor + paper branches both `augment_with_web=False` →
  both touch `RetrievalCache` concurrently; retrieval.py:355). NOT fully isolated — reranker/
  Milvus tie-breaking may also contribute and may predate parallelism.

## Test status
- 21 chat tests: NOT re-run this session (commit c4fa382 claims pass). To re-confirm in Phase 5.

## Verdict
- **Keepalive**: Accept (behavior-preserving, 0 GOAWAY, deterministic).
- **Parallel**: NOT Accept as refactor-contract — non-deterministic set (33/35/35). Decision
  needed (refactor-contract.md §Verdict): isolate / fix / downgrade.
