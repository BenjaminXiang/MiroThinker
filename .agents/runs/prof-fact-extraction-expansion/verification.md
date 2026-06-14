# Verification: prof-fact-extraction-expansion

## Pending

This child run workspace was created by the `prof-admin-workbench`
parent close-out (T2.3) on 2026-05-23.

Implementation and E2E evidence must be added here when the
`prof-fact-extraction-expansion` phase starts. Do not mark this child
complete until its own `tasks.md`, `acceptance.md`, and verification
commands are updated with current evidence.

## 2026-05-23 T1 review gate

Scope:
- Complete T1.1 and T1.3 only.
- Verify the child spec is aligned with the completed quality-status
  parent/child contract before implementation.
- Confirm the approved LLM-client pattern before extractor or runner
  code is written.

Commands and current-state evidence:

- `openspec status --change prof-fact-extraction-expansion --json`
  - Result: schema `spec-driven`, all artifacts present.

- `openspec instructions apply --change prof-fact-extraction-expansion --json`
  - Result before T1 updates: 1/24 tasks complete, 23 remaining.

- `sed -n '1,260p' openspec/specs/professor-admin-workbench/spec.md`
  - Result: synced parent spec requires four-state quality semantics,
    quality-gate reason persistence, watermark-bound overrides, and a
    standalone re-evaluation entry point.

- `sed -n '1,260p' openspec/changes/archive/2026-05-23-prof-quality-status-rework/specs/professor-quality-status/spec.md`
  - Result: archived child spec confirms the re-evaluation contract and
    the exact `professor_quality_gate` reason persistence behavior this
    fact backfill must call after writing facts.

- `sed -n '1,260p' apps/miroflow-agent/scripts/run_professor_quality_re_eval.py`
  - Result: current re-evaluation entry point is
    `run_re_eval(args)`, backed by `evaluate_professor_quality`,
    `load_professor_canonical_states`, and
    `persist_professor_quality_evaluation`.

- `sed -n '1,260p' apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py`
  - Result: approved LLM-client pattern is
    `resolve_professor_llm_settings("gemma4", include_profile=True)`,
    OpenAI-compatible client construction, and an owned
    `httpx.Client(timeout=90.0, trust_env=False)` to avoid ambient proxy
    inheritance.

Task status updated:
- T1.1 complete.
- T1.3 complete.

Next implementation step:
- Start T2 preflight with RED Postgres tests for eligible rows,
  missing-summary counts, target fact gaps, and skipped no-raw-text
  rows.

## 2026-05-23 T2 preflight implementation

Scope:
- Complete T2.1, T2.2, and T2.3.
- Also complete T6.3 because the read-only `miroflow_real` preflight was
  executed and recorded.

RED commands and outcomes:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_preflight.py -q -n0`
  - First RED result: collection error,
    `ModuleNotFoundError: No module named
    'src.data_agents.professor.fact_backfill'`.

- After adding a minimal import skeleton:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_preflight.py -q -n0`
  - Second RED result: failed on the intended behavior assertion,
    `assert report.total_professors == 4`, with actual `0`.

GREEN commands and outcomes:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_preflight.py -q -n0`
  - Result: passed, 1 passed.
  - Coverage: seeded migrated Postgres state with four professors,
    two eligible rows, two skipped rows, one missing summary among
    eligible rows, active/deprecated fact boundaries, and all four
    target fact gap counts.

- `uv run --no-sync ruff check src/data_agents/professor/fact_backfill.py tests/postgres/test_professor_fact_backfill_preflight.py`
  - Result: passed, `All checks passed!`.

Read-only real preflight:

- `uv run --no-sync python - <<'PY' ... compute_fact_backfill_preflight(conn) ... PY`
  against `postgresql://miroflow:miroflow@localhost:15432/miroflow_real`
  - Result: exited 0.
  - Counts:
    - total non-merged professors: `495`
    - eligible non-empty `profile_raw_text`: `253`
    - skipped no/blank `profile_raw_text`: `242`
    - missing `profile_summary` among eligible rows: `250`
    - active target facts:
      `education=0`, `work_experience=0`, `award=0`,
      `academic_position=0`
    - missing target facts:
      `education=253`, `work_experience=253`, `award=253`,
      `academic_position=253`

Task status updated:
- T2.1 complete.
- T2.2 complete.
- T2.3 complete.
- T6.3 complete.

Next implementation step:
- Start T3 structured extractor with mocked-client RED tests for
  `education`, `work_experience`, `award`, and `academic_position`,
  malformed JSON, and low-confidence preservation.

## 2026-05-23 T3 extractor implementation

Scope:
- Complete T3.1, T3.2, T3.3, and T3.4.
- Stay within extractor/parser behavior only; persistence and runner
  wiring remain pending.

RED command and outcome:

- `uv run --no-sync pytest tests/data_agents/professor/test_fact_extraction.py -q -n0`
  - Result: failed with 7 intended behavior failures. The import API was
    present, but the skeleton returned no facts and no malformed/LLM
    error strings.

