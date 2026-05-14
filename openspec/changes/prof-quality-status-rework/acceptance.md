# Acceptance: prof-quality-status-rework

## 1. Spec validation

- [x] `openspec validate prof-quality-status-rework` exits 0.
- [x] Child spec review is complete before implementation starts.

## 2. Evaluator behavior

- [ ] Complete official-source professor evaluates to `ready`.
- [ ] Trustworthy incomplete professor evaluates to
  `needs_enrichment`, not `needs_review`.
- [ ] Low-quality parse signals evaluate to `low_confidence`.
- [ ] Missing official source evaluates to `low_confidence`, not
  `needs_enrichment`.
- [ ] True anomalies evaluate to `needs_review`.
- [ ] `field_contradiction` is raised only for the pinned
  machine-detectable contradiction set.
- [ ] Missing title, department, research topic, or summary does not
  count as `field_contradiction`.
- [ ] The pinned required key-field list is covered by tests.
- [ ] Priority cascade is anomaly > low-quality parse > ready >
  incomplete.
- [ ] Quality-gate-authored issue rows do not feed back as blocking
  signals.
- [ ] Newly filed external issue invalidates a fresh human override.
- [ ] Unchanged canonical data preserves a fresh human override.

## 3. Persistence behavior

- [ ] Canonical write and re-evaluation converge on one open
  `pipeline_issue` row for the same reason.
- [ ] Stale quality-gate rows are marked resolved when the reason
  disappears.
- [ ] Rows from other `reported_by` values are never resolved by the
  quality gate.
- [ ] All reason stages use existing V006/V023 stage values.
- [ ] `external_blocking_issue` is display-only and does not create a
  duplicate `pipeline_issue` row written by `professor_quality_gate`.

## 4. Real data evidence

- [ ] `miroflow_real` re-evaluation shows official-source,
  identity-resolved professors with no external open issue and no
  detected field contradiction are not assigned `needs_review`.
- [ ] Distribution by `quality_status` is recorded before and after the
  write pass.
- [ ] Open `pipeline_issue` counts by `reported_by` and `stage` are
  recorded before and after the write pass.
- [ ] Re-running the write pass is idempotent.
