# Refactor Contract — perf-retrieval-keepalive-parallel

> Intended behavior-preserving (CLAUDE.md §8). Delivered in commit c4fa382. Verification found
> the parallel part is NON-deterministic — see verification.md; the keepalive part IS clean.

## Scope

1. **Milvus keepalive** (`apps/miroflow-agent/src/data_agents/storage/milvus_collections.py:161-174`):
   inject `grpc_options` (keepalive_time_ms=600000, permit_without_calls=False) at the
   `MilvusClientCompat` chokepoint. Fixes GOAWAY too_many_pings from pymilvus 2.6.11 defaults
   (10s ping on idle channels).
2. **D-path parallel** (`apps/admin-console/backend/api/chat.py` `_lookup_cross_domain_evidence`,
   the `ThreadPoolExecutor(max_workers=3)` block): professor/paper/company retrieve concurrently;
   wall-time = max(1), not sum(3).

## Behavior-preservation analysis

### Keepalive — behavior-preserving (CLEAN)
Only changes gRPC keepalive timing, not query results. Verified: 0 GOAWAY; latency oracle ran
clean (p95 5.71s).

### Parallel — order preserved by construction; SET is non-deterministic (ISSUE)
- **Order:** the parallel block iterates `for f in futures` in submission order and calls
  `f.result()` (blocks per-future), so `merged` is extended professor→paper→company —
  **identical order to the pre-c4fa382 serial for-loop**. The "evidence-completion-order change"
  concern from the design is a non-issue: the code re-orders to submission order.
- **Set:** verification found the D-path candidate set is NON-deterministic across runs
  (33/35/35 candidates). Leading hypothesis: a shared-cache race from the OUTER parallelism
  (c4fa382) — the professor and paper branches both have `augment_with_web=False`, so both
  read/write the shared `RetrievalCache` (retrieval.py:355) concurrently; cold-vs-warm drift
  (run0=33 cold, run1+2=35 warm) is consistent with a cache write race. NOT fully isolated —
  could also be reranker/Milvus tie-breaking (which may predate parallelism). Needs a
  serial-vs-parallel comparison to conclude.

## RED (baseline)
- Pre-fix: GOAWAY too_many_pings spikes (45s variance on D); serial D ~13-45s.

## GREEN
- 0 GOAWAY post-fix (MET).
- Retrieval wall-clock p95 ≤ 6s (MET, 5.71s).
- Golden-order: evidence set stable across runs — **NOT MET** (33/35/35 non-determinism).

## Verdict (per design §5 risk)
The **keepalive** part is behavior-preserving and Acceptable. The **parallel** part is NOT
certifiably behavior-preserving (non-deterministic set) and **cannot reach Accept as a
refactor-contract** until the non-determinism root cause is isolated and either fixed or
accepted. Three options (decision needed):
1. **Isolate** — run serial (pre-c4fa382) vs parallel to confirm whether the non-determinism is
   introduced by parallelism or pre-exists (reranker/Milvus). If pre-exists, parallel is
   behavior-preserving (the non-determinism is pre-existing).
2. **Fix** — if the cache race is confirmed, make `RetrievalCache` thread-safe (lock) or bypass
   the cache for concurrent outer calls. Codex code fix; then re-verify set stability.
3. **Downgrade** — accept the parallel part as behavior-affecting (OpenSpec): tolerate bounded
   set drift (2/34) as a documented behavior, gated by the precision oracle.

## Allowed Superpowers mode
- Keepalive: baseline/golden proof of unchanged behavior (deterministic; clean).
- Parallel: CANNOT use refactor-contract mode until GREEN "set stable" is met. If downgraded,
  becomes an OpenSpec behavior-affecting change with eval-gated acceptance.

## Out of scope
- streaming / cache-as-feature (next latency workstream).
- B-path / E-path latency (only D-path parallelized in c4fa382).
