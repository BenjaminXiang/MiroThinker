# Verification: prof-quality-status-rework

Date: 2026-05-15

## TDD Red Checks

- Pure evaluator tests failed before implementation because
  `ProfessorCanonicalState`, `ProfessorQualityReason`,
  `ProfessorQualityEvaluation`, and `evaluate_professor_quality` were
  missing.
- Persistence tests failed before implementation because
  `load_professor_canonical_state` and
  `persist_professor_quality_evaluation` were missing.
- Canonical writer helper test failed before implementation because
  `canonical_writer` did not import or expose the quality
  loader/evaluator/persistence helpers.
- Re-evaluation CLI tests failed before implementation because
  `apps/miroflow-agent/scripts/run_professor_quality_re_eval.py` did not
  exist.

## Green Checks

- `pytest -n0 apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_complete_state_ready apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_missing_summary_needs_enrichment_not_review apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_missing_official_source_low_confidence apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_unresolved_identity_needs_review_priority_over_low_confidence apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_gate_authored_issue_does_not_block_itself apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_external_issue_blocks_without_duplicate_persist_reason apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_fresh_confirm_ready_override_applies apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_later_external_issue_invalidates_override apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_multiple_current_primary_institutions_are_contradiction apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_missing_title_department_is_not_contradiction apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_conflicting_same_source_contacts_are_contradiction apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_professor_quality_verified_paper_signal_only_required_when_candidates_exist -q`
  returned `12 passed`.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_load_professor_canonical_state_maps_persisted_rows apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_evaluation_upserts_gate_issue_and_resolves_stale apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_external_blocking_issue_is_display_only -q`
  returned `3 passed`.
- `pytest -n0 apps/miroflow-agent/tests/professor/test_canonical_writer.py::test_evaluate_and_persist_professor_quality_helper_wires_loader_and_persistence -q`
  returned `1 passed`.
- `pytest -n0 apps/miroflow-agent/tests/scripts/test_run_professor_quality_re_eval.py -q`
  returned `3 passed`.
- `pytest -n0 apps/miroflow-agent/tests/data_agents/professor/test_quality_gate.py apps/miroflow-agent/tests/professor/test_canonical_writer.py apps/miroflow-agent/tests/scripts/test_run_professor_quality_re_eval.py -q`
  returned `48 passed, 7 skipped`.

## Real-Data Verification

- `uv run python ...` initially failed before DB access because the
  configured SUSTech PyPI mirror returned a TLS handshake error while
  resolving `hatchling`.
- `UV_INDEX_URL=https://pypi.org/simple DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run python scripts/run_professor_quality_re_eval.py --dry-run`
  returned success. Summary: `professors_total=495`,
  `before_distribution={"needs_enrichment": 493, "ready": 2}`,
  `after_distribution={"needs_enrichment": 493, "ready": 2}`,
  `issues_upserted=0`, `stale_issues_reconciled=0`.
- `UV_INDEX_URL=https://pypi.org/simple DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run python scripts/run_professor_quality_re_eval.py`
  returned success. Summary: `professors_total=495`,
  `before_distribution={"needs_enrichment": 493, "ready": 2}`,
  `after_distribution={"needs_enrichment": 493, "ready": 2}`.
- Post-write SQL evidence for `reported_by='professor_quality_gate'`:
  `open=1195`, `resolved=1195`, `duplicate_groups=0`; open stage
  counts were `affiliation=246`, `coverage=492`,
  `research_directions=457`.
- Idempotency rerun evidence: before rerun counts were `total=2390`,
  `open=1195`, `resolved=1195`, `duplicate_rows=0`; after rerun counts
  were unchanged. After the rowcount reporting fix, the rerun reported
  `issues_upserted=0` and `stale_issues_reconciled=0`.

## Report Rowcount Regression

- RED: `UV_INDEX_URL=https://pypi.org/simple uv run pytest -n0 tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_evaluation_reports_actual_rowcounts -q`
  returned `1 failed` because persistence reported generated reason
  counts rather than actual DB row counts.
- GREEN: `UV_INDEX_URL=https://pypi.org/simple uv run pytest -n0 tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_evaluation_reports_actual_rowcounts tests/data_agents/professor/test_quality_gate.py::test_persist_professor_quality_evaluation_upserts_gate_issue_and_resolves_stale tests/scripts/test_run_professor_quality_re_eval.py::test_selected_professor_write_persists_and_reports_issue_counts -q`
  returned `3 passed`.
- Updated focused regression:
  `UV_INDEX_URL=https://pypi.org/simple uv run pytest -n0 tests/data_agents/professor/test_quality_gate.py tests/professor/test_canonical_writer.py tests/scripts/test_run_professor_quality_re_eval.py -q`
  returned `49 passed, 7 skipped`. The skipped tests require
  `DATABASE_URL_TEST` or `DATABASE_URL` to be exported into pytest; the
  real-data script checks above passed with an explicit
  `DATABASE_URL`.
