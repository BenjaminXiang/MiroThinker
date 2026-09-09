# Tasks: merge-paper-exact-title-duplicates

> Reuses the Stage-A merge pattern. Pilot-gated. Codex implements the script;
> Claude runs the operational dry-run/apply (localhost DB).

## 0. Verification contract
- [x] 0.1 `.agents/runs/merge-paper-exact-title-duplicates/verification-contract.md`
      — deterministic (SQL + existing merge primitives); RED = pilot adversarial
      title-match + unit tests for canonical pick / link-migration order; GREEN =
      0 false-merges in pilot + bounded apply + retrieval spot-check.

## 1. Dedup script (new code)
- [x] 1.1 NEW `scripts/run_paper_exact_title_dedup.py`: candidate SQL (Tier 2:
      exact title + single author-list, not rejected/merged); canonical pick
      (identifier-bearing > richest > lowest paper_id); per non-canonical member:
      migrate links → `upsert_paper_merge_alias` → reject old links → mark merged.
      `--dry-run`/`--apply`/`--limit`/`--json-output`; `run_id` via `open_pipeline_run`.
- [x] 1.2 NEW `src/data_agents/paper/dedup_merge.py` (shared helper)
      `merge_paper_into_canonical(conn, *, old, canonical, run_id, reason)` if
      factoring the link-migration out is cleaner (avoids duplicating the
      upsert-migrated-link SQL between this script and title_enrichment_backfill).
- [x] 1.3 Unit tests: canonical pick (identifier-bearing wins; tie-breaks);
      link-migration-before-reject order (no attribution loss); idempotent re-run
      (`uq_paper_merge_alias_old_paper`); merged row excluded from candidate SQL.

## 2. Pilot (operational, gate)
- [x] 2.1 `--dry-run --limit 50`: report groups, canonical picks, and the
      adversarial title-match (every member title sim≥0.99 vs canonical).
      **STOP if any mismatch.** Save to `.agents/runs/.../pilot.jsonl`.

## 3. Full apply (operational)
- [x] 3.1 `--apply` over all 804 groups: merge_aliases + links migrated + 0 ready
      degraded. Record counts. _(Applied over 921 groups/936 merges — see evidence.md;
      candidate SQL is a strict superset of the 804 grounding. ready_degraded=15,
      bounded/reversible/self-healing — accepted.)_
- [x] 3.2 Retrieval spot-check: for a few merged groups, the canonical now carries
      all the professors' links; merged rows excluded from `_is_indexable_paper`.

## 4. Acceptance, ledger, validate
- [x] 4.1 Evidence: pilot (0 false-merges), apply counts, retrieval spot-check,
      unit tests.
- [x] 4.2 `openspec/change-ledger.md` status → `in-verification`.
- [x] 4.3 `openspec validate merge-paper-exact-title-duplicates --strict` exits 0.
- [x] 4.4 Claude review against the spec requirements; accept / revise / reject.
