## ADDED Requirements

### Requirement: Tiered paper duplicate-merge strategy

The system SHALL deduplicate paper rows by a tiered confidence model:
- **Tier 1 (identifier-anchored, deterministic):** rows sharing a DOI / arXiv /
  OpenAlex ID are the same paper — merge with zero false-positive risk. (Enforced
  by the DB unique constraint + Phase-2 ingest-dedup; no active merge needed.)
- **Tier 2 (exact-title + identical author list, high-confidence):** rows sharing
  an exact (case-insensitive) title AND a single author list across the group
  are merged automatically (this change).
- **Tier 3 (exact-title + divergent authors, ambiguous):** NOT auto-merged —
  review-gated (owned by `duplicate-paper-review-workflow`).

#### Scenario: Tier 1 is enforced by constraint
- **GIVEN** two paper rows with the same DOI
- **WHEN** the DB constraint is applied
- **THEN** they cannot coexist as separate non-merged rows (identifier uniqueness)

### Requirement: Tier 2 auto-merge preserves attribution

For each Tier 2 group, the system SHALL pick a canonical member (identifier-bearing
preferred, else richest) and merge every other member into it by:
1. **migrating** each non-canonical member's `professor_paper_link`s onto the
   canonical (upsert by `(professor_id, canonical_paper_id)`, preserving
   `link_status`/evidence/evidence_page_id) — so no professor↔paper edge is lost;
2. writing `paper_merge_alias(old→canonical, reason='exact_title_dedup')`;
3. rejecting the old member's `professor_paper_link`s (link_status='rejected',
   reason `merged_into_canonical:<canonical>`);
4. marking the old member `identity_status='merged'`, `quality_status='rejected'`.

#### Scenario: A co-authored duplicate group collapses to one canonical
- **GIVEN** 3 paper rows with identical title + identical author list, linked to
  professors A, B, C respectively
- **WHEN** Tier 2 merge runs
- **THEN** 1 canonical remains; professors A, B, C links are all on the canonical;
  the 2 non-canonical rows are `identity_status='merged'` + their old links rejected

#### Scenario: Canonical pick prefers the identifier-bearing member
- **GIVEN** a Tier 2 group where one member has a DOI and the others do not
- **WHEN** the canonical is picked
- **THEN** the DOI-bearing member is the canonical (deterministic, richest)

### Requirement: Tier 2 is pilot-gated with a false-merge check

Before the full apply, a bounded pilot (sample of groups) SHALL run in dry-run
and report: group count, rows, canonical picks, and an adversarial title-match
check (every member's title ≈ the canonical's title). The full apply proceeds
only after the pilot shows 0 false-merges in the sample.

#### Scenario: Pilot blocks the full run on a title mismatch
- **GIVEN** a pilot group where a member's title differs significantly from the
  canonical's
- **WHEN** the pilot's adversarial check runs
- **THEN** the group is flagged and the full apply does NOT proceed without review

### Requirement: Merged rows are excluded from retrieval

A merged paper row (`identity_status='merged'`) SHALL be excluded from Milvus
indexing and from retrieval candidate SQL (via the existing `_is_indexable_paper`
`identity_status not in {rejected,merged}` filter + `paper_merge_alias` LEFT JOIN
exclusion). Retrieval resolves the canonical via `resolve_canonical_paper_id`.

#### Scenario: A merged row is not indexed
- **GIVEN** a row merged into a canonical (identity_status='merged')
- **WHEN** a Milvus backfill selects candidates
- **THEN** the merged row is excluded; the canonical (if ready) is indexed
