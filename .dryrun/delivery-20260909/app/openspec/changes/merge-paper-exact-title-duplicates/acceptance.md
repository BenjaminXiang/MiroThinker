# Acceptance: merge-paper-exact-title-duplicates

A change is accepted only when ALL of the following hold.

## Tier 2 selection + canonical pick
- [ ] Candidate SQL selects exactly the Tier 2 groups (exact title + single
      author-list, not rejected/merged); ~804 groups / ~2,135 rows.
- [ ] Canonical pick: identifier-bearing member preferred (725/804 have one);
      tie-breaks deterministic (richest > lowest paper_id).

## Attribution preservation (the invariant)
- [ ] Every non-canonical member's `professor_paper_link`s are migrated to the
      canonical BEFORE the old links are rejected (step 1 before step 3).
- [ ] No professor↔paper edge lost: the canonical's link count ≥ the sum of the
      group's pre-merge links (deduped by (professor_id, canonical)).

## Merge correctness
- [ ] `paper_merge_alias(old→canonical, reason='exact_title_dedup')` written for
      each non-canonical member; idempotent re-run (no duplicate alias rows).
- [ ] Old members `identity_status='merged'`, `quality_status='rejected'`.
- [ ] **0 `ready` papers degraded** (merged members were not the canonical; the
      canonical keeps its quality_status).

## Pilot gate (false-merge guard)
- [ ] Pilot (50 groups) dry-run: adversarial title-match — every member title
      sim≥0.99 vs canonical; 0 mismatches before the full apply.

## Retrieval
- [ ] Merged rows excluded from `_is_indexable_paper` (identity_status='merged');
      retrieval resolves canonical via `resolve_canonical_paper_id`.
- [ ] Spot-check: a merged group's professors all link to the canonical.

## Code quality / invariants
- [ ] No schema migration; `paper`/`paper_merge_alias`/`professor_paper_link` reused.
- [ ] No enum/`_is_indexable_paper` change; no A–G / `_VALID_DOMAINS` / evidence change.
- [ ] `uv run pytest` green; `just lint` clean.
- [ ] `openspec validate merge-paper-exact-title-duplicates --strict` exits 0.

## Evidence to report
- Pilot JSONL (0 false-merges), apply counts, retrieval spot-check, unit tests.
