# Tasks: prof-admin-workbench (Epic parent)

This parent change carries the Epic-level `proposal.md`, `design.md`,
and the cross-cutting behavior contract in
`specs/professor-admin-workbench/spec.md`. Implementation is sliced
into three child changes; the parent's own tasks are to scaffold and
sequence them.

## 1. Scaffold child changes

- [x] T1.1: Create `openspec/changes/prof-quality-status-rework/` with
  the full artifact set. Behavior: the corrected four-state
  `quality_status` semantics, `evaluate_professor_quality` as a pure
  function, reason persistence to `pipeline_issue` with `reported_by =
  professor_quality_gate`, the `rule_id → stage` map (existing
  V006/V023 stages only), the canonical-watermark definition, the two
  write call sites, and the standalone re-evaluation entry point.
- [x] T1.2: Create `openspec/changes/prof-fact-extraction-expansion/`
  with the full artifact set. Behavior: LLM structured extraction of
  `education / work_experience / award / academic_position` into
  `professor_fact`, the eligible-set preflight, the backfill runner,
  and the post-backfill re-evaluation.
- [x] T1.3: Create `openspec/changes/prof-admin-workbench-ui/` with the
  full artifact set. Behavior: the `/api/admin/professor/*` namespace
  (triage list + detail payload + marking endpoints), the
  `professor_admin_action` table migration (with
  `observed_data_updated_at`), and the Layout A audit workbench
  frontend.

## 2. Register and sequence

- [x] T2.1: Parent change registered in `openspec/change-ledger.md`.
- [x] T2.2: Register the three child changes in the ledger once
  scaffolded, sequenced as `prof-quality-status-rework` →
  `prof-fact-extraction-expansion` → `prof-admin-workbench-ui`.
- [x] T2.3: Create `.agents/runs/prof-admin-workbench/` and the
  per-child run workspaces when implementation starts.

## Notes

- The parent ships design + cross-cutting contract only; it has no
  implementation code of its own.
- Child changes MUST respect the Epic-level contract in
  `specs/professor-admin-workbench/spec.md` — corrected four-state
  semantics, reason persistence, the self-feedback guard, the
  canonical watermark, the lightweight marking actions, and the
  triage-list requirement.