GREEN commands and outcomes:

- `uv run --no-sync pytest tests/data_agents/professor/test_fact_extraction.py -q -n0`
  - Result: passed, 7 passed.
  - Coverage: all target fact types (`education`, `work_experience`,
    `award`, `academic_position`), fenced JSON parsing, injected model
    and `extra_body`, low-confidence preservation, malformed-output
    safe error return, and LLM exception safe error return.

- `uv run --no-sync ruff check src/data_agents/professor/fact_backfill.py tests/data_agents/professor/test_fact_extraction.py`
  - Result: passed, `All checks passed!`.

Task status updated:
- T3.1 complete.
- T3.2 complete.
- T3.3 complete.
- T3.4 complete.

Next implementation step:
- Start T4 persistence with RED tests for active-fact idempotency,
  provenance preservation, and `academic_position` coverage.

## 2026-05-23 T4 persistence implementation

Scope:
- Complete T4.1 through T4.5.
- Also complete T6.1 because extractor and persistence checks were run
  after the persistence implementation.
- Keep runner, batch failure isolation, real bounded LLM backfill, and
  post-backfill quality re-evaluation pending for T5/T6.

RED commands and outcomes:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_persistence.py -q -n0`
  - First RED result: collection error,
    `ImportError: cannot import name 'ProfessorFactPersistenceReport'`
    from `src.data_agents.professor.fact_backfill`.

- After adding a minimal persistence API skeleton:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_persistence.py -q -n0`
  - Second RED result: 3 intended failures. The skeleton returned
    `facts_written=0` where the tests expected inserted and updated
    `professor_fact` rows.

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/professor/test_canonical_writer.py::test_academic_positions_become_facts -q -n0`
  - Intended RED result: failed because no `academic_position` facts were
    written by `write_professor_bundle`.
  - One earlier setup-only run failed because only `DATABASE_URL_TEST`
    was set while this legacy fixture calls `seed_loader.load_all()`
    through `DATABASE_URL`; this was not counted as behavior evidence.

Implementation notes:
- Extended `canonical_writer._upsert_fact(...)` to accept
  `value_normalized` and to dedupe active facts by
  `professor_id + fact_type + normalized_fact_key`, independent of
  `source_page_id` and `evidence_span`.
- Added `persist_extracted_professor_facts(...)` and
  `ProfessorFactPersistenceReport` to `fact_backfill.py`. The backfill
  helper reuses the canonical writer fact write helper.
- Added canonical writer support for `academic_positions` as
  `fact_type = academic_position`.

GREEN commands and outcomes:

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_persistence.py -q -n0`
  - Result: passed, 3 passed.
  - Coverage: provenance/run id/status persistence,
    `academic_position` persistence, normalized-key idempotency across
    different source pages and evidence spans, and missing-normalized
    fallback to raw normalized key.

