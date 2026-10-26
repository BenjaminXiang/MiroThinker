## ADDED Requirements

### Requirement: Overlay counts are labelled as local

A paper count injected from the projection overlay MUST render as
`本地收录论文：N 篇`, because it counts this pack's relationship graph, not a
publication total. A `paper_count` already present in the pack document MUST keep
the plain `论文数` label.

#### Scenario: Overlay-injected count

- **WHEN** the overlay supplies `paper_count = 4`
- **THEN** the claim contains `本地收录论文：4 篇`

#### Scenario: Pack-provided count

- **WHEN** the pack document already has `paper_count = 5`
- **THEN** the claim contains `论文数：5`

### Requirement: Repeated sentences collapse to one

When rendering a professor summary, a sentence repeated verbatim MUST appear once;
non-repeating text MUST be unchanged, and the result MUST still respect the claim
field limit.

#### Scenario: Template summary

- **WHEN** the summary is the same sentence three times
- **THEN** the claim shows it once

#### Scenario: Normal summary

- **WHEN** every sentence is distinct
- **THEN** the claim text is unchanged
