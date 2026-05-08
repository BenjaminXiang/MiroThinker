# Sweep slice w13-V3-intent-benchmark-archive — ESCALATED

**Sweep slice outcome:** escalated (per spec §10.3 — classifier code under active drift; benchmark would measure phantom uncommitted state)
**Date:** 2026-05-08
**Spec read:** `.agents/specs/2026-05-02-w13-V3-intent-benchmark-archive.md`

## Reported case

Previous benchmark run returned 0.000 accuracy because LLM was unreachable in
sandbox. `docs/index.md` Agentic-RAG row lists `host 复跑 100-case` as #1
next-priority. Production classifier accuracy is currently unknown.

## Why escalated

`apps/admin-console/backend/api/chat.py` (classifier implementation) has
**1331 line insertions + 91 deletions** in the working tree. The drift
introduces a substantial new layer:

```
+def _classify_query_by_rules(query: str) -> dict[str, str] | None:
+    reason="out-of-scope deterministic rule"
+    reason="knowledge question deterministic rule"
+    reason="context-dependent cross-domain deterministic rule"
+    reason="multi-domain aggregate deterministic rule"
+    reason="exact patent deterministic rule"
+    reason="ambiguous paper title deterministic rule"
```

This is a deterministic pre-LLM classification layer that materially changes
classifier behavior. Running the benchmark now measures the **uncommitted
working-tree state**, not any version anyone can re-derive from git history.

Additionally, `apps/admin-console/tests/test_classifier_benchmark.py` has
17 lines of drift — possibly accommodating the new rule layer's output shape.

Per pattern-repair §2 hard rule: **"Never claim a verification command passed
unless it ran successfully in the current session."** Per spec §10.3:
**"Larger → escalate to a separate `.agents/specs/` plan."**

A benchmark result tied to a phantom code state is worse than no benchmark — it
gives false confidence with no reproducibility.

## Sibling search

- **Lane 1 (admin-console)**:
  - `chat.py`: 1331+/91- drift, includes new `_classify_query_by_rules` deterministic layer
  - `test_classifier_benchmark.py`: 17 lines drift, likely adapting to rule layer
  - Fixture intact: `tests/fixtures/intent_classifier_benchmark.jsonl` — 100 cases, distribution A=50/B=20/C=15/D=5/E=5/F=3/G=2 matches spec ✅
- **Lane 2 (canonical/contracts)**: not searched — drift on Lane 1 already blocks
- **Lane 4 (docs)**: `docs/architecture-decisions/ADR-008-intent-benchmark-ci-gate.md` exists with skeleton (Context / Options / Recommendation / Decision Notes / Follow-up sections) — ready to fill once benchmark runs cleanly

## What this slice actually needs to proceed safely

Two stages, in this order:

1. **Stage A — drift coordination**: drift owner reviews their `chat.py` rule-layer additions, commits or reverts, gets working tree clean on `chat.py` + `test_classifier_benchmark.py`.
2. **Stage B — benchmark execution**: with clean working tree and Gemma-4 reachable, run:

   ```bash
   cd /home/longxiang/MiroThinker/apps/admin-console
   unset https_proxy HTTPS_PROXY
   DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_mock \
     uv run pytest tests/test_classifier_benchmark.py -m requires_classifier_llm -v --tb=short \
     | tee /tmp/intent_benchmark_2026-05-XX.log
   cp /tmp/intent_benchmark_2026-05-XX.log docs/source_backfills/intent-classifier-benchmark-2026-05-XX.log
   ```

3. **Stage C — fill ADR-008** with overall accuracy, per-class accuracy,
   misclassified samples, and systemd-vs-GH-Action recommendation.

These cannot run in parallel.

## Defect class (final)

- **L5** (Routing/Classification Drift verification gap) + **C1** (test-matrix gap on classifier)
- Compounded by **operational hazard**: 1331-line uncommitted classifier-layer drift on the very file under benchmark

## Recommended next action

Suggested escalation spec slug:
`.agents/specs/2026-05-08-w13-V3-impl-escalated.md`

Skeleton:
```md
---
status: blocked-on-drift
blockers:
  - apps/admin-console/backend/api/chat.py has 1331+/91- unstaged drift
    introducing _classify_query_by_rules deterministic layer
  - apps/admin-console/tests/test_classifier_benchmark.py has 17 lines drift
related_review: .agents/reviews/2026-05-08-sweep-w13-V3-escalated.md
---

# W13-V3 implementation (escalated from sweep)

## Stage A: drift coordination
- Verify rule-layer additions are intentional and committable
- Add tests for new deterministic rules (currently no test coverage of them)
- Commit chat.py + test changes together

## Stage B: benchmark execution per `.agents/specs/2026-05-02-w13-V3-intent-benchmark-archive.md`

## Stage C: ADR-008 fill
```

I am NOT writing this escalation spec automatically because Stage A requires
human judgment about the rule-layer drift's commit-readiness AND additional
test coverage decisions for the new rules.

## Files touched by this slice

None — escalation only. No code changes, no fixture changes, no doc changes.

## Verification

- Fixture integrity: ✅ verified 100 rows, expected_type distribution matches spec (A=50/B=20/C=15/D=5/E=5/F=3/G=2)
- Test marker present: ✅ `@pytest.mark.requires_classifier_llm` at line 88
- Benchmark execution: **NOT RUN** — see "Why escalated" above

## Self-review

- Scope control: ✅ stopped at boundary; did not run benchmark on phantom code state; did not write into drifted files
- Invariants preserved (data-agent contract, A–G semantics, _VALID_DOMAINS, evidence shape, V001–V018, secrets boundary): ✅ no code touched
- Patch-only risk: N/A — no patch made
- Rollback / checkpoint: nothing to roll back

## Skip-but-note epilogue

Sibling risk: the new `_classify_query_by_rules` deterministic layer has
**no test coverage in the drifted test file** (the 17 line drift on
test_classifier_benchmark.py is too small to cover 6 new rules). If Stage A
commits the rule layer without adding rule-level unit tests, this becomes a
**latent C1 (test-matrix gap)** that will surface as a future regression.
Worth flagging to the drift owner before they commit.
