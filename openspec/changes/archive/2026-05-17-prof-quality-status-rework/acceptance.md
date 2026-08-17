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

- 2026-05-15: Pure evaluator RED command failed before implementation
  because the new dataclasses and `evaluate_professor_quality` did not
  exist.
- 2026-05-15: Pure evaluator GREEN command passed: `pytest -n0
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_complete_state_ready
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_missing_summary_needs_enrichment_not_review
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_missing_official_source_low_confidence
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_unresolved_identity_needs_review_priority_over_low_confidence
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_gate_authored_issue_does_not_block_itself
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_external_issue_blocks_without_duplicate_persist_reason
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_fresh_confirm_ready_override_applies
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_later_external_issue_invalidates_override
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_multiple_current_primary_institutions_are_contradiction
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_missing_title_department_is_not_contradiction
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_conflicting_same_source_contacts_are_contradiction
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_verified_paper_signal_only_required_when_candidates_exist
  -q` returned `12 passed`.
- 2026-05-15: Persistence RED command failed before implementation
  because `load_professor_canonical_state` and
  `persist_professor_quality_evaluation` did not exist.
- 2026-05-15: Persistence GREEN command passed: `pytest -n0
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_load_professor_canonical_state_maps_persisted_rows
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_evaluation_upserts_gate_issue_and_resolves_stale
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_external_blocking_issue_is_display_only
  -q` returned `3 passed`.
- 2026-05-15: Canonical writer helper RED command failed before
  implementation because the writer did not import or call the quality
  loader/evaluator/persistence helpers.
- 2026-05-15: Canonical writer helper GREEN command passed: `pytest -n0
  apps/miroflow-agent/tests/professor/test_canonical_writer.py::test_evaluate_and_persist_professor_quality_helper_wires_loader_and_persistence
  -q` returned `1 passed`.
- 2026-05-15: Re-evaluation CLI RED command failed before implementation
  because `scripts/run_professor_quality_re_eval.py` did not exist.
- 2026-05-15: Re-evaluation CLI GREEN command passed: `pytest -n0
  apps/miroflow-agent/tests/scripts/test_run_professor_quality_re_eval.py
  -q` returned `3 passed`.
- 2026-05-15: Focused regression command passed: `pytest -n0
  apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py
  apps/miroflow-agent/tests/professor/test_canonical_writer.py
  apps/miroflow-agent/tests/scripts/test_run_professor_quality_re_eval.py
  -q` returned `48 passed, 7 skipped`.
- 2026-05-15: `miroflow_real` connection probe succeeded using the
  local libpq DSN form. The initial `uv run` attempt failed before DB
  access because the configured SUSTech PyPI mirror returned a TLS
  handshake error for `hatchling`; reruns used
  `UV_INDEX_URL=https://pypi.org/simple` to keep the project command
  path intact.
- 2026-05-15: Real-data dry-run command passed:
  `UV_INDEX_URL=https://pypi.org/simple DATABASE_URL=postgresql://.../miroflow_real
  uv run python scripts/run_professor_quality_re_eval.py --dry-run`.
  It evaluated 495 professors with before distribution
  `{needs_enrichment: 493, ready: 2}` and predicted the same after
  distribution. No professor was predicted as `needs_review`.
- 2026-05-15: Real-data write pass command passed:
  `UV_INDEX_URL=https://pypi.org/simple DATABASE_URL=postgresql://.../miroflow_real
  uv run python scripts/run_professor_quality_re_eval.py`. It evaluated
  495 professors with before/after distribution
  `{needs_enrichment: 493, ready: 2}`. The first write pass inserted
  1195 current quality-gate issue rows and reconciled stale
  quality-gate issue rows.
- 2026-05-15: Post-write issue count query recorded
  `professor_quality_gate` rows as `open=1195`, `resolved=1195`,
  `duplicate_groups=0`; open counts by stage were
  `affiliation=246`, `coverage=492`, and
  `research_directions=457`.
- 2026-05-15: Idempotency rerun passed. Before rerun counts were
  `total=2390`, `open=1195`, `resolved=1195`, `duplicate_rows=0`;
  after rerun counts were unchanged. After fixing report rowcount
  semantics, the rerun reported `issues_upserted=0` and
  `stale_issues_reconciled=0`.
- 2026-05-15: Report-rowcount RED command failed as intended:
  `UV_INDEX_URL=https://pypi.org/simple uv run pytest -n0
  tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_evaluation_reports_actual_rowcounts
  -q` returned `1 failed` because persistence reported logical reason
  counts instead of actual database row counts.
- 2026-05-15: Report-rowcount GREEN command passed:
  `UV_INDEX_URL=https://pypi.org/simple uv run pytest -n0
  tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_evaluation_reports_actual_rowcounts
  tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_evaluation_upserts_gate_issue_and_resolves_stale
  tests/scripts/test_run_professor_quality_re_eval.py::test_selected_professor_write_persists_and_reports_issue_counts
  -q` returned `3 passed`.
- 2026-05-15: Updated focused regression command passed:
  `UV_INDEX_URL=https://pypi.org/simple uv run pytest -n0
  tests/data_agents/professor/test_quality_gate.py
  tests/professor/test_canonical_writer.py
  tests/scripts/test_run_professor_quality_re_eval.py -q`
  returned `49 passed, 7 skipped`. The skips are Postgres integration
  tests because `DATABASE_URL_TEST` / `DATABASE_URL` were not exported
  into the pytest process; the real-data script path above covered
  `miroflow_real` explicitly.
