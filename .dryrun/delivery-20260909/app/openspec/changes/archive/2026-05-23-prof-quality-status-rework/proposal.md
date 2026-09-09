---
change_id: prof-quality-status-rework
type: feat/refactor (professor quality-status engine)
weight: Standard
behavior_change: true
code_change: yes
adds_requirements: true
created: 2026-05-14
parent: prof-admin-workbench
canonical_input:
  - openspec/changes/prof-admin-workbench/
  - docs/Data-Agent-Shared-Spec.md §7.2
  - docs/Professor-Data-Agent-Requirements-Audit-2026-05-09.md
---

# Proposal: prof-quality-status-rework

## Why

All 495 professors inspected in `miroflow_real` are currently stuck at
`quality_status = needs_review` even though their
`identity_status = resolved`. The root cause is mechanical:
`canonical_writer.py` never writes `quality_status`, so professor rows
keep the column default. The existing `quality_gate.evaluate_quality`
also evaluates the transient `EnrichedProfessorProfile` object rather
than persisted canonical state, and it treats mere incompleteness as
`needs_review`.

This makes the admin review queue unusable. `needs_review` must mean a
true anomaly requiring human judgment; incomplete but trustworthy rows
belong in `needs_enrichment`, and scrape/parse quality failures belong
in `low_confidence`.

## What Changes

- Add a pure `evaluate_professor_quality(canonical_state,
  latest_admin_action=None)` function over persisted professor state.
- Correct the four-state mapping: `ready`, `needs_enrichment`,
  `low_confidence`, and `needs_review`.
- Persist non-ready evaluation reasons to `pipeline_issue` with fixed
  `reported_by = professor_quality_gate`.
- Exclude quality-gate-authored issue rows from the evaluator's own
  blocking inputs to prevent a self-feedback loop.
- Wire evaluation into `canonical_writer.py` and a standalone
  re-evaluation script for existing rows.
- Reconcile stale quality-gate issue rows idempotently without touching
  issue rows from other reporters.

## Non-goals

- No schema migration. Existing professor quality-status values and
  `pipeline_issue` are sufficient.
- No admin UI or marking endpoints. Those belong to
  `prof-admin-workbench-ui`.
- No LLM fact extraction or summary backfill. Those belong to
  `prof-fact-extraction-expansion`.
- No lifecycle modeling. `quality_status` answers whether data is
  trustworthy, not whether the professor is still active.
