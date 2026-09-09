# Acceptance: prof-summary-fields

## Spec validation

- [x] `openspec validate prof-summary-fields` exits 0.

## Storage

- [x] Durable professor-level paper and patent summary fields exist.
- [x] Storage is additive and reversible.

## Generation

- [x] Only accepted professor-paper links feed `paper_summary`.
- [x] Only accepted professor-patent links feed `patent_summary`.
- [x] Rejected or uncertain links are excluded.
- [x] LLM calls are mocked in unit tests.

## Refresh

- [x] Changed summaries can be selected by the professor research-vector
  refresh path.

## 2026-05-23 T1 schema evidence

Storage decision:

- Chosen shape: nullable `paper_summary` and `patent_summary` columns on
  `professor`.
- Rationale: this is the smallest additive shape, matches the
  OpenSpec option, and keeps the fields directly queryable by the
  professor vector publisher without introducing a new join contract.

RED/GREEN:

- RED:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/storage/test_v025_migration.py -q -n0`
  failed because `V025_add_professor_output_summary_fields.py` did not
  exist and migrated `professor` had no `paper_summary` or
  `patent_summary` columns.
- GREEN:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/storage/test_v025_migration.py -q -n0`
  passed: 3 passed.
- `uv run --no-sync ruff check alembic/versions/V025_add_professor_output_summary_fields.py tests/storage/test_v025_migration.py`
  passed.
- `openspec validate prof-summary-fields --strict`
  passed.

## 2026-05-23 T4 backfill-runner evidence

Implemented runner and refresh signal:

- `run_output_summary_backfill`
- `select_professors_for_output_summary_backfill`
- `persist_professor_output_summaries`
- `select_professors_for_research_vector_refresh`
- `OutputSummaryBackfillReport`

Runner behavior:

- Selects professors with at least one verified paper or patent link.
- Supports `limit`, `professor_ids`, and `dry_run`.
- Reports `eligible`, `processed`, `skipped`, `failed`,
  `paper_summaries_written`, `patent_summaries_written`, and
  `refresh_professor_ids`.
- In dry-run mode, reports projected writes without mutating
  `professor.paper_summary` or `professor.patent_summary`.
- In write mode, changed summaries update `professor.run_id`; later
  research-vector refresh can select changed professors by that run id.

RED/GREEN:

- RED:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_output_summary_backfill.py -q -n0`
  failed during collection because `run_output_summary_backfill` did not
  exist.
- GREEN:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_output_summary_backfill.py -q -n0`
  passed: 2 passed.
- Full `prof-summary-fields` verification:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/storage/test_v025_migration.py tests/data_agents/professor/test_output_summaries.py tests/postgres/test_professor_output_summary_inputs.py tests/postgres/test_professor_output_summary_backfill.py -q -n0`
  passed: 11 passed.
- `uv run --no-sync ruff check src/data_agents/professor/output_summaries.py tests/data_agents/professor/test_output_summaries.py tests/postgres/test_professor_output_summary_inputs.py tests/postgres/test_professor_output_summary_backfill.py tests/storage/test_v025_migration.py`
  passed.
- `openspec validate prof-summary-fields --strict`
  passed.

Bounded dry-run sample:

- `test_output_summary_backfill_dry_run_reports_without_writing` runs the
  backfill with `dry_run=True` and `limit=1` against migrated Postgres
  schema through V025.
- It verifies one eligible professor is processed, one paper summary and
  one patent summary are projected, no failures occur, and the professor
  row remains unwritten.

## 2026-05-23 T3 summary-generation evidence

Implemented generator:

- `generate_professor_output_summaries`
- `ProfessorOutputSummaryResult`

Generation behavior:

- No eligible papers or patents returns explicit
  `no_summary_reason = "no eligible papers or patents"` and does not call
  the LLM client.
- Eligible inputs are summarized through an injected LLM client and model.
- The generator asks for strict JSON with `paper_summary` and
  `patent_summary`.
- Tests mock the LLM client and cover paper-only, patent-only, mixed, and
  no-output cases.

RED/GREEN:

- RED:
  `uv run --no-sync pytest tests/data_agents/professor/test_output_summaries.py -q -n0`
  failed during collection because
  `generate_professor_output_summaries` did not exist.
- GREEN:
  `uv run --no-sync pytest tests/data_agents/professor/test_output_summaries.py -q -n0`
  passed: 4 passed.
- Combined query and generator verification:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/data_agents/professor/test_output_summaries.py tests/postgres/test_professor_output_summary_inputs.py -q -n0`
  passed: 6 passed.
- `uv run --no-sync ruff check src/data_agents/professor/output_summaries.py tests/data_agents/professor/test_output_summaries.py tests/postgres/test_professor_output_summary_inputs.py`
  passed.
- `openspec validate prof-summary-fields --strict`
  passed.

## 2026-05-23 T2 input-selection evidence

Implemented input selectors:

- `select_eligible_paper_summary_inputs`
- `select_eligible_patent_summary_inputs`

Eligibility rule:

- Paper and patent inputs require `link_status = 'verified'`.
- `candidate` links are treated as uncertain and excluded.
- `rejected` links are excluded.
- Joined canonical rows with `identity_status IN ('rejected', 'merged')`
  are excluded.

RED/GREEN:

- RED:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_output_summary_inputs.py -q -n0`
  failed during collection because
  `src.data_agents.professor.output_summaries` did not exist.
- GREEN:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_output_summary_inputs.py -q -n0`
  passed: 2 passed. The test upgraded Postgres through V025 and verified
  inclusion/exclusion against real `professor_paper_link`,
  `professor_patent_link`, `paper`, `patent`, and `professor` tables.
- `uv run --no-sync ruff check src/data_agents/professor/output_summaries.py tests/postgres/test_professor_output_summary_inputs.py`
  passed.
- `openspec validate prof-summary-fields --strict`
  passed.
