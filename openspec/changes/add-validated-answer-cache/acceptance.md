# Acceptance: add-validated-answer-cache

| # | Criterion | Evidence |
|---|---|---|
| A1 | Web-only answers are never cached; mixed local+web answers may cache | `test_validate_candidate_rejects_web_citation`; synthetic mixed-envelope gate check |
| A2 | Marker/fallback answers are never cached; a bounded enumeration coverage tail may cache | marker/fallback checks in the gate; live marker cleanup |
| A3 | Response citation ids must resolve in the response citation map | `test_validate_candidate_requires_resolvable_citation_map`; envelope-based gate check |
| A4 | Referent/time-sensitive queries are not eligible | `test_eligible_query_rejects_referents_and_time_sensitivity` |
| A5 | Release or data-epoch change misses | `test_cache_round_trip_hits_until_release_or_epoch_changes` |
| A6 | Expired entries miss and purge | `test_cache_expired_entry_misses_and_purges` |
| A7 | Live first call is a miss and second identical call is a hit | `介绍清华的丁文伯` 4.42s→0.06s; lidar 89.23s→0.08s; `hit_count` |
| A8 | Follow-up after a cache hit still binds the local context | cookie-jar probe: 丁文伯 → 他的研究方向 (5.96s, 1 citation); lidar → 这些公司 (6.82s, 7 citations) |
| A9 | A web-only answer leaves no cache row; a local+web answer may cache | cache table inspection; lidar mixed answer row has `local_grounding=true` |

Evidence: `.agents/runs/add-validated-answer-cache/verification.md`.
