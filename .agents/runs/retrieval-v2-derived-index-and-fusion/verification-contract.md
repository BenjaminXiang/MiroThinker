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

## Measured outcomes (appended 2026-09-13; contract above kept as written)

- **Step 1 lexical index**: speed axis met (lane-internal 0.056–0.710 s vs
  0.9–3.6 s baseline), quality axis RED (g2 2/3, g5 1/2, replay 3 failures)
  → lane pinned OFF (`CANONICAL_V2_LEXICAL_INDEX=0`).
- **Step 1b(a) cross-encoder**: unit RED→GREEN (25 + 71 green); live ON/OFF
  differential → quality gate RED (testset 1/5 vs same-day OFF 4/5;
  generalization on-category loss 46→30 drone, 47→39 medical; replay clean vs
  same-day OFF runs). TTFT within budget on both arms (11.6–23.8 s); model
  wall 208 ms at the 128-document cap; ON proven real via the endpoint request
  counter (+128/turn). Lane OFF.
- **Step 1b.0b fault injection**: GREEN — malformed payload and refused
  connection each produced a complete answer with the deterministic fallback
  recorded and zero stream error events; served-journal scan (23,713 lines)
  shows 0 credential / 0 query / 0 candidate text. Restore to OFF verified
  by env inspection + `/api/health`.
- **Open**: 1b.0c (pronoun→person), 1b.1 (wide pool + bigram residue recall),
  1b.2 (embedding scoring over the pool), 1b.3 (recall + commit superset
  guard), 1b.4 (four-oracle default-on gate).

## G7 closure slice — RED/GREEN contract (2026-09-13, diagnosis-first)

Evidence basis: 26 archived 具身智能 turns (`diagnose_g7_recall.py` over
the turn-debug dir): 优必选 in-window 6/26 (rank ~37), commit 0/26; today's
3 replay runs: 0/3 in-window; r1/r3 passes were web-prose mentions with 0
优必选 citations. Code points: F1 sort key `knowledge_read_isolated.py:
8875-8883`; `expands` mechanism `:8705-8748` (PCB-only today); commit join
`knowledge_answer.py:2678-2700`; AQ-S2c sentence `:1339-1375`.

### RED definitions

- R1 (recall): offline F1 rank for 优必选 on the G7 query + 4 view variants
  — today: outside a top-32 cut in the majority of variants (record exact
  ranks first; the slice's RED asserts top-32 in ≥90%).
- R2 (commit): controlled turn where 优必选 IS in-window → commit universe
  lacks it today (assert presence; RED from the 6 historical in-window
  turns, to be re-derived on the current code before the fix).
- R3 (anti-masking): an answer whose only 优必选 mention is web prose
  without a local handle/citation must NOT count as green in the slice's
  acceptance.

### GREEN criteria

- Offline rank table (R1) meets the ≥90% top-32 bar; live replay G7 ×3: 3/3
  answers name 优必选 with a local handle committed or a local citation.
- Commit probe (R2): in-window → commit 3/3.
- No regression: G2/G5 enumeration turns, g2/g5 testset spot checks, lane
  cost <1 s, TTFT <30 s.

### Instrument-first notes

- The slice opens by re-deriving R2 on the CURRENT code (the 6 historical
  in-window turns may predate the present commit path) and by recording
  per-lane in-window diffs (which lane carries 优必选, where it is cut).
- The declaration update (`expands` family) is config-data: re-generate
  provenance (`generated_from.pack_sha256`) honestly; runtime parse is
  fail-closed on schema/shape only.
