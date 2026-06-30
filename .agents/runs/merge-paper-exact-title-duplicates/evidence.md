# Evidence — merge-paper-exact-title-duplicates (Tier-2 paper dedup)

> Change applied 2026-06-29. Claude-owned operational evidence (tasks 2.1, 3.1, 3.2, 4.1).
> All counts DB-grounded against `miroflow_real` (localhost:15432); proxy vars unset.

## Verification-contract gates

| Gate | Result |
|---|---|
| Unit tests (fake-conn RED cases) | **6/6 passed** (`tests/scripts/test_run_paper_exact_title_dedup.py`, independent Claude re-run, 3.85s) |
| Pilot adversarial title-match | **0 false-merges** (`false_merge_count=0` over ALL groups, not just 50) |
| Merged rows excluded from indexing | **0** merged-this-run rows pass `_is_indexable_paper` |
| Alias reachability | member → canonical resolves via `paper_merge_alias` ✓ |

## Candidate-set reconciliation (921 vs 804 grounding)

The design §1 grounding SQL and the implemented candidate SQL differ by one clause
(the implemented SQL excludes `identity_status in {rejected,merged}` members from the
outer join, so `HAVING count(DISTINCT authors)=1` sees only live members). Live DB:

| Candidate SQL | groups | rows | identifier-bearing | merged/rejected members in groups |
|---|---|---|---|---|
| design §1 (grounding, reproduced live) | 804 | 2,135 | 728 | 512 |
| **implemented (script, live)** | **921** | **1,857** | **841** | **0** |

- design §1 reproduces **804 / 2,135** exactly → **DB did not drift** since grounding.
- implemented SQL is a **strict superset by groups**: 921 ⊇ 804 (all 804 preserved + 117 extra,
  **0 dropped**). The 117 extras are legit duplicate groups design §1 wrongly blocked because
  unrelated already-merged/rejected members had divergent author lists.
- implemented SQL includes **0 merged/rejected members** in any group → never re-merges an
  already-merged row. This is the correct/safer semantics. (User-approved 2026-06-29.)

## Apply (run_id `4a1c6a7a-b2ad-4264-9bf8-ce13aefae78f`, mode=apply)

| Metric | Value | Reconciliation |
|---|---|---|
| groups_total / rows_total | 921 / 1,857 | |
| groups_processed | 921 | |
| members_merged | 936 | = 1,857 − 921 canonicals |
| merge_aliases_written | 936 | DB `paper_merge_alias`: 29,742 → 30,675 (**+933**); 3 pre-existing aliases repointed (idempotent ON CONFLICT) |
| old_links_rejected | 936 | DB `professor_paper_link` rejected: 36,275 → 37,211 (**+936**) |
| links_verified | — | 65,786 → 64,861 (**−925**): redundant professor→duplicate edges consolidated on canonical (11 new inserts − 936 rejected) |
| false_merge_count | **0** | gate held through apply |
| ready_degraded | **15** | see below |
| DB `paper` merged | 31,303 → 32,239 (**+936**) | = members_merged ✓ |

## ready_degraded = 15 (review: ACCEPT)

- The merge set each non-canonical member to `quality_status='rejected'`. 15 of the 936 merged
  members were `ready` pre-merge → −15 net `ready` rows (23,432 → 23,417).
- Canonical readiness across 921 groups: **644 ready** (directly indexable), 277 non-ready
  (187 partial + 88 needs_enrichment + 2 rejected). Canonical pick = identifier-bearing > richest
  fields > lowest `paper_id` — `quality_status` is NOT a canonical-pick factor, so a ready member
  can land under a non-ready canonical.
- Retrieval impact: retrieval candidate SQL excludes `identity_status='merged'` and resolves via
  `resolve_canonical_paper_id`. A ready member under a non-ready canonical is therefore temporarily
  not directly indexable. Worst case ≤15 papers (0.06% of 23,417 ready) — **bounded, reversible**
  (`paper_merge_alias`), and **self-heals** when those 277 canonicals are promoted to `ready`
  (they are the richest/identifier-bearing members, i.e. the best promotion candidates).
- Decision: **accept**. Re-picking canonicals to `prefer ready` (a spec change to canonical
  criteria) is a clean follow-up but not worth an un-merge/re-merge for ≤15 papers.

## Retrieval spot-check (task 3.2)

- `merged-this-run` rows passing `_is_indexable_paper`: **0** ✓
- Alias reachability: `PAPER-F70FC6280E29 → PAPER-90C0AE30BC36` ✓
- 3 sampled multi-member groups: all merged members `identity_status='merged'`; canonicals carry
  the consolidated verified professor links (attribution preserved). ✓

## Follow-ups (out of this change's scope)

1. Canonical pick could add `prefer ready` to eliminate the temporary retrieval gap for future runs.
2. Optional Milvus `paper_chunks` re-backfill to drop stale merged-member chunks (spec scoped
   re-index as not-needed; retrieval resolves canonicals via alias either way).

## Artifacts

- `scripts/run_paper_exact_title_dedup.py` + `src/data_agents/paper/dedup_merge.py`
  + `tests/scripts/test_run_paper_exact_title_dedup.py` (Codex, reviewed accept).
- `.agents/runs/merge-paper-exact-title-duplicates/pilot.jsonl` (full dry-run, all 921 groups)
- `.agents/runs/merge-paper-exact-title-duplicates/apply.jsonl` (apply report)
- `.agents/runs/merge-paper-exact-title-duplicates/verification-contract.md`
