# Change log: patent-company-relationship-reprojection (C1)

Append-only. One entry per slice round.

## 2026-09-15 — diagnosis + fix + D0 reconciliation (round 1)

- **Diagnosed** (design.md §1): the run15 relationship layer lost 7,042 → 123
  applicant bindings at the *seed* stage, not in the projection.
  `relationship_projection_result` shows `candidates=123 / admitted=123 /
  rejected=0`, and the completeness guard `len(current_relationships) ==
  len(links)+len(typed_seeds)` holds with `typed_seeds = 124`.
  122 of the 123 edges carry `match_kind=resolved_binding` — precisely the
  bindings whose patent *and* company are `s12a-released-objects-full-v1` rows.
- **Root cause**: `_typed_relationship_seeds` indexed raw landed rows by
  `payload["id"]`; only the released-objects source lands in released-object
  shape, the 12 supplemental batches keep `patent_id` / `company_name`, and the
  released-object shape synthesized for them by `_merge_p4_created_rows` lives
  in `row_by_object`, which never reached the relationship authority.
- **Fixed**: `_map_public_authority` returns `row_by_object`;
  `_relationship_seed_object_rows` is the single universe helper;
  `_typed_relationship_seeds(object_rows_by_id=…, supplemental_rows=…)`.
- **Added (D0)**: `_reconcile_patent_company_bindings` prints
  `PATENT_COMPANY_BINDING_LEDGER` and raises when a document binding with
  admitted endpoints produced no seed.
- **Verified**: 7 new/updated unit tests green; run15 replay (read-only) gives
  pre-fix 122 / post-fix 7,611 edges with 7,489 → 0 missing document pairs, and
  the reconciliation rejects the pre-fix state and accepts the post-fix state.
- **Not done**: no rebuild (run16 owns it); person-graph types
  (`patent_has_inventor`, `paper_has_author`) left empty (different cause:
  `person_projections = 0`).
- Commits: `d5e1828d` (fix + tests + OpenSpec change), `097625e1` (evidence +
  human docs), `58405450` (test call sites for the new parameter).
