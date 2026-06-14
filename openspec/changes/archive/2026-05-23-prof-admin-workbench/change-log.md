# Change Log: prof-admin-workbench

## 2026-05-14 — Epic proposed and designed

- Brainstorming session locked five decisions: read-only workbench plus
  lightweight marking actions; new `/api/admin/professor/*` namespace;
  pure `evaluate_professor_quality` with two write call sites; LLM
  summary backfill; v1 includes experience-field extraction. The
  initial Epic decomposition was crisis-first (quality rework →
  workbench UI → fact extraction). Frontend layout decided as Layout A
  (diagnosis-pinned single column).
- Live `miroflow_real` inspection confirmed the root cause: all 495
  professors sit at the `needs_review` column default because
  `canonical_writer` never writes `quality_status`. Also confirmed
  `ck_professor_quality_status` and `ck_professor_fact_type` already
  permit the values this Epic needs (no constraint migration for
  Child 1 or the fact-extraction child).
- Wrote the Epic-level `proposal.md`, `design.md`, and the
  cross-cutting `specs/professor-admin-workbench/spec.md`. Registered
  the parent in `openspec/change-ledger.md`.
- Review round 1 (5 findings) resolved: non-ready reasons persisted to
  `pipeline_issue` per Shared-Spec §7.2; `flag_recrawl` uses the
  existing `data_quality_flag` stage instead of a new `stage` value;
  `professor_admin_action` gains `observed_data_updated_at`; the UI
  child gains an admin triage list; the fact-extraction summary
  backfill count is established by a preflight rather than assumed.
- Review round 2 (4 findings) resolved: quality-gate-authored
  `pipeline_issue` rows carry `reported_by = professor_quality_gate`
  and are excluded from the evaluation's own blocking input (no
  self-feedback loop); reason-persistence idempotency uses the existing
  `uq_pipeline_issue_open` index dimensions; the canonical watermark
  includes external open `pipeline_issue` activity; the parent
  artifact set (`tasks.md`, `acceptance.md`, `change-log.md`,
  `source-links.md`, `agent-links.md`) was completed.

## 2026-05-14 — Child sequencing and scaffold review alignment

- Corrected the `professor_admin_action.observed_data_updated_at`
  design text so it matches the canonical watermark definition in the
  Human override section: the watermark includes professor, fact,
  affiliation, and external open `pipeline_issue` activity.
- Re-sequenced the child changes from quality → workbench → facts to
  quality → facts → workbench. Child 1 still resolves the universal
  `needs_review` default first; Child 2 then improves collected facts
  and profile summaries before Child 3 builds the dedicated audit UI.
- Scaffolded the three child OpenSpec changes and registered them in
  the ledger. Child implementation remains gated on child-spec review
  and a clean implementation checkpoint.
