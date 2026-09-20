# Verification contract — slice B: read the receipt instead of recomputing

Change: `reduce-rebuild-validation-cost` (step 2, read side). Branch:
`feat/connect-collection-line` (worktree `.worktrees/collection-line`), because that
is the tree the live line points at.
Upstream: `docs/plans/2026-09-20-boot-hash-reader-audit.md` (reader audit),
`docs/plans/2026-09-20-boot-cost-attribution.md` (71% of boot = serialize + hash).

## What this slice changes

Three boot-time sites recompute a hash from a pydantic `model_dump` although the
sealed pack manifest already carries the identical value. Slice B reads the receipt
instead of recomputing it:

| # | site | today | after |
|---|---|---|---|
| B1 | `serving_pack_loader.py:1818` (`create_serving_pack_query_planner`) | `_canonical_sha256(index_request.model_dump(mode="json"))` | `authority.manifest.index_projection_request_sha256` |
| B2 | `serving_pack_loader.py:1966` (`create_serving_pack_knowledge_read`) | `iso._canonical_sha256(relationship_request.model_dump(mode="json"))` | `manifest.relationship_request_sha256` |
| B3 | `complete_candidate_runner.py:799` (`_compose_pack_consumer_runtime`) | `_canonical_sha256(...)` | the same manifest receipt |

Shown by the audit to be the same fact recomputed up to four times, with the
handoff already carrying the manifest's value (`complete_candidate_runner.py:1019-1023`).

## Done when (each carries its own check)

1. **Equivalence, measured — not assumed.** Before any production edit, a probe opens
   the real sealed pack and proves the recomputed string is byte-equal to the manifest
   receipt, for every value slice B stops computing — including the `exclude_unset`
   variant the loader's own check uses, because the planner/receiver dumps *without* it.
   → `verify:` probe output `ALL EQUAL` over all compared values.
2. **The receipts still exist and are still verified.** Slice B removes *recomputation*,
   never the check that makes the receipt trustworthy: the pack's per-file hashes and
   the two `reproduce its recorded hash` checks at `:919`/`:1000` stay.
   → `verify:` both checks still present and still exercised by a booting pack.
3. **No external semantics change.** The values that reach bindings, traces and
   evidence are byte-identical before and after.
   → `verify:` replay 7/7; the two verbatim probes unchanged; TTFT unchanged.
4. **Boot gets measurably faster** and the profile confirms the sites went quiet.
   → `verify:` scratch boot (18199, same argv, isolated state dirs) timed before/after,
   plus a fresh py-spy profile showing the three sites gone from the top frames.
5. **Contract tests still green** for the loader/knowledge_read/runner suites, and the
   full admin-console + miroflow-agent failure sets are unchanged.

## Not in this slice (recorded)

- The two `open_serving_pack_authority` checks themselves (12.7%) — that is slice A
  (parser/schema version binding), which needs a pack-manifest field and therefore a
  contract change.
- `_ContentModel` construction-time self-hashing — slice C, needs its own design.
- The seal-side (`envelope_validate`, 2071s) twin of the same recomputation.

## Rollback

Three single-line substitutions in two files; revert the commit. No schema, no data,
no pack change.

---

## Result (2026-09-20)

| check | outcome |
|---|---|
| equivalence probe on the real sealed pack | **8/8 EQUAL** — including the dump WITHOUT `exclude_unset` the two call sites used |
| the two receipt checks | untouched (`serving_pack_loader.py:921`, `:1002`) and still exercised by a booting pack |
| contract tests | 357 passed / 1 failed; the failure is this worktree's own `config/managed/settings.json` pinning `chat_llm_profile`, reproduced with the change stashed |
| perf, mechanism | the three sites measure **exactly 0 samples** after (7.2% / 6.6% / 6.8% before); the untouched checks are unchanged in absolute terms (7,205 → 7,158 samples) |
| perf, wall clock | same protocol: **642 s → 450 s (−192 s, −30%)** |
| live line | restarted and re-verified (see the round-20 log) |

Caveat carried forward: the after run had a warmer page cache for the 4.1 GB pack,
so the wall-clock delta is an upper bound; the sample-level attribution is
cache-independent and is the load-bearing evidence.

Slice A's territory is now quantified from the same run: `open_serving_pack_authority`
holds **63.5% of the remaining 451 s ≈ 288 s**.
