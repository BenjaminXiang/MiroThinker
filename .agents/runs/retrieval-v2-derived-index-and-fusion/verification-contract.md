# Verification contract: retrieval-v2-derived-index-and-fusion

> Created before production-code edits (OpenSpec config rule). RED artifacts
> come from the acceptance criteria in `acceptance.md`; GREEN evidence is
> listed per step with its oracle strength.

## Oracles (strongest first)

1. **Replay gate** (`apps/admin-console/scripts/replay_fix_round1.py`,
   7 sessions × repeats): scenario replay, zero new signatures vs
   `replay-post-lat3` (ALL PASS).
2. **Generalization probes** (`probe_generalization.py` + checker): property
   checks P1 (no fabrication) / P2 (coverage precision) / P3 (shape); P2
   off-category counts are the primary RED metric for Step 1/2.
3. **Workbook testset** (`run_testset.py`, g2/g5): entity coverage layers.
4. **Live latency probe** (`probe_latency.py`) + turn-debug lane timings:
   wall-time budgets.
5. **Offline harness** (`latency/latency_harness.py`, production components,
   no live network noise): lane-level stages, same-day comparisons.
6. **Unit/contract tests** (agent app): tokenization matrix, field weights,
   facet predicates, RRF determinism, artifact binding/fallback.

## Frozen baselines (2026-09-12, deployed eced3c83 semantics)

- TTFT r4: 24.42 / 14.59 / 19.77 / 15.62 / 17.47 / 15.41 / 11.14 s.
- Lane walls (live): lexical 0.92-3.54s; exact 0.12-0.55s; vector
  3.19-5.39s; web 6.86-11.16s.
- Generalization r5 P2: lidar off 25/64 and 18/64; storage off 9/56;
  drone 0; medical 0.
- Testset: g2 3/3; g5 entity 2/2. Replay: ALL PASS (`replay-post-lat3`).

## Step RED → GREEN

### Step 1 — derived lexical index

- **RED (unit, deterministic)**: `test_lexical_index.py` — segmentation
  matrix (大疆/优必选/则成电子/PCB打样/别名/城市前缀), field weights
  (name > tags > body), OR semantics (multi-term query is a ranked sample),
  manifest mismatch refusal, missing-artifact fallback, sealed-pack
  untouched (build into a temp copy; pack hashes compared).
- **GREEN (behavioral)**: live A/B batch (switch on/off) —
  lexical lane P95 < 150 ms; lidar off ≤ 12, storage off ≤ 4; g2 3/3 and
  g5 entity 2/2 unchanged; replay zero new signatures; TTFT regression
  < 10%.

### Step 1b — pool + relevance-model rerank (revised 2026-09-13)

Owner directive: the site now serves a dedicated cross-encoder
(`qwen3-reranker-8b`, `:18006`); the embedding model stays the vector lane's
job. Two placements are in scope: (a) index pool → window selection inside the
laned path, (b) final serving ordering — the same model orders candidates
*inside* the preserved local/current-Web buckets of `_serving_reranker`
(switch-gated by `CANONICAL_V2_RERANK_BASE_URL`; unset = today's behaviour).

- **RED (unit, deterministic)**: `test_rerank_client.py` — request shape,
  index-realignment, malformed/duplicate/out-of-range/non-finite payloads,
  401/transport wrap, document cap, empty input, log redaction (no query, no
  candidate text, no credential). `test_serving_rerank_model.py` — model
  ordering inside buckets, local/Web balance preserved, unscored candidates
  behind scored ones, failure → deterministic order, no config → deterministic
  order, real-endpoint payload shape.
- **GREEN (behavioral, live A/B, lexical OFF on both sides so only the model
  changes)**: testset g2 3/3 + g5 2/2; generalization P2 not worse than the
  same-day OFF baseline; replay zero new signatures; TTFT within the same
  ±10% band; rerank call wall time measured per turn (cap ≤ 3 s, expected
  ~0.2 s at 128 documents).
- **GREEN (fault injection, live)**: instance pointed at a stub that returns a
  malformed payload, then at a closed port — every turn must still answer via
  the deterministic order, and the logs must carry endpoint/model/count/elapsed
  only.

### Step 2 — facets

- **RED (unit)**: facet predicate tests, geography-from-registered-address
  (深南电路 class passes 深圳; 北京-registered fails), contradiction/empty
  behavior.
- **GREEN (behavioral)**: live 深圳-narrowing turns (g2-t2 phrasing) return
  exactly the typed-field matches; no off-category widening on the
  generalization suite.

### Step 3 — RRF

- **RED (unit)**: synthetic-rank fusion order/determinism/quota-as-weight
  tests; fusion receipt contents.
- **GREEN (behavioral)**: offline harness differential + live batch; replay
  zero new signatures; TTFT regression < 10%.

### Step 4 — page cache + freshness

- **RED (unit)**: cache TTL/day-key behavior, freshness computation from
  as_of + snapshot times.
- **GREEN (behavioral)**: repeated-run cold-batch TTFT variance; cache-hit
  traces; replay wording unchanged except the as-of line.

### Step 5 — incremental refresh

- **RED (unit)**: diff → partial update; **GREEN**: partial artifact
  equals a full rebuild for the same inputs.

## Mock boundaries

- Unit tests mock the pack (constructed documents) and the judge; they do
  NOT stand in for retrieval-behavior claims.
- The offline harness reuses real production components (pack authority,
  planner/read/reranker/selector) with private cache copies; its numbers
  are reported with the harness deviation list.
- Live A/B requires the same-day differential rule (both sides run the same
  day; environment failures such as httpx errors are excluded, and the
  exclusion is named).
