# Tasks: retrieval-v2-derived-index-and-fusion

> Sequencing (user 2026-09-12): the web-completion track is already queued and
> runs in parallel; this change executes Step 1+2 → 3 → 4 → 5 in the serving
> worktree. Every step: tests → same-day differential → replay gate → live
> probe evidence → change-log entry.

## Step 0 — contract and baseline

- [x] 0.1 Create `.agents/runs/retrieval-v2-derived-index-and-fusion/verification-contract.md`:
       frozen baselines (TTFT r4, generalization r5 P2 counts, testset g2/g5,
       replay ALL PASS) + RED/GREEN per step.
- [x] 0.2 Register the change in `openspec/change-ledger.md` (in-implementation).
- [x] 0.3 Field contract: which lookup fields feed name/tags/body columns,
       which feed facets, which stay display-only (retrieval-review §10.3).

## Step 1 — derived lexical index

- [x] 1.1 `canonical_v2/lexical_index.py`: shared `segment()` (jieba +
       name-form user dictionary) and build/search API; FTS5 schema
       name/tags/body; `bm25(..., 8, 4, 1)`.
- [x] 1.2 Build script `apps/miroflow-agent/scripts/build_lexical_index.py`
       (idempotent; artifact + manifest outside the sealed pack).
- [x] 1.3 Unit tests: tokenization matrix (2-char/3-char/mixed/alias/name
       form), field weights, OR semantics, missing-artifact fallback,
       manifest mismatch refusal.
- [x] 1.4 Lane integration behind `CANONICAL_V2_LEXICAL_INDEX`; candidate
       construction keeps the existing lineage/claim-binding path; lane trace
       gains index-hit counts.
- [x] 1.5 Build the run14 artifact; offline measurement of query latency and
       a candidate-precision proxy on the P2 probe terms. Artifact built
       against the serving pack (`index-v1`), 47,071 docs / 94.2 MB / 70 s;
       lane-internal select+build 0.056-0.710 s on the four harness turns
       (`step1-measurements.md`).
- [x] 1.6 Live A/B batch (switch on/off): generalization + testset + replay
       + TTFT. **Red**: replay 3 failures (G3 person scope, G7 优必选
       missing 2/3), testset g2 2/3 + g5 1/2, while TTFT was unchanged
       (lane not on the critical path). Root cause: the lane replaced the
       tuned F1 category recall with token+BM25+window; attribution via
       id-level window diff. The lane is pinned off by default
       (`lexical-index.conf`) and Step 1b replaces the substitution with
       candidate-generation + rerank (design.md "Step 1 exit review").

## Step 1b — index as candidate generator + relevance rerank

- [x] 1b.0 Cross-encoder relevance rerank lane (implemented 2026-09-13, OFF by
       default): `canonical_v2/rerank_client.py` + serving wiring; transport
       contract and fail-closed validation per design.md "Step 1b(a)"; the
       model reorders **inside** the existing deterministic buckets and any
       `RerankUnavailable` falls back to `_deterministic_serving_rerank()`.
       Tests: `test_rerank_client.py` + `test_serving_rerank_model.py` 25
       green; four-file regression 71 green. Live ON/OFF differential is
       tracked in 1b.0b and is NOT yet closed.
- [ ] 1b.0b Live differential for 1b.0 (same day, same pack, ON vs OFF):
       **measured 2026-09-13 — quality gate failed.** testset 1/5 vs OFF 4/5
       (g2 0/3: 九号 missing, pool 4<5, stance check); generalization
       on-category lost (drone 46→30, medical 47→39) while off-category gained;
       TTFT all < 30 s (11.6-23.8 s); replay clean — the single ON failure
       `G3_person_pronoun` fails identically in both OFF runs (same assertion,
       same `query_type`), so it is a pre-existing deterministic defect, not a
       rerank regression. ON verified real via the endpoint's request counter
       (+128/turn). Remaining: live fault injection (malformed payload,
       refused connection) proving the deterministic fallback and secret-free
       logging on a real turn.
- [ ] 1b.0c Pronoun→person defect (found while reading the replay gate): after
       an institution turn, `他有哪些论文` never routes to clarification, and
       the oracle accepts only `clarification_only` or the literal substrings
       教授/老师/学者/论文作者, so a prose clarification ("“他”具体指哪位作者")
       is scored as a failure. Fix the routing, then make the assertion measure
       the behaviour instead of a literal proxy.
- [ ] 1b.1 Wider pool: recall pass 2-4x the request window (cap ~512);
       bigram-aware recall for residue terms so F1-class hits (优必选 via
       智能) are generated, not lost.
- [ ] 1b.2 Relevance rerank of the pool. Landed half: cross-encoder
       Qwen3-Reranker-8B (`:18006`, `POST /v1/rerank`) over the existing
       buckets — 1b.0. Open half: embedding scoring with Qwen3-Embedding-8B
       (`:18005`, 4096-dim, `POST /v1/embeddings`; reuse the pack's persisted
       vector matrix where the document→point mapping holds, else batch-embed
       the candidates' short text) over the wide pool; deterministic tie-break.
- [ ] 1b.3 Superset guard: for category queries the index window must be a
       superset of the substring lane's recall (offline id-level diff on the
       frozen harness turns) or the lane falls through. **Widened 2026-09-13**:
       the same guard must cover the *commit* axis — 1b(a) showed a
       text-only cross-encoder demoting struct-field matches (九号:
       `industry=机器人` with a thin profile renders a near-empty document), so
       every entity the legacy path committed has to stay committed after
       rerank, or the lane falls through. Instrument first: per turn, the
       pre-rerank position, post-rerank position and rendered document length
       of the struct-field-matched entities.
- [ ] 1b.4 Four oracles, same day, before default-on: replay zero new
       signatures; testset g2 3/3 + g5 2/2; P2 not worse (lidar ≤10,
       storage 0); harness lane cost <1 s + superset proven.
- [ ] 1b.5 Unit tests: pool sizing/truncation, rerank determinism, superset
       guard behavior, fall-through on thin recall.

## Step 2 — facets (structured filter channel)

- [ ] 2.1 `doc_facet` schema + build rows (domain/industry/tech_tag/
       geography/founded_year/quality_tier).
- [ ] 2.2 `StructuredConstraints` consumers translating plan slots into facet
       predicates; facet counts in the trace.
- [ ] 2.3 Tests: facet predicates, geography from the registered address
       (AQ-S8 witness), empty/contradiction behavior.
- [ ] 2.4 Live A/B on geography-narrowing and category+city turns.

## Step 3 — RRF fusion

- [ ] 3.1 Fusion function + receipt (per-lane ranks, k=60, weights default
       1.0, deterministic tie-break by canonical id).
- [ ] 3.2 Unit tests on synthetic ranks (order, determinism, quota
       semantics as weights).
- [ ] 3.3 Offline harness differential (lane-level) + live differential
       batch (generalization + testset + replay + TTFT).
- [ ] 3.4 Default-on only after zero-new-signature replay and TTFT
       regression < 10%.

## Step 4 — page cache + freshness

- [ ] 4.1 `web_page_cache` table + day-keyed TTL; hits recorded in the web
       lane trace.
- [ ] 4.2 Freshness footer (`数据截至 …` from pack as_of + web snapshot
       timestamps) + trace field.
- [ ] 4.3 Evidence: cold-batch TTFT variance, cache hit rate, replay.

## Step 5 — incremental refresh (staged)

- [ ] 5.1 `(canonical_object_id, content_sha256)` diff → partial FTS
       update; idempotence test.
- [ ] 5.2 Wire into the periodic full-rebuild flow (boring full rebuild
       remains the default path).
