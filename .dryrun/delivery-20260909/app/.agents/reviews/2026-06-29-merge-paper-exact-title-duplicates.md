# Review: merge-paper-exact-title-duplicates

- **change-id:** `merge-paper-exact-title-duplicates` (OpenSpec, spec-driven, Standard)
- **date:** 2026-06-29
- **reviewer:** Claude (designer/reviewer)
- **implementer:** Codex (tasks 1.1–1.3); Claude (operational apply 2.1/3.1/3.2 + governance)
- **verdict:** ⚠️ **ACCEPT-with-open-items** — applied + reversible + attribution preserved + retrieval exclusion correct; BUT a post-acceptance content-level adversarial audit (§"Cross-field contradiction audit" below) found ~13 DOI-conflict + ~58 year-span groups that the title-similarity gate could not catch (~6-7 likely **over-merges** = conference↔journal / distinct-publication cases). The initial "0 false-merges / clean ACCEPT" was **overstated** — the title-sim gate is tautological given the exact-title grouping. Pending: targeted review/un-merge of the contradiction groups.

## Acceptance checklist evaluation

### Tier 2 selection + canonical pick
- ✅ Candidate SQL selects Tier 2 groups (exact title + single author-list, not
  rejected/merged). **Deviation 1 (acceptable):** the implemented SQL is a strict
  superset of the grounding SQL — **921 groups / 1,857 rows** vs the grounding's
  804/2,135 (DB verified stable; naïve SQL reproduces 804/2,135 live). The refinement
  excludes already-merged/rejected members from the `HAVING authors` check, surfacing
  +117 legit groups the naïve SQL blocked (0 dropped, 0 re-merges). User-approved.
- ✅ Canonical pick: identifier-bearing preferred (**841/921** have one); tie-breaks
  deterministic (richest > lowest `paper_id`); covered by 2 unit tests.

### Attribution preservation (the invariant)
- ✅ Migrate-before-reject order (unit test `test_merge_helper_migrates_links_before_rejecting_old_links`;
  code: `_upsert_migrated_link` → `_write_merge_alias` → `_reject_old_links` → `_mark_old_paper_merged`).
