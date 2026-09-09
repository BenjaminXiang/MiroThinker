# Change Log: harden-serving-test-harness

## 2026-09-10 — Change opened + A1/A1b/A2 landed

- Opened under the system-completion plan approved 2026-09-10.
- A1: three-layer judgment (entity / stance / completeness + provenance)
  rewritten into `run_testset.py`; 25/25 turns anchored, 5 previously
  unanchored turns curated and marked human-verified; `--offline` re-scoring
  mode added.
- A1b: `gap-registry.md` — all 16 gaps mapped to executable assertions;
  8 RED / 1 PASS data probes (`data_probes.py`), endpoint-side RED states
  recorded from the archived flash-systemd run.
- Judgment rebase: keyword 22/25 → three-layer 9/25 on the same archived
  answers; every FAIL maps to a gap; two anchor curation errors found and
  fixed (g9 博士生导师 alias; g5-t1 over-wide completeness set).
- A2: requirements matrix v1 (68 items, L0–L8) landed; L0–L4 fully judged
  (14 met / 22 gap / 30 pending / 2 non-goal overall).
- GAP-12 (stage-0 hit-rate targets) still pending user decision;
  provisional targets proposed in the gap registry.
- Remaining: A3 (test-env fixes), A4 (traffic pack-hit evidence).
