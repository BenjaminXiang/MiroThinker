# Verification: prof-summary-fields

## 2026-05-23 T1 schema implementation

Scope:
- Complete T1.1, T1.2, and T1.3.
- Also complete T5.2 because the migration/schema check was executed.
- Leave input selection, generation, runner, refresh signal, and bounded
  dry-run sample pending for later stages.

Storage decision:
- Use nullable columns on `professor`:
  - `paper_summary text NULL`
  - `patent_summary text NULL`
- Reason: direct queryability by vector publisher and no new summary-table
  join contract.

RED command and outcome:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/storage/test_v025_migration.py -q -n0`
  - Result: failed with 3 expected failures.
  - First failure: `FileNotFoundError` for
    `V025_add_professor_output_summary_fields.py`.
  - Schema failures: migrated `professor` had no `paper_summary` or
    `patent_summary` columns.

Implementation:
- Added `apps/miroflow-agent/alembic/versions/V025_add_professor_output_summary_fields.py`.
- Revision chain: `V025` after `V024`.
- Upgrade adds nullable `paper_summary` and `patent_summary` columns to
  `professor`.
- Downgrade drops the two columns in reverse order.

GREEN commands and outcomes:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/storage/test_v025_migration.py -q -n0`
  - Result: passed, 3 passed.
  - Coverage: revision chain, nullable text column presence, and writable
    professor output-summary fields on migrated schema.

- `uv run --no-sync ruff check alembic/versions/V025_add_professor_output_summary_fields.py tests/storage/test_v025_migration.py`
  - Result: passed, `All checks passed!`.

- `openspec validate prof-summary-fields --strict`
  - Result: passed, `Change 'prof-summary-fields' is valid`.

Task status updated:
- T1.1 complete.
- T1.2 complete.
- T1.3 complete.
- T5.2 complete.

Next implementation step:
- Start T2 input selection with RED tests for accepted paper/patent links
  and rejected/uncertain/unresolved exclusion.

## 2026-05-23 T2 input selection

Scope:
- Complete T2.1, T2.2, T2.3, and T2.4.
- Leave generator, backfill runner, refresh signal, and bounded dry-run
  sample pending.

Eligibility decision:
- Current link tables expose `verified`, `candidate`, and `rejected`.
- Accepted summary inputs are `link_status = 'verified'`.
- `candidate` is the current schema representation of uncertain links and
  is excluded.
- Rejected links are excluded.
- Joined canonical `paper` and `patent` rows with
  `identity_status IN ('rejected', 'merged')` are excluded.

RED command and outcome:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_output_summary_inputs.py -q -n0`
  - Result: failed during collection.
  - Expected failure:
    `ModuleNotFoundError: No module named 'src.data_agents.professor.output_summaries'`.

Implementation:
- Added `apps/miroflow-agent/src/data_agents/professor/output_summaries.py`.
- Added `PaperSummaryInput` and `PatentSummaryInput` dataclasses.
- Added `select_eligible_paper_summary_inputs`.
- Added `select_eligible_patent_summary_inputs`.
- Added Postgres integration tests in
  `apps/miroflow-agent/tests/postgres/test_professor_output_summary_inputs.py`.

GREEN commands and outcomes:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_output_summary_inputs.py -q -n0`
  - Result: passed, 2 passed.
  - Coverage: Alembic upgrade through V025, real canonical/link tables,
    verified paper/patent inclusion, candidate/rejected exclusion, and
    cross-professor exclusion.

- `uv run --no-sync ruff check src/data_agents/professor/output_summaries.py tests/postgres/test_professor_output_summary_inputs.py`
  - Result: passed, `All checks passed!`.

- `openspec validate prof-summary-fields --strict`
  - Result: passed, `Change 'prof-summary-fields' is valid`.

Task status updated:
- T2.1 complete.
- T2.2 complete.
- T2.3 complete.
- T2.4 complete.

Next implementation step:
- Start T3 summary generation with RED tests for injected mocked LLM,
  no-output fallback, and separate paper/patent/mixed summary behavior.

## 2026-05-23 T3 summary generation

Scope:
- Complete T3.1, T3.2, and T3.3.
- Complete T5.1 because generator and query tests were run together.
- Leave backfill runner, refresh signal, and bounded dry-run sample
  pending.

Generation decision:
- Use an injected LLM client and model for eligible outputs.
- Return explicit no-summary outcome without an LLM call when a professor
  has no eligible paper or patent inputs.
- Require strict JSON with `paper_summary` and `patent_summary`.

RED command and outcome:

- `uv run --no-sync pytest tests/data_agents/professor/test_output_summaries.py -q -n0`
  - Result: failed during collection.
  - Expected failure:
    `ImportError: cannot import name 'generate_professor_output_summaries'`.

