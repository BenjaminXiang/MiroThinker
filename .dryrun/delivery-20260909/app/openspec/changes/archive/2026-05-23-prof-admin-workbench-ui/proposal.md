---
change_id: prof-admin-workbench-ui
type: feat (professor admin workbench API and UI)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-14
parent: prof-admin-workbench
canonical_input:
  - openspec/changes/prof-admin-workbench/
  - openspec/changes/prof-quality-status-rework/
  - openspec/changes/prof-fact-extraction-expansion/
---

# Proposal: prof-admin-workbench-ui

## Why

After the backend quality status and structured fact backfill land, an
administrator still needs a dedicated surface to inspect professor
quality, understand missing or suspect fields, review provenance, and
record lightweight decisions. The current generic `RecordDetail.tsx`
viewer is not sufficient for scrape-quality operations.

## What Changes

- Add a new `/api/admin/professor/*` namespace for professor triage,
  rich detail payloads, and marking actions.
- Add the additive `professor_admin_action` migration for append-only
  operation logging and canonical-watermark-bound overrides.
- Build a professor-specific audit workbench with quality diagnosis
  pinned at the top and inline provenance for key fields.
- Keep the existing lean `/api/professor/{id}` API unchanged.

## Non-goals

- No in-page field editing.
- No same-name merge workflow.
- No lifecycle modeling.
- No change to company, paper, or patent generic detail pages except
  routing professor detail to the new workbench where appropriate.
