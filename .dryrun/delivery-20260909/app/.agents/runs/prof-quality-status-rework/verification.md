# Verification: prof-quality-status-rework

## 2026-05-21 - Implementation and dry-run checkpoint

### Scope

- Change: `prof-quality-status-rework`
- Implemented:
  - canonical-state dataclasses and pure
    `evaluate_professor_quality(...)`
  - SQL loader for `ProfessorCanonicalState`
  - idempotent quality-gate issue persistence and stale-row
    reconciliation
  - `write_professor_bundle(...)` quality-status wiring in the same
    transaction as canonical writes
  - `scripts/run_professor_quality_re_eval.py` with dry-run,
    selected-professor, distribution, and issue-count reporting

### Red / green evidence

- RED evaluator test:
  `uv run --no-sync pytest tests/data_agents/professor/test_professor_quality_status_rework.py -q`
  failed because `PipelineIssueState` / canonical evaluator API did
  not exist.
- GREEN evaluator/persistence test:
  same command -> `10 passed in 9.62s`.
- RED canonical-writer test:
  `DATABASE_URL=... DATABASE_URL_TEST=... uv run --no-sync pytest tests/professor/test_canonical_writer.py::test_write_professor_bundle_sets_incomplete_official_quality_status -q -n0`
  failed because written professor rows stayed at default
  `needs_review`.
- GREEN canonical-writer test:
  same command -> `1 passed in 4.62s`.
- RED script test:
  `uv run --no-sync pytest tests/scripts/test_run_professor_quality_re_eval.py -q`
  failed because `scripts/run_professor_quality_re_eval.py` did not
  exist.
- GREEN script test:
  same command -> `4 passed in 9.24s`.

### Focused verification

```bash
cd apps/miroflow-agent
uv run --no-sync pytest \
  tests/data_agents/professor/test_professor_quality_status_rework.py \
  tests/data_agents/professor/test_quality_gate.py \
  tests/scripts/test_run_professor_quality_re_eval.py \
  -q
```

Result: `43 passed in 9.96s`.

```bash
cd apps/miroflow-agent
DATABASE_URL=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_quality_status_rework \
DATABASE_URL_TEST=postgresql+psycopg://miroflow:miroflow@localhost:15432/miroflow_test_quality_status_rework \
uv run --no-sync pytest \
  tests/professor/test_canonical_writer.py::test_write_professor_bundle_sets_incomplete_official_quality_status \
  -q -n0
```

Result: `1 passed in 4.62s`.

```bash
cd apps/miroflow-agent
uv run --no-sync ruff check \
  src/data_agents/professor/quality_gate.py \
  src/data_agents/professor/canonical_writer.py \
  scripts/run_professor_quality_re_eval.py \
  tests/data_agents/professor/test_professor_quality_status_rework.py \
  tests/scripts/test_run_professor_quality_re_eval.py \
  tests/professor/test_canonical_writer.py
```

Result: `All checks passed!`.

### Real DB dry-run

```bash
cd apps/miroflow-agent
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
uv run --no-sync python scripts/run_professor_quality_re_eval.py --dry-run
```

Result:

```json
{
  "dry_run": true,
  "evaluated": 495,
  "written": 0,
  "before_distribution": {
    "needs_enrichment": 493,
    "ready": 2
  },
  "after_distribution": {
    "needs_enrichment": 493,
    "ready": 2
  },
  "before_quality_gate_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457
  },
  "after_quality_gate_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457
  },
  "reason_counts": {
    "missing_research_topic": 457,
    "missing_profile_summary": 492,
    "missing_title_or_department": 246
  }
}
```

## 2026-05-21 - Real DB write pass after approval

### Pre-write dry-run

```bash
cd apps/miroflow-agent
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
uv run --no-sync python scripts/run_professor_quality_re_eval.py --dry-run
```

Result:

```json
{
  "dry_run": true,
  "evaluated": 495,
  "written": 0,
  "before_distribution": {
    "needs_enrichment": 493,
    "ready": 2
  },
  "after_distribution": {
    "needs_enrichment": 493,
    "ready": 2
  },
  "before_quality_gate_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457
  },
  "after_quality_gate_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457
  },
  "reason_counts": {
    "missing_research_topic": 457,
    "missing_profile_summary": 492,
    "missing_title_or_department": 246
  }
}
```

### Write pass

```bash
cd apps/miroflow-agent
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
uv run --no-sync python scripts/run_professor_quality_re_eval.py
```

Result:

```json
{
  "dry_run": false,
  "evaluated": 495,
  "written": 495,
  "before_distribution": {
    "needs_enrichment": 493,
    "ready": 2
  },
  "after_distribution": {
    "needs_enrichment": 493,
    "ready": 2
  },
  "before_quality_gate_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457
  },
  "after_quality_gate_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457
  },
  "reason_counts": {
    "missing_research_topic": 457,
    "missing_profile_summary": 492,
    "missing_title_or_department": 246
  }
}
```

### Post-write SQL guard

Result:

```json
{
  "quality_status": [
    {
      "quality_status": "needs_enrichment",
      "n": 493
    },
    {
      "quality_status": "ready",
      "n": 2
    }
  ],
  "open_quality_gate_issues": [
    {
      "stage": "affiliation",
      "n": 246
    },
    {
      "stage": "coverage",
      "n": 492
    },
    {
      "stage": "research_directions",
      "n": 457
    }
  ],
  "duplicate_open_quality_gate_uq_keys": [],
  "external_open_issues": [
    {
      "reported_by": "professor_seed_runner",
      "stage": "adapter_missing",
      "n": 3
    },
    {
      "reported_by": "professor_seed_runner",
      "stage": "discovery",
      "n": 1
    }
  ]
}
```

### Idempotence rerun

The write command was run a second time to verify status and issue-count
idempotence. Result stayed unchanged:

```json
{
  "dry_run": false,
  "evaluated": 495,
  "written": 495,
  "before_distribution": {
    "needs_enrichment": 493,
    "ready": 2
  },
  "after_distribution": {
    "needs_enrichment": 493,
    "ready": 2
  },
  "before_quality_gate_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457
  },
  "after_quality_gate_issue_counts": {
    "professor_quality_gate:affiliation": 246,
    "professor_quality_gate:coverage": 492,
    "professor_quality_gate:research_directions": 457
  },
  "reason_counts": {
    "missing_research_topic": 457,
    "missing_profile_summary": 492,
    "missing_title_or_department": 246
  }
}
```

Final dry-run and SQL guard after rerun:

```json
{
  "quality_status": [
    {
      "quality_status": "needs_enrichment",
      "n": 493
    },
    {
      "quality_status": "ready",
      "n": 2
    }
  ],
  "open_quality_gate_issues": [
    {
      "stage": "affiliation",
      "n": 246
    },
    {
      "stage": "coverage",
      "n": 492
    },
    {
      "stage": "research_directions",
      "n": 457
    }
  ],
  "duplicate_open_quality_gate_uq_key_count": 0,
  "needs_review_count": 0
}
```

Note: the CLI reports `written=495` on each write pass because it
persists each evaluated professor row. The idempotence asserted here is
for quality-status distribution, quality-gate issue counts, and absence
of duplicate open quality-gate issue keys.