Implementation:
- Extended `apps/miroflow-agent/src/data_agents/professor/output_summaries.py`.
- Added `ProfessorOutputSummaryResult`.
- Added `generate_professor_output_summaries`.
- Added strict JSON parsing with fenced JSON support.
- Added source-grounded prompt construction from selected paper/patent
  rows.
- Added mocked-client unit tests in
  `apps/miroflow-agent/tests/data_agents/professor/test_output_summaries.py`.

GREEN commands and outcomes:

- `uv run --no-sync pytest tests/data_agents/professor/test_output_summaries.py -q -n0`
  - Result: passed, 4 passed.
  - Coverage: no-output no-LLM path, paper-only LLM call, patent-only LLM
    call, mixed paper/patent output, and fenced JSON parsing.

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/data_agents/professor/test_output_summaries.py tests/postgres/test_professor_output_summary_inputs.py -q -n0`
  - Result: passed, 6 passed.
  - Coverage: generator tests plus Postgres input-selection tests with
    Alembic upgrade through V025.

- `uv run --no-sync ruff check src/data_agents/professor/output_summaries.py tests/data_agents/professor/test_output_summaries.py tests/postgres/test_professor_output_summary_inputs.py`
  - Result: passed, `All checks passed!`.

- `openspec validate prof-summary-fields --strict`
  - Result: passed, `Change 'prof-summary-fields' is valid`.

Task status updated:
- T3.1 complete.
- T3.2 complete.
- T3.3 complete.
- T5.1 complete.

Next implementation step:
- Start T4 bounded backfill runner with dry-run mode, persistence of
  changed summaries, reporting, and refresh-signal emission.

## 2026-05-23 T4 backfill runner and dry-run sample

Scope:
- Complete T4.1, T4.2, T4.3, and T5.3.
- Finish all remaining `prof-summary-fields` implementation tasks.

Refresh-signal decision:
- Summary writes update `professor.run_id` for changed rows.
- `select_professors_for_research_vector_refresh(conn, run_id=...)`
  selects professors with changed output summaries for the later
  research-vector rebuild path.

RED command and outcome:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_output_summary_backfill.py -q -n0`
  - Result: failed during collection.
  - Expected failure:
    `ImportError: cannot import name 'run_output_summary_backfill'`.

Implementation:
- Extended `apps/miroflow-agent/src/data_agents/professor/output_summaries.py`.
- Added `OutputSummaryPersistenceResult`.
- Added `OutputSummaryBackfillReport`.
- Added `run_output_summary_backfill`.
- Added `select_professors_for_output_summary_backfill`.
- Added `persist_professor_output_summaries`.
- Added `select_professors_for_research_vector_refresh`.
- Added Postgres integration tests in
  `apps/miroflow-agent/tests/postgres/test_professor_output_summary_backfill.py`.

GREEN commands and outcomes:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_output_summary_backfill.py -q -n0`
  - Result: passed, 2 passed.
  - Coverage: bounded dry-run report without writes; write mode persists
    paper/patent summaries and emits a refresh selector signal.

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/storage/test_v025_migration.py tests/data_agents/professor/test_output_summaries.py tests/postgres/test_professor_output_summary_inputs.py tests/postgres/test_professor_output_summary_backfill.py -q -n0`
  - Result: passed, 11 passed.
  - Coverage: V025 migration, selector eligibility, mocked generator,
    bounded dry-run sample, persistence, and refresh selection.

- `uv run --no-sync ruff check src/data_agents/professor/output_summaries.py tests/data_agents/professor/test_output_summaries.py tests/postgres/test_professor_output_summary_inputs.py tests/postgres/test_professor_output_summary_backfill.py tests/storage/test_v025_migration.py`
  - Result: passed, `All checks passed!`.

- `openspec validate prof-summary-fields --strict`
  - Result: passed, `Change 'prof-summary-fields' is valid`.

Task status updated:
- T4.1 complete.
- T4.2 complete.
- T4.3 complete.
- T5.3 complete.

Bounded dry-run sample evidence:
- `test_output_summary_backfill_dry_run_reports_without_writing` runs
  `run_output_summary_backfill(..., dry_run=True, limit=1)` against
  migrated Postgres schema through V025.
- It verifies `processed == 1`, `failed == 0`,
  `paper_summaries_written == 1`, `patent_summaries_written == 1`,
  and unchanged persisted `professor.paper_summary` /
  `professor.patent_summary`.

Next implementation step:
- Run final `prof-summary-fields` close-out checks and, if clean, prepare
  this change for archive.
