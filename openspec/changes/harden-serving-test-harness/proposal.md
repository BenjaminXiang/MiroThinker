# Proposal: harden-serving-test-harness

> Stage A of the system-completion plan approved 2026-09-10 (human docs:
> `docs/plans/2026-09-09-testset-baseline-and-repair-plan.md` §九/§十 and
> the 2026-09-10 plan). Agent-governed per AGENTS.md §3.
> Behavior-affecting: acceptance criteria and test infrastructure only —
> no serving-path behavior changes. No spec deltas: this change governs
> instruments, not capabilities.

## Why

The workbook score is not trustworthy evidence today:

- **GAP-10** — keyword-only checks passed turns whose answers were wrong or
  incomplete: g2-t2 (1 of 6 GT companies) PASS, g2-t3 (stance opposite to
  GT) PASS, g4-t2 (wrong legal-representative fact) PASS.
- **GAP-11** — five turns have empty 关键点 anchors (g6-t2, g8-t2, g9, g10,
  g14) and are scored on ad-hoc guesses.
- **GAP-12** — stage-0 hit rates (41%/50%/50%) have no target line, so
  "gap closed" is undecidable for retrieval-quality work.
- **L2 noise** — canonical_v2 suites carry 4 Milvus-deadlock timeouts + 1
  module-set drift; admin-console suites carry 122 real-DB-guard errors per
  run. Environment-class failures mask real regressions.

Until judgment is three-layer and each of the 16 gaps is an executable RED
assertion, "fixed" cannot be distinguished from "keywords happened to hit".

## What Changes

1. **Three-layer judgment** in the workbook runner
   (`.agents/runs/testset-baseline-20260909/run_testset.py`): per turn —
   ① entity coverage (curated expected/forbidden entities), ② stance
   consistency (polarity + key-fact anchors vs the workbook GT answer),
   ③ completeness (key-point coverage ≥ 80%). A turn passes only when all
   applicable layers pass. Re-scoring the archived 2026-09-09 result JSONs
   offline must flip g2-t2, g2-t3, g4-t2 to FAIL without re-running the
   service.
2. **Anchors for the 5 unanchored turns** (g6-t2, g8-t2, g9, g10, g14),
   curated from the workbook 答案 column and marked `human-verified`.
3. **16-gap RED registry**: every gap in evidence doc §九 maps to a named
   executable assertion (runner check or pytest) with its current RED state
   recorded; the registry lives at
   `.agents/runs/harden-serving-test-harness/gap-registry.md`.
4. **Requirements matrix v1** (L0–L8, 68 items): each item gets a status
   {met / evidenced-gap / non-goal} + evidence pointer (code path, data
   measurement, or endpoint run). L0–L4 (user-visible) completed first.
   Stored at
   `.agents/runs/harden-serving-test-harness/requirements-matrix-v1.md`.
5. **Test-environment fixes**: Milvus-deadlock tests get an explicit
   in-test timeout baseline; admin-console suites get a disposable-DB URL
   path so the real-data guard stops producing 122 errors.

## Impact

- `.agents/runs/testset-baseline-20260909/run_testset.py` (scoring rewrite)
- `.agents/runs/testset-baseline-20260909/anchors.py` (new, curated anchors)
- `.agents/runs/harden-serving-test-harness/` (gap registry, matrix,
  verification artifacts)
- `apps/miroflow-agent` test config (Milvus timeout baseline)
- `apps/admin-console` test config (disposable DB URL)

## Acceptance

- Offline re-score of archived result JSONs: g2-t2, g2-t3, g4-t2 flip to
  FAIL; all turns that were genuinely correct stay PASS (no
  over-tightening — verified against `results-ds-flash-systemd.json`).
- All 25 turns have anchors; the 5 new ones are marked human-verified.
- Gap registry has 16 entries, each with an executable assertion and a
  recorded RED state.
- canonical_v2 three suites + admin-console run with zero
  environment-class failures.