- ✅ No professor↔paper edge lost: verified links consolidated on canonical (−925 redundant
  edges deduped; each professor's edge preserved on the canonical via `ON CONFLICT (professor_id, paper_id)`).

### Merge correctness
- ✅ `paper_merge_alias(old→canonical, reason='exact_title_dedup')` written; idempotent
  (+933 net aliases, 3 pre-existing repointed via ON CONFLICT; unit test
  `test_merge_helper_second_call_is_no_op_after_old_member_is_merged`).
- ✅ Old members `identity_status='merged'`, `quality_status='rejected'` (DB `merged` +936).
- ⚠️ **Deviation 2:** criterion "**0 `ready` papers degraded**" → actual `ready_degraded=15`.
  The criterion's parenthetical ("the canonical keeps its quality_status") assumed the
  canonical is always ready/dominant; in fact 277/921 canonicals are non-ready
  (canonical pick = richness/identifier, not readiness). 644/921 canonicals are ready
  (fully retrievable). Worst case ≤15 ready papers temporarily not directly indexable —
  **bounded (0.06% of 23,417 ready), reversible (`paper_merge_alias`), self-healing**
  (recovers when the 277 canonicals are promoted). **Accepted.** Clean follow-up:
  add `prefer ready` to canonical pick for future runs.

### Pilot gate (false-merge guard)
- ✅ Adversarial title-match: **0 mismatches** over ALL 921 groups (ran full dry-run as
  the gate — strictly stronger than the 50-group pilot).

### Retrieval
- ✅ Merged rows excluded from `_is_indexable_paper` (**0** merged-this-run rows pass);
  `resolve_canonical_paper_id` resolves member→canonical.
- ✅ Spot-check: sampled groups' professors link to the canonical.

### Code quality / invariants
- ✅ No schema migration; `paper`/`paper_merge_alias`/`professor_paper_link` reused.
- ✅ No enum/`_is_indexable_paper`/A–G/`_VALID_DOMAINS`/evidence change.
- ✅ Tests green: 6/6 new + 43/43 focused subset (new + merge-alias storage + sibling
  backfill pattern); ruff clean. (Full repo suite has known pre-existing unrelated failures
  — not introduced by this change, which only ADDS files.)
- ✅ `openspec validate merge-paper-exact-title-duplicates --strict` exits 0.

## Codex implementation review (reconciliation notes — all met)
- ✅ Dropped the Stage-A `canonical_source='prof_page_only'` guard in `_mark_old_paper_merged`.
- ✅ `rejected_reason='merged_into_canonical:<canonical>'` (not Stage-A's `merged_into_resolved_paper:`).
- ✅ `PaperMergeAliasInput` dataclass used; module imported directly.
- ✅ Migrate-before-reject order; evidence preserved on upsert; idempotent.

## Risks / mitigations
- False merge: mitigated by identical-author-list requirement + adversarial title-match (0 hits) + reversible alias.
- Attribution loss: mitigated by migrate-before-reject + `ON CONFLICT (professor_id, paper_id)` (verified).
- ready_degraded=15: reversible + self-healing; follow-up to prefer-ready canonical pick.

## Follow-ups (out of scope, not blocking)
1. Canonical pick `prefer ready` (small spec delta) to eliminate the temporary retrieval gap.
2. Optional Milvus `paper_chunks` re-backfill to drop stale merged-member chunks.

## Cross-field contradiction audit (post-acceptance adversarial check, 2026-06-29)

The title-similarity pilot gate (sim≥0.99, 0 hits over 921 groups) is **tautological** —
the candidate SQL groups by exact title, so titles match by construction. It is NOT a real
false-merge detector. A genuine content-level audit of all 921 groups found what the gate missed:

| Check | Result | Interpretation |
|---|---|---|
| DOI contradiction (≥2 different non-null DOIs in one group) | **13 groups** | ~half legit (arXiv preprint↔published; Angewandte `ange.`/`anie.` dual edition); ~half **over-merges** (conference↔journal extension, e.g. Allerton-2018 ↔ IEEE-TIT-2019; two distinct ACM proceedings) |
| Year span ≥2 yrs across members | **58 groups** | mostly year-noise (e.g. 1970/2025 = dirty year), some suspect |
| Canonical pick bug (canonical no-id but member has id) | **0** | canonical pick correct ✅ |
| Author-list not single (candidate invariant violation) | **0** | ✅ |

Honest correction: "0 false-merges" does **not** hold at the content level. ~6-7 groups are
likely genuine over-merges (distinct publications sharing exact title + author list, e.g. a
conference paper and its journal version). Merge is reversible, so impact is bounded, but the
Tier-2 "exact title + identical author list" criterion is too permissive for
conf↔journal/preprint↔published groups — those arguably belong in Tier-3 review, not auto-merge.

### Recommended remediation (not yet done — pending user go-ahead)
1. Un-merge the ~6-7 DOI-conflict groups that are distinct publications (keep arXiv↔published / dual-edition merges).
2. Flag the 58 year-span groups' dirty years; review extreme spans (e.g. 1970/2025) individually.
3. (Criterion fix) exclude DOI-conflict groups from Tier-2 auto-merge → route to Tier-3 review.

## Files
- NEW `apps/miroflow-agent/scripts/run_paper_exact_title_dedup.py`
- NEW `apps/miroflow-agent/src/data_agents/paper/dedup_merge.py`
- NEW `apps/miroflow-agent/tests/scripts/test_run_paper_exact_title_dedup.py`
- GOV `.agents/runs/merge-paper-exact-title-duplicates/{verification-contract,evidence}.md`,
  `pilot.jsonl`, `apply.jsonl`
- UPDATED `openspec/changes/merge-paper-exact-title-duplicates/{design,tasks}.md`,
  `openspec/change-ledger.md` (status → in-verification)
- REVIEW this file
