## ADDED Requirements

### Requirement: Tier-2 auto-merge excludes DOI-conflict groups

The Tier-2 auto-merge SHALL exclude any candidate group whose live members carry ≥2 distinct
non-null **publisher** DOIs; a DOI-conflict group (e.g. a conference paper and its journal extension
sharing an exact title + identical author list but with distinct publisher DOIs) routes to Tier-3
review instead of being auto-merged. Preprint DOI prefixes (`10.48550/arxiv.`, `10.2139/ssrn.`,
`10.5194/egusphere-`) are excluded from the publisher-DOI count so legit preprint↔published pairs
remain Tier-2-eligible. (Tier-3 review is owned by `duplicate-paper-review-workflow`.)

#### Scenario: DOI-conflict group routes to Tier-3, not auto-merged

- **GIVEN** a group with an exact title + identical author list but two distinct publisher DOIs
  (e.g. a conference paper and its journal extension)
- **WHEN** the Tier-2 candidate SQL runs
- **THEN** the group is excluded from Tier-2 auto-merge and routed to Tier-3 review

#### Scenario: Preprint↔published pair stays Tier-2-eligible

- **GIVEN** a group with one publisher DOI and one arXiv/SSRN/egusphere preprint DOI
- **WHEN** the Tier-2 candidate SQL runs
- **THEN** the group remains Tier-2-eligible (preprint DOIs whitelisted)

### Requirement: Canonical-correction flip for conference↔journal over-merges

The system SHALL correct a confirmed conference↔journal Tier-2 over-merge by flipping the canonical
from the conference to the journal version (View B: one work, journal as the visible record), in one
transaction under a real `run_id`:

1. **reversing** the `paper_merge_alias` (delete the old `journal→conference` alias; upsert
   `conference→journal`, reason `exact_title_dedup_canonical_correction`);
2. **promoting** the journal (`identity_status='confirmed'`, `quality_status='ready'`) and
   **demoting** the conference (`identity_status='merged'`, `quality_status='rejected'`);
3. **un-rejecting** the journal's `professor_paper_link` (its own clean evidence is intact) and
   **rejecting** the conference's link (`rejected_reason='merged_into_canonical:<journal>'` — the
   migrated/contaminated evidence becomes invisible on the hidden conference row);
4. **refreshing** Milvus (delete the conference's chunks, index the journal).

The flip SHALL be idempotent (detect-and-skip if already corrected) and reversible.

#### Scenario: Flip makes the journal retrievable and hides the conference version

- **GIVEN** a Tier-2 over-merge with the conference = `confirmed/ready` (retrievable) and the
  journal = `merged/rejected` (hidden), the journal's link intact-but-rejected
- **WHEN** the canonical-correction flip runs
- **THEN** the journal becomes `confirmed/ready` with its link `verified` (clean evidence, no
  migration suffix); the conference becomes `merged/rejected` with its link rejected; the alias
  points `conference→journal`; retrieval returns the journal and not the conference

#### Scenario: Flip is idempotent

- **GIVEN** a group already flipped (alias `conference→journal` present, conference merged)
- **WHEN** the flip runs again
- **THEN** it is a no-op (zero counts)
