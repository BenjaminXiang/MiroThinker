## ADDED Requirements

### Requirement: Deep Enumeration Fetch

Enumeration-shaped web-lane requests SHALL fetch the full text of the top-8
organic results (non-PDF) and carry up to 2400 characters of fetched body
into the evidence snippet, so listicle contents survive into synthesis.

#### Scenario: listicle body reaches synthesis

- **WHEN** an enumeration query's top results include a listicle page whose
  company list starts beyond character 1200
- **THEN** the fetched evidence still contains the list entries

### Requirement: One Refinement Round for Thin Enumerations

When an enumeration-shaped request's round-1 merged results carry fewer than
6 organization-looking entries, the web lane SHALL issue exactly one refined
view set（"{original} 榜单/名单/盘点" variants）, fetch its top results, and
merge them with round-1 evidence. Total search rounds SHALL NOT exceed 2,
and every round-2 search flows through the quota counters.

#### Scenario: thin round-1 triggers refined round-2

- **WHEN** round 1 returns 3 org-looking results for an enumeration query
- **THEN** a refined query set is issued (observable as round-2 views in the
  turn trace's web outcomes)
- **AND** the merged evidence includes round-2 results when they resolve

#### Scenario: rich round-1 skips refinement

- **WHEN** round 1 already yields >= 6 org-looking results
- **THEN** no round-2 searches are issued (provider call count unchanged)
