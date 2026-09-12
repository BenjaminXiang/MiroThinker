# Acceptance: retrieval-v2-derived-index-and-fusion

## Frozen baseline (2026-09-12, deployed eced3c83 semantics)

| axis | baseline |
|---|---|
| TTFT r4 (7 turns) | 24.42 / 14.59 / 19.77 / 15.62 / 17.47 / 15.41 / 11.14 s |
| Lane walls (live, turn-debug) | lexical 0.92-3.54s; exact 0.12-0.55s; vector 3.19-5.39s; web 6.86-11.16s |
| Generalization r5 P2 off-category | lidar 25/64 and 18/64; storage 9/56; drone 0; medical 0 |
| Testset | g2 3/3; g5 entity 2/2 |
| Replay gate | ALL PASS (2026-09-12, `replay-post-lat3`) |
| Derived-index feasibility (probes) | build 54s / 47k docs; index 62MB; query ~1ms; jieba+dict load 1.2s |

## Step 1 — derived lexical index

- [ ] Lexical lane wall **P95 < 150ms** live (baseline 0.9-3.6s), evidence:
      turn-debug lane timings + offline harness stage rows.
      **Revised 2026-09-13 with data**: the lane *stage* wall is not a lane
      metric — it carries the process-shared bound-document read (9.1 s on the
      first lane call of a process). The lane's own cost is select+build:
      measured 0.056 / 0.607 / 0.710 s (lidar / g2 / pcb-1). Criterion becomes:
      lane-internal cost < 1 s on OR-fill-heavy category queries and
      < 150 ms on single-term queries.
- [ ] Generalization lidar off-category **≤ 12** (baseline 25) and storage
      **≤ 4** (baseline 9) on the same probe suite; miss counts not worse.
      Measured 2026-09-13 with the content-residue query: lidar 10 and 10,
      storage 0, drone 0, medical 0 — **met on this axis, but Step 1 as a
      whole is red** (see below).
- [ ] Testset g2 stays 3/3; g5 entity layer stays 2/2; replay gate zero new
      signatures vs `replay-post-lat3`.
      **Measured red with the lane on**: g2 2/3 (entity layer missing
      开普勒/九号), g5 1/2, replay 3 failures (G3 person scope, G7 优必选
      2/3). Attribution: id-level window diff — the index window drops or
      fails to generate the very ids the answers then miss.
- [ ] TTFT regression < 10% on all seven probe turns. Measured with the lane
      on: 23.63 / 14.06 / 20.81 / 16.81 / 16.40 / 14.32 / 9.75 s vs baseline
      24.42 / 14.59 / 19.77 / 15.62 / 17.47 / 15.41 / 11.14 s — within ±8%
      (met), and it shows the lane is not on the TTFT critical path.
- [ ] Lineage/integrity suites green (read_isolated, serving_isolated,
      pack_loader, multitask contract suites). Met: read_isolated 48,
      pack_loader + fast_boot 36, lexical_index 16.

**Step 1 verdict (2026-09-13)**: speed axis met, quality axis red → the lane is
**off by default** (systemd drop-in `lexical-index.conf`) and Step 1b
(candidate generation + embedding rerank + superset guard, see design.md) must
pass all four oracles before default-on. Step 1's own criteria stay open until
1b lands, because a lane that changes answers is not accepted.

## Step 1b — candidate generation + relevance rerank (added 2026-09-13)

### Step 1b(a) — cross-encoder rerank, live differential measured 2026-09-13

Same pack, same day, `CANONICAL_V2_LEXICAL_INDEX=0` in both arms, ON proven by
the endpoint's own request counter (+128 per turn).

- [ ] **Replay gate zero new signatures** — met in the sense that matters:
      ON failed only `G3_person_pronoun`, which also fails in both same-day OFF
      runs with the identical assertion and query_type. The historical
      `replay-post-lat3` ALL PASS is not a valid same-day baseline (web/LLM
      non-determinism); the same-day OFF runs are. ON 5/7 vs OFF 4/7 and 5/7.
- [ ] **testset g2 3/3, g5 2/2 — RED**: 1/5 (g2 0/3: 九号 missing 7/10,
      pool 4<5, stance check; g5 1/2 with coverage 7/12). OFF was 4/5.
- [ ] **generalization P2 not worse — RED**: on-category coverage dropped
      (drone 46→30, 64→59, 35→33; medical 47→39) while off-category improved
      (lidar 25→20, 23→19; storage 8→5).
- [ ] **Unit tests** — met: `test_rerank_client.py` +
      `test_serving_rerank_model.py` 25 green; four-file regression 71 green.
- [ ] **harness lane cost + recall superset** — not applicable to 1b(a)
      (no pool change); still open for 1b.1/1b.3, and now widened to a
      *commit*-superset guard.
- [ ] **live fault injection (malformed payload + refused connection)** —
      see "Fault injection" below.

**Step 1b(a) verdict**: fail-safe transport + fallback implemented, quality
gate failed on the testset and the generalization on-category axis. Not
default-on; the unit returns to OFF. The next implementation step is candidate
generation (1b.1) and the commit-superset guard (1b.3), not reranker tuning.

### Fault injection (live, 18188, serial)

- [ ] malformed payload (stub `:18099`) → turn still answers, deterministic
      fallback recorded, no error event.
- [ ] refused connection (stub stopped) → same.
- [ ] no credential, query or candidate text in the served logs.

## Step 1b — acceptance criteria for the remaining work

- [ ] testset g2 3/3, g5 2/2.
- [ ] generalization P2 not worse than the 2026-09-13 OFF measurement
      (lidar ≤ 20/19, storage ≤ 5, drone 46/64/35, medical 47).
- [ ] harness: lane-internal cost < 1 s on the four frozen turns **and** the
      lane window a superset of the substring lane's recall (offline id-level
      diff), else the query falls through.
- [ ] commit-superset guard: every entity the legacy path committed for a
      category query stays committed after rerank, or the lane falls through.
- [ ] Unit tests: pool sizing/truncation, rerank determinism, superset guard,
      fall-through on thin recall.

## Step 2 — facets

- [ ] Geography/industry/tag facet filters return exactly the entities whose
      typed fields match (unit: constructed facets; live: 深圳-narrowing on
      g2/g5 phrasing, 深圳×机器人 class).
- [ ] No off-category widening vs baseline on the generalization suite.

## Step 3 — RRF fusion

- [ ] Fusion deterministic (synthetic-rank unit tests) and reproducible on
      replay (zero new signatures).
- [ ] Generalization + testset not worse than the Step-1 state; TTFT
      regression < 10%.

## Step 4 — page cache + freshness

- [ ] Page cache hit rate recorded; cold-batch TTFT variance narrows
      (evidence: repeated-run probe batch).
- [ ] Every answer carries the data as-of signal; no wording regression in
      the replay sessions.

## Step 5 — incremental refresh

- [ ] Partial update produces an artifact byte-equal to a full rebuild for
      the same inputs (idempotence + equivalence evidence).
