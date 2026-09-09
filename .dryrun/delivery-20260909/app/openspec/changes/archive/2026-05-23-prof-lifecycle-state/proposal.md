---
change_id: prof-lifecycle-state
type: feat (professor lifecycle separate from quality)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-15
canonical_input:
  - openspec/changes/prof-admin-workbench/
  - docs/Professor-Data-Agent-PRD.md
---

# Proposal: prof-lifecycle-state

## Why

`quality_status` should answer whether the collected data is
trustworthy. It should not also encode whether a professor is currently
active at a school, archived, or merged into another school record.
Keeping lifecycle and quality coupled makes non-current but well-sourced
records look like data-quality failures.

## What Changes

- Add a separate professor lifecycle state.
- Keep lifecycle out of professor quality evaluation except where
  lifecycle evidence itself is contradictory.
- Provide transition rules for active, archived, and merged records.
- Expose lifecycle in admin/API surfaces without changing the meaning
  of `quality_status`.

## Non-goals

- No same-name merge UI. This change defines lifecycle state and
  persistence only.
- No deletion of historical professor records.
