# Verification: prof-quality-status-rework

Date: 2026-05-14

Workspace:
`/home/longxiang/.config/superpowers/worktrees/MiroThinker/prof-quality-status-rework`

## Commands

- `openspec validate prof-quality-status-rework`
  - Result: passed, change is valid.
- `git diff --check`
  - Result: passed, no whitespace errors.
- `PYTHONPATH=. /home/longxiang/MiroThinker/apps/miroflow-agent/.venv/bin/python -m pytest -o addopts='' tests/data_agents/professor/test_quality_gate.py tests/scripts/test_run_professor_quality_re_eval.py -q`
  - Result: passed, 46 tests.
- `DATABASE_URL=<local miroflow_test_mock DSN> DATABASE_URL_TEST=<local miroflow_test_mock DSN> PYTHONPATH=. /home/longxiang/MiroThinker/apps/miroflow-agent/.venv/bin/python -m pytest -o addopts='' tests/professor/test_canonical_writer.py -q`
  - Result: passed, 7 tests, 30 existing Pydantic deprecation warnings.
- `DATABASE_URL=<local miroflow_real DSN> PYTHONPATH=. /home/longxiang/MiroThinker/apps/miroflow-agent/.venv/bin/python scripts/run_professor_quality_re_eval.py --dry-run`
  - Result: passed, read-only full-population dry-run.
- `DATABASE_URL=<local miroflow_real DSN> PYTHONPATH=. /home/longxiang/MiroThinker/apps/miroflow-agent/.venv/bin/python scripts/run_professor_quality_re_eval.py`
  - Result: passed, write pass.
- Same write-pass command repeated once.
  - Result: passed, idempotency confirmed.

## Real Data Evidence

Full dry-run over `miroflow_real`:

```json
{
  "before_distribution": {"needs_review": 495},
  "after_distribution": {"needs_enrichment": 493, "needs_review": 0, "ready": 2},
  "before_open_issue_counts": {
    "professor_seed_runner:adapter_missing": 3,
    "professor_seed_runner:discovery": 1
  },
  "after_open_issue_counts": {
    "professor_seed_runner:adapter_missing": 3,
    "professor_seed_runner:discovery": 1
  },
  "dry_run": true,
  "evaluated_statuses": {"needs_enrichment": 493, "ready": 2},
  "issues_inserted": 0,
  "issues_resolved": 0,
  "professors_scanned": 495,
  "statuses_changed": 495
}
```

Write pass over `miroflow_real`:

```json
{
  "before_distribution": {"needs_review": 495},
  "after_distribution": {"needs_enrichment": 493, "ready": 2},
  "after_open_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457,
    "professor_seed_runner:adapter_missing": 3,
    "professor_seed_runner:discovery": 1
  },
  "dry_run": false,
  "evaluated_statuses": {"needs_enrichment": 493, "ready": 2},
  "issues_inserted": 1195,
  "issues_resolved": 0,
  "professors_scanned": 495,
  "statuses_changed": 495
}
```

Idempotency re-run over `miroflow_real`:

```json
{
  "before_distribution": {"needs_enrichment": 493, "ready": 2},
  "after_distribution": {"needs_enrichment": 493, "ready": 2},
  "after_open_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457,
    "professor_seed_runner:adapter_missing": 3,
    "professor_seed_runner:discovery": 1
  },
  "dry_run": false,
  "evaluated_statuses": {"needs_enrichment": 493, "ready": 2},
  "issues_inserted": 0,
  "issues_resolved": 0,
  "professors_scanned": 495,
  "statuses_changed": 0
}
```

## Notes

- `uv sync --group dev` in the isolated worktree was attempted but failed
  before dependency installation because the configured PyPI mirror returned a
  TLS handshake EOF while fetching `hatchling`. Verification therefore reused
  the existing main checkout `apps/miroflow-agent/.venv`.
- Running `tests/professor/test_canonical_writer.py` with only
  `DATABASE_URL_TEST` set failed because `seed_loader.load_all()` reads
  `DATABASE_URL`; the passing run set both variables to the same local
  `miroflow_test_mock` DSN.
