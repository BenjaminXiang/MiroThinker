## ADDED Requirements

### Requirement: Professor paper evidence is an opt-in sidecar

The serving runtime MUST render professor paper evidence only when an overlay
file is configured via `CANONICAL_V2_PROFESSOR_PROJECTION`. With the variable
unset, absent, or pointing at an unreadable/malformed file, professor claims MUST
be identical to the behaviour without the overlay and the request MUST still
succeed.

#### Scenario: Overlay disabled

- **WHEN** the environment variable is unset
- **THEN** a professor claim contains no `论文数` and no `代表作`

#### Scenario: Overlay file is broken

- **WHEN** the variable points at a file that is not valid JSON
- **THEN** the overlay is disabled, a warning is logged once, and the claim is
  rendered as if the overlay did not exist

### Requirement: Existing pack values win

The overlay MUST NOT overwrite fields the pack already carries. A professor whose
document already has `paper_count` keeps that value.

#### Scenario: Pack already knows a count

- **WHEN** the professor document has `paper_count = 3` and the overlay says 90
- **THEN** the claim renders `论文数：3`

### Requirement: Ambiguous identities are excluded

Records flagged `duplicate_name` MUST NOT be applied, because two people sharing
a name cannot be distinguished by this evidence.

#### Scenario: Two professors share a name

- **WHEN** an allowlist record carries the `duplicate_name` flag
- **THEN** that professor's claim is rendered without overlay fields

### Requirement: Overlay adds count and representative papers

For an allowlisted professor with no pack values, the claim MUST include
`论文数：<n>` and up to three `代表作：《title》year` entries, using the Chinese
title when present.

#### Scenario: Allowlisted professor

- **WHEN** the professor is on the allowlist with `paper_count = 90` and four
  top papers
- **THEN** the claim contains `论文数：90` and exactly three `代表作` entries
