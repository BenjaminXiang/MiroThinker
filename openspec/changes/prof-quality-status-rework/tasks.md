# Tasks: prof-quality-status-rework

## 1. Child spec review gate

- [x] T1.1: Review this child spec against the parent
  `prof-admin-workbench` contract before code edits.
- [x] T1.2: Confirm the required key-field list for `ready`.
- [x] T1.3: Confirm the `rule_id -> pipeline_issue.stage` map uses only
  existing V006/V023 stages.
- [x] T1.4: Define machine-detectable `field_contradiction` signals.

## 2. Pure evaluator

- [ ] T2.1: Add canonical-state and evaluation dataclasses in
  `apps/miroflow-agent/src/data_agents/professor/quality_gate.py`.
- [ ] T2.2: Add `evaluate_professor_quality(...)` with four-state
  priority cascade.
- [ ] T2.3: Cover ready, needs_enrichment, low_confidence,
  needs_review, and priority cascade in unit tests.
- [ ] T2.4: Cover self-feedback exclusion for
  `reported_by = professor_quality_gate`.
- [ ] T2.5: Cover human override fresh/stale behavior.
- [ ] T2.6: Cover `field_contradiction` positive and negative cases.
- [ ] T2.7: Cover the pinned required-key-field list, including the
  verified-paper-signal conditional.
- [ ] T2.8: Cover missing official source evaluating to
  `low_confidence`.

## 3. Persistence helpers

- [ ] T3.1: Add SQL loader for `ProfessorCanonicalState`.
- [ ] T3.2: Add idempotent quality-gate issue upsert using the existing
  `uq_pipeline_issue_open` dimensions.
- [ ] T3.3: Add stale quality-gate issue reconciliation that only
  resolves rows from `reported_by = professor_quality_gate`.
- [ ] T3.4: Add tests for duplicate prevention and stale-row
  reconciliation.
- [ ] T3.5: Add a persistence test proving `external_blocking_issue`
  is display-only and does not create a quality-gate-authored
  duplicate issue row.

## 4. Write-time wiring

- [ ] T4.1: Wire evaluation into
  `professor/canonical_writer.py::write_professor_bundle`.
- [ ] T4.2: Persist `professor.quality_status` in the same transaction
  as canonical writes.
- [ ] T4.3: Add canonical-writer regression tests proving a trustworthy
  incomplete row does not remain at the default `needs_review`.

## 5. Re-evaluation entry point

- [ ] T5.1: Add `apps/miroflow-agent/scripts/run_professor_quality_re_eval.py`.
- [ ] T5.2: Support dry-run and selected-professor modes.
- [ ] T5.3: Report before/after `quality_status` distribution and
  quality-gate issue counts.
- [ ] T5.4: Add script tests with mocked or temporary Postgres state.

## 6. Verification

- [ ] T6.1: Run focused professor quality tests.
- [ ] T6.2: Run canonical-writer regression tests.
- [ ] T6.3: Run re-eval dry-run on `miroflow_real`.
- [ ] T6.4: Run re-eval write pass only after dry-run review.
- [ ] T6.5: Record distribution and issue-count evidence in
  `acceptance.md` and `.agents/runs/prof-quality-status-rework/`.
