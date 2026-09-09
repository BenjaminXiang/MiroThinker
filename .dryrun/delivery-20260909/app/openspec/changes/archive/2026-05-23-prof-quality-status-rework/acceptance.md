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
- [x] Re-running the write pass is idempotent for status and issue
  counts. *(The script still updates touched professor rows as part of
  persistence; idempotence is asserted on quality distribution,
  quality-gate issue counts, and duplicate open issue keys.)*

## Evidence

### 2026-05-21 implementation and dry-run evidence

- Focused unit/script suite:
  `uv run --no-sync pytest tests/data_agents/professor/test_professor_quality_status_rework.py tests/data_agents/professor/test_quality_gate.py tests/scripts/test_run_professor_quality_re_eval.py -q`
  -> `43 passed in 9.96s`.
- Canonical-writer integration regression:
  `DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_quality_status_rework DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_quality_status_rework uv run --no-sync pytest tests/professor/test_canonical_writer.py::test_write_professor_bundle_sets_incomplete_official_quality_status -q -n0`
  -> `1 passed in 4.62s`.
- Ruff:
  `uv run --no-sync ruff check src/data_agents/professor/quality_gate.py src/data_agents/professor/canonical_writer.py scripts/run_professor_quality_re_eval.py tests/data_agents/professor/test_professor_quality_status_rework.py tests/scripts/test_run_professor_quality_re_eval.py tests/professor/test_canonical_writer.py`
  -> `All checks passed!`.
- `miroflow_real` dry-run:
  `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_professor_quality_re_eval.py --dry-run`
  -> evaluated `495`, written `0`.
- Dry-run distribution:
  - before: `needs_enrichment=493`, `ready=2`
  - after evaluation: `needs_enrichment=493`, `ready=2`
  - `needs_review=0`
- Dry-run open quality-gate issue counts:
  - `professor_quality_gate:affiliation=246`
  - `professor_quality_gate:coverage=492`
  - `professor_quality_gate:research_directions=457`
- Dry-run reason counts:
  - `missing_research_topic=457`
  - `missing_profile_summary=492`
  - `missing_title_or_department=246`
- Write pass after user approval:
  `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_professor_quality_re_eval.py`
  -> evaluated `495`, written `495`, before distribution
  `needs_enrichment=493`, `ready=2`, after distribution
  `needs_enrichment=493`, `ready=2`.
- Write-pass issue counts before and after:
  - `professor_quality_gate:affiliation=246`
  - `professor_quality_gate:coverage=492`
  - `professor_quality_gate:research_directions=457`
- Idempotence re-run:
  same write command -> evaluated `495`, written `495`, before and
  after distribution still `needs_enrichment=493`, `ready=2`; before
  and after quality-gate issue counts still
  `affiliation=246`, `coverage=492`, `research_directions=457`.
- Post-rerun SQL guard:
  - `needs_review_count=0`
  - `duplicate_open_quality_gate_uq_key_count=0`
