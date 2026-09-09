# Tasks: harden-serving-test-harness

## A1 Three-layer judgment + anchors

- [x] A1.1 Curate per-turn anchors: expected entities, forbidden entities,
       stance anchors (polarity + key facts), key-point sets from the
       workbook GT; fill the 5 unanchored turns (g6-t2, g8-t2, g9, g10,
       g14) marked human-verified.
- [x] A1.2 Rewrite scoring in `run_testset.py`: three layers (entity
       coverage / stance / completeness ≥80%); turn passes only when all
       applicable layers pass; keep `--offline <results.json>` re-scoring
       mode.
- [x] A1.3 Offline re-score archived JSONs; confirm g2-t2, g2-t3, g4-t2
       flip to FAIL and no genuine pass regresses. Record the table in
       `.agents/runs/harden-serving-test-harness/verification.md`.

## A1b 16-gap RED registry

- [x] A1b.1 Write `gap-registry.md`: 16 entries, each with assertion name,
       kind (runner/pytest/manual), current state (RED), evidence pointer.
- [x] A1b.2 Implement the runner-side assertions (GAP-01..09, 15 checkable
       via endpoint; GAP-13/14/16 via data probes).

## A2 Requirements matrix v1

- [x] A2.1 Derive L0–L4 items from the workbook + PRD docs; L5–L8 from the
       2026-09-10 plan; 68 items total.
- [x] A2.2 Score each L0–L4 item {met / evidenced-gap / non-goal} with an
       evidence pointer; leave L5–L8 pending with owners (stage B/C/F/G).
       (Landed with evidence-backed L5/L6/L8 rows scored too:
       14 met / 22 gap / 30 pending / 2 non-goal.)

## A3 Test-environment fixes

- [ ] A3.1 Milvus-deadlock tests: explicit timeout baseline in-test; no
       suite-level hangs.
- [ ] A3.2 admin-console: disposable-DB URL path so the real-data guard is
       satisfied without 122 errors.
- [ ] A3.3 Re-run the three canonical_v2 suites + admin-console; zero
       environment-class failures recorded in verification.md.

## A4 Traffic evidence (read-only analysis)

- [ ] A4.1 Measure pack hit rate on real traffic (access-log 462+696 turns
       vs current pack coverage); record the number as data-priority input.