- `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_preflight.py tests/postgres/test_professor_fact_backfill_persistence.py -q -n0`
  - Result: passed, 4 passed.
  - Coverage: T2 preflight plus T4 migrated-Postgres persistence checks.

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/professor/test_canonical_writer.py::test_academic_positions_become_facts -q -n0`
  - Result: passed, 1 passed.

- `uv run --no-sync pytest tests/data_agents/professor/test_fact_extraction.py -q -n0`
  - Result: passed, 7 passed.

- `uv run --no-sync ruff check src/data_agents/professor/fact_backfill.py src/data_agents/professor/canonical_writer.py tests/data_agents/professor/test_fact_extraction.py tests/postgres/test_professor_fact_backfill_preflight.py tests/postgres/test_professor_fact_backfill_persistence.py tests/professor/test_canonical_writer.py`
  - Result: passed, `All checks passed!`.

Operational caveat:
- Postgres tests that run Alembic upgrade/downgrade against the same
  `miroflow_test_mock` database must be run serially. A parallel trial
  caused a migration setup collision on `seed_registry`; serial reruns
  passed.

Task status updated:
- T4.1 complete.
- T4.2 complete.
- T4.3 complete.
- T4.4 complete.
- T4.5 complete.
- T6.1 complete.

Next implementation step:
- Start T5 runner with RED tests for a bounded `run_*` entrypoint,
  shared profile-text input, per-professor failure isolation, and the
  Child 1 quality re-evaluation call.

## 2026-05-23 T5 runner implementation

Scope:
- Complete T5.1, T5.2, T5.3, and T5.4.
- Also complete T6.2 because the runner was verified with mocked LLM,
  mocked persistence, and mocked quality re-evaluation.
- Do not mark T6.4 or T6.5 complete; no bounded real backfill sample or
  before/after quality distribution has been executed yet.

RED command and outcome:

- `uv run --no-sync pytest tests/scripts/test_run_professor_fact_backfill.py -q -n0`
  - RED result: failed with 4 `FileNotFoundError` failures because
    `scripts/run_professor_fact_backfill.py` did not exist.

Implementation notes:
- Added `scripts/run_professor_fact_backfill.py`.
- The runner preflights current eligible rows, selects non-merged
  professors with non-empty `profile_raw_text`, and reports
  `processed`, `skipped`, `failed`, `facts_written`, `facts_updated`,
  `facts_skipped`, `summaries_written`, and `re_evaluated`.
- The runner passes the same trimmed `profile_raw_text` to
  `extract_professor_facts(...)` and
  `generate_reinforced_profile_summary(..., bio=...)`.
- Per-professor exceptions roll back that professor's work, increment
  `failed`, and continue the batch.
- Successful batches call `run_re_eval(...)` from
  `scripts/run_professor_quality_re_eval.py` unless
  `--skip-re-eval` is set.
- `_open_llm_client()` follows the approved local Gemma4 pattern with
  `httpx.Client(timeout=90.0, trust_env=False)`.

GREEN commands and outcomes:

- `uv run --no-sync pytest tests/scripts/test_run_professor_fact_backfill.py -q -n0`
  - Result: passed, 4 passed.
  - Coverage: eligible SQL, shared profile raw text into extractor and
    summary generation, persistence and summary write dispatch,
    per-professor failure isolation, quality re-evaluation invocation,
    and CLI JSON output.

- `uv run --no-sync pytest tests/scripts/test_run_professor_fact_backfill.py tests/data_agents/professor/test_fact_extraction.py -q -n0`
  - Result: passed, 11 passed.

- `uv run --no-sync ruff check scripts/run_professor_fact_backfill.py tests/scripts/test_run_professor_fact_backfill.py src/data_agents/professor/fact_backfill.py src/data_agents/professor/canonical_writer.py`
  - Result: passed, `All checks passed!`.

Task status updated:
- T5.1 complete.
- T5.2 complete.
- T5.3 complete.
- T5.4 complete.
- T6.2 complete.

Next implementation step:
- Run a bounded real backfill sample only after review/approval for
  T6.4, then record before/after quality distribution for T6.5.

## 2026-05-23 T6.4/T6.5 bounded real sample

Scope:
- Complete T6.4 and T6.5.
- Run one bounded real sample on `miroflow_real`.
- Record the concrete run id and before/after quality distribution.

Read-only candidate selection:

- `uv run --no-sync python - <<'PY' ... candidate query ... PY`
  against `postgresql://miroflow:miroflow@localhost:15432/miroflow_real`
  - Result: exited 0.
  - Before quality distribution:
    `{"needs_enrichment": 493, "ready": 2}`.
  - Selected candidate:
    - professor_id: `PROF-0012FFC9DEC2`
    - canonical_name: `毛润泽`
    - quality_status: `needs_enrichment`
    - profile_raw_text length: `4991`
    - profile_summary length: `0`
    - active target facts before: `0`

Dry-run smoke:

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_professor_fact_backfill.py --id PROF-0012FFC9DEC2 --limit 1 --dry-run --skip-re-eval`
  - Result: exited 0.
  - LLM evidence: two Gemma4 `/chat/completions` requests returned
    HTTP 200.
  - Report:
    `{"run_id":"563ae459-9529-461a-b55d-3e7cdf700a8c","eligible":1,"processed":1,"skipped":242,"failed":0,"facts_written":16,"facts_updated":0,"facts_skipped":0,"summaries_written":1,"re_evaluated":0,"dry_run":true,"duration_seconds":15.96}`.

Real bounded sample:

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_professor_fact_backfill.py --id PROF-0012FFC9DEC2 --limit 1`
  - Result: exited 0.
  - LLM evidence: two Gemma4 `/chat/completions` requests returned
    HTTP 200.
  - Report:
    `{"run_id":"b4da92b2-5010-40e4-819f-b2d32b9d7065","eligible":1,"processed":1,"skipped":242,"failed":0,"facts_written":17,"facts_updated":0,"facts_skipped":0,"summaries_written":1,"re_evaluated":1,"dry_run":false,"duration_seconds":16.21}`.

Read-only after verification:

- `uv run --no-sync python - <<'PY' ... after query ... PY`
  against `postgresql://miroflow:miroflow@localhost:15432/miroflow_real`
  - Result: exited 0.
  - After quality distribution:
    `{"needs_enrichment": 493, "ready": 2}`.
  - Candidate after state:
    - professor_id: `PROF-0012FFC9DEC2`
    - canonical_name: `毛润泽`
    - quality_status: `needs_enrichment`
    - profile_summary length: `658`
    - professor run_id:
      `b4da92b2-5010-40e4-819f-b2d32b9d7065`
  - Active fact rows written by the real sample run:
    `academic_position=1`, `award=10`, `education=3`,
    `work_experience=3`.
  - Sample fact checks: non-null source page, evidence spans, and
    confidence values were present.

Rollback checkpoint:
- The real sample is traceable by run id
  `b4da92b2-5010-40e4-819f-b2d32b9d7065`.

Task status updated:
- T6.4 complete.
- T6.5 complete.

Next implementation step:
- `prof-fact-extraction-expansion` is ready for final validation and
  archive.
