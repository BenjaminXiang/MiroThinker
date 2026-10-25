# Tasks: add-validated-answer-cache

- [x] 1.1 Add the SQLite answer-cache store (exact query key, release/epoch
      checks, TTL, hit counter, purge).
- [x] 1.2 Add the write gate: local-grounded citations (at least one
      `local-source-*`; web citations allowed, web-only rejected), resolvable
      response citation map, no protocol marker, no fallback, no conflicts,
      answer length 40–8000, no referent/time-sensitive query.
- [x] 1.3 Attach the cache post-construction and add the hit path before
      retrieval; rehydrate the session context, displayed ids, and checkpoint.
- [x] 1.4 Store a validated turn after commit; never fail a turn on cache I/O.
- [x] 1.5 Unit tests for the gate and the store (hit, release/epoch miss, TTL).
- [x] 1.6 Deploy the module and enable it in `run.sh`
      (`CANONICAL_V2_ANSWER_CACHE_DB`, `CANONICAL_V2_ANSWER_CACHE=1`).
- [x] 1.7 Live verify: first call slow/miss, identical second call fast/hit,
      follow-up after the hit still binds context, web-only answers are not
      cached. Evidence: `介绍清华的丁文伯` 4.42s → 0.06s; lidar 89.23s →
      0.08s; hit + cookie follow-up 5.96s; cache rows 7, all grounded.
