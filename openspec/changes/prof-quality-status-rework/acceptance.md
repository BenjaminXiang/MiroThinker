# Acceptance: prof-quality-status-rework

## 1. Spec validation

- [x] `openspec validate prof-quality-status-rework` exits 0.
- [x] Child spec review is complete before implementation starts.

## 2. Evaluator behavior

- [x] Complete official-source professor evaluates to `ready`.
- [x] Trustworthy incomplete professor evaluates to
  `needs_enrichment`, not `needs_review`.
- [x] Low-quality parse signals evaluate to `low_confidence`.
- [x] Missing official source evaluates to `low_confidence`, not
  `needs_enrichment`.
- [x] True anomalies evaluate to `needs_review`.
- [x] `field_contradiction` is raised only for the pinned
  machine-detectable contradiction set.
- [x] Missing title, department, research topic, or summary does not
  count as `field_contradiction`.
- [x] The pinned required key-field list is covered by tests.
- [x] Priority cascade is anomaly > low-quality parse > ready >
  incomplete.
- [x] Quality-gate-authored issue rows do not feed back as blocking
  signals.
- [x] Newly filed external issue invalidates a fresh human override.
- [x] Unchanged canonical data preserves a fresh human override.

## 3. Persistence behavior

- [x] Canonical write and re-evaluation converge on one open
  `pipeline_issue` row for the same reason.
- [x] Stale quality-gate rows are marked resolved when the reason
  disappears.
- [x] Rows from other `reported_by` values are never resolved by the
  quality gate.
- [x] All reason stages use existing V006/V023 stage values.
- [x] `external_blocking_issue` is display-only and does not create a
  duplicate `pipeline_issue` row written by `professor_quality_gate`.

## 4. Real data evidence

- [x] `miroflow_real` re-evaluation shows official-source,
  identity-resolved professors with no external open issue and no
  detected field contradiction are not assigned `needs_review`.
- [x] Distribution by `quality_status` is recorded before and after the
  write pass.
- [x] Open `pipeline_issue` counts by `reported_by` and `stage` are
  recorded before and after the write pass.
- [x] Re-running the write pass is idempotent.

## Evidence

- Focused evaluator and script tests:
  `PYTHONPATH=. /home/longxiang/MiroThinker/apps/miroflow-agent/.venv/bin/python -m pytest -o addopts='' tests/data_agents/professor/test_quality_gate.py tests/scripts/test_run_professor_quality_re_eval.py -q`
  exited 0: 46 passed.
- Canonical-writer regression tests:
  `DATABASE_URL=<local miroflow_test_mock DSN> DATABASE_URL_TEST=<local miroflow_test_mock DSN> PYTHONPATH=. /home/longxiang/MiroThinker/apps/miroflow-agent/.venv/bin/python -m pytest -o addopts='' tests/professor/test_canonical_writer.py -q`
  exited 0: 7 passed, 30 warnings.
- `openspec validate prof-quality-status-rework` exited 0.
- `git diff --check` exited 0.
- `miroflow_real` dry-run, all rows:
  before distribution `{"needs_review": 495}`;
  projected after distribution `{"needs_enrichment": 493, "needs_review": 0, "ready": 2}`;
  before and after open external issue counts unchanged:
  `{"professor_seed_runner:adapter_missing": 3, "professor_seed_runner:discovery": 1}`;
  `professors_scanned=495`, `statuses_changed=495`, `issues_inserted=0`,
  `issues_resolved=0`.
- `miroflow_real` write pass:
  before distribution `{"needs_review": 495}`;
  after distribution `{"needs_enrichment": 493, "ready": 2}`;
  after open issue counts
  `{"professor_quality_gate:affiliation": 246, "professor_quality_gate:coverage": 492, "professor_quality_gate:research_directions": 457, "professor_seed_runner:adapter_missing": 3, "professor_seed_runner:discovery": 1}`;
  `issues_inserted=1195`, `issues_resolved=0`.
- `miroflow_real` idempotency re-run:
  before and after distribution stayed `{"needs_enrichment": 493, "ready": 2}`;
  before and after open issue counts stayed unchanged;
  `statuses_changed=0`, `issues_inserted=0`, `issues_resolved=0`.
