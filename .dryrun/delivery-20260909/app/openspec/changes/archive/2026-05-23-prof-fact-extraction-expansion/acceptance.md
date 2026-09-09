# Acceptance: prof-fact-extraction-expansion

## 1. Spec validation

- [x] `openspec validate prof-fact-extraction-expansion` exits 0.
- [x] Child spec review is complete before implementation starts.

## 2026-05-23 T1 review gate evidence

- The archived `professor-quality-status` spec and the synced
  `professor-admin-workbench` spec both require four-state professor
  quality evaluation, non-ready reason persistence through
  `professor_quality_gate`, and standalone re-evaluation of existing
  professor rows. This child remains aligned because it writes missing
  structured facts and then invokes the existing quality re-evaluation
  entry point instead of introducing new quality-status semantics.
- `apps/miroflow-agent/scripts/run_professor_quality_re_eval.py`
  provides the Child 1 re-evaluation entry point through
  `run_re_eval(args)`, using `evaluate_professor_quality`,
  `load_professor_canonical_states`, and
  `persist_professor_quality_evaluation`.
- The approved LLM pattern for this backfill is the proxy-safe
  OpenAI-compatible local Gemma4 client used by
  `scripts/run_paper_summary_zh_backfill.py`:
  `resolve_professor_llm_settings("gemma4", include_profile=True)`,
  `OpenAI(...)`, and an owned `httpx.Client(timeout=90.0,
  trust_env=False)`. Extractor tests must inject mocked clients and
  make no real HTTP calls.

## 2. Preflight evidence

- [x] Eligible professor count with non-empty `profile_raw_text` is
  recorded.
- [x] Missing-summary count is recorded.
- [x] Missing target fact counts are recorded for `education`,
  `work_experience`, `award`, and `academic_position`.
- [x] Skipped rows without `profile_raw_text` are recorded.

## 2026-05-23 T2 preflight evidence

Implementation:

- Added `src/data_agents/professor/fact_backfill.py` with
  `TARGET_FACT_TYPES`, `FactBackfillPreflightReport`, and
  `compute_fact_backfill_preflight(conn)`.
- The preflight treats non-`merged_into` professors with non-empty
  trimmed `profile_raw_text` as eligible.
- It reports total non-merged professors, eligible professor count,
  skipped no-raw-text count, missing `profile_summary` count among
  eligible rows, active fact counts per target type, missing fact counts
  per target type, and the ordered eligible professor ids for a bounded
  runner.

RED/GREEN:

- RED:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_preflight.py -q -n0`
  failed first because `src.data_agents.professor.fact_backfill` did
  not exist, then failed on the expected assertion
  `report.total_professors == 4` after the import skeleton was added.
- GREEN:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_preflight.py -q -n0`
  passed: 1 passed.
- `uv run --no-sync ruff check src/data_agents/professor/fact_backfill.py tests/postgres/test_professor_fact_backfill_preflight.py`
  passed.

`miroflow_real` read-only preflight:

```json
{
  "total_professors": 495,
  "eligible_professor_count": 253,
  "skipped_no_profile_raw_text_count": 242,
  "missing_profile_summary_count": 250,
  "active_fact_counts": {
    "education": 0,
    "work_experience": 0,
    "award": 0,
    "academic_position": 0
  },
  "missing_fact_counts": {
    "education": 253,
    "work_experience": 253,
    "award": 253,
    "academic_position": 253
  }
}
```

## 3. Extraction and persistence

- [x] Each target fact type has unit test coverage.
- [x] Malformed LLM output is rejected or safely skipped.
- [x] Low-confidence facts retain confidence values for downstream
  review.
- [x] Facts are written with provenance and run id.
- [x] Re-running the same batch does not duplicate active facts.
- [x] Duplicate detection uses
  `professor_id + fact_type + normalized_fact_key`.
- [x] Re-seeing the same normalized fact from a different source page or
  evidence span updates or supplements the existing active fact instead
  of creating another active row.

## 2026-05-23 T3 extractor evidence

Implementation:

- Extended `src/data_agents/professor/fact_backfill.py` with
  `ExtractedProfessorFact`, `ProfessorFactExtractionResult`, and
  `extract_professor_facts(...)`.
- The extractor calls the injected OpenAI-compatible client with an
  explicit JSON-only prompt, the selected model, deterministic
  temperature, and caller-supplied `extra_body`.
- The parser accepts fenced or plain JSON, requires a top-level
  `facts` list, validates target `fact_type`, non-empty raw/evidence
  text, optional normalized value, and confidence in `[0, 1]`.
- Low-confidence facts are preserved for downstream review instead of
  being filtered.
- Malformed output and LLM exceptions return an empty fact tuple with an
  error string instead of raising.

RED/GREEN:

- RED:
  `uv run --no-sync pytest tests/data_agents/professor/test_fact_extraction.py -q -n0`
  failed with 7 behavior failures while the extractor skeleton returned
  no facts and no errors.
- GREEN:
  `uv run --no-sync pytest tests/data_agents/professor/test_fact_extraction.py -q -n0`
  passed: 7 passed.
- `uv run --no-sync ruff check src/data_agents/professor/fact_backfill.py tests/data_agents/professor/test_fact_extraction.py`
  passed.

## 2026-05-23 T4 persistence evidence

Implementation:

- Extended the existing `canonical_writer._upsert_fact(...)` write
  helper with `value_normalized` support and the active-fact key
  `professor_id + fact_type + normalized_fact_key`.
- `normalized_fact_key` is `value_normalized` when present, otherwise a
  deterministic normalized form of `value_raw` using trimming,
  case-folding, and whitespace collapse.
- `source_page_id` and `evidence_span` are no longer part of duplicate
  detection. Re-seeing the same normalized fact updates the active row's
  raw value, normalized value, source page, evidence span, confidence,
  and run id instead of creating another active row.
- Added `persist_extracted_professor_facts(...)` in
  `src/data_agents/professor/fact_backfill.py`; it reuses the shared
  `professor_fact` write helper and reports written/updated/skipped
  counts.
- Wired `academic_positions` from the canonical writer into
  `professor_fact` rows with `fact_type = academic_position`.

RED/GREEN:

- RED:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_persistence.py -q -n0`
  first failed on missing persistence API, then failed on the intended
  written/updated assertions after the import skeleton was added.
- RED:
  `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/professor/test_canonical_writer.py::test_academic_positions_become_facts -q -n0`
  failed because the current canonical writer produced no
  `academic_position` fact rows.
- GREEN:
  `DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/postgres/test_professor_fact_backfill_preflight.py tests/postgres/test_professor_fact_backfill_persistence.py -q -n0`
  passed: 4 passed.
- GREEN:
  `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run --no-sync pytest tests/professor/test_canonical_writer.py::test_academic_positions_become_facts -q -n0`
  passed: 1 passed.
- `uv run --no-sync pytest tests/data_agents/professor/test_fact_extraction.py -q -n0`
  passed: 7 passed.
- `uv run --no-sync ruff check src/data_agents/professor/fact_backfill.py src/data_agents/professor/canonical_writer.py tests/data_agents/professor/test_fact_extraction.py tests/postgres/test_professor_fact_backfill_preflight.py tests/postgres/test_professor_fact_backfill_persistence.py tests/professor/test_canonical_writer.py`
  passed.

## 4. Backfill and re-evaluation

- [x] Runner reports processed, skipped, failed, facts_written, and
  summaries_written counts.
- [x] Per-professor LLM failure does not abort the batch.
- [x] Post-backfill re-evaluation runs through the Child 1 entry point.
- [x] Quality-status distribution is recorded before and after the
  backfill sample.

## 2026-05-23 T5 runner evidence

Implementation:

- Added `scripts/run_professor_fact_backfill.py` with a `run_*` style
  CLI and a testable `run_backfill(args)` entry point.
- The runner performs preflight, selects non-merged professors with
  non-empty `profile_raw_text`, extracts structured facts, persists
  facts, optionally refreshes `profile_summary`, isolates
  per-professor failures, and reports `processed`, `skipped`, `failed`,
  `facts_written`, `facts_updated`, `facts_skipped`,
  `summaries_written`, and `re_evaluated`.
- The same trimmed `profile_raw_text` value is passed to both
  `extract_professor_facts(...)` and
  `generate_reinforced_profile_summary(..., bio=...)`.
- Successful batches call the Child 1 quality re-evaluation entry point
  through `run_re_eval(...)`.
- The LLM client follows the approved proxy-safe local Gemma4 pattern
  with an owned `httpx.Client(timeout=90.0, trust_env=False)`.

RED/GREEN:

- RED:
  `uv run --no-sync pytest tests/scripts/test_run_professor_fact_backfill.py -q -n0`
  first failed because `scripts/run_professor_fact_backfill.py` did not
  exist.
- GREEN:
  `uv run --no-sync pytest tests/scripts/test_run_professor_fact_backfill.py -q -n0`
  passed: 4 passed.
- Combined runner/extractor verification:
  `uv run --no-sync pytest tests/scripts/test_run_professor_fact_backfill.py tests/data_agents/professor/test_fact_extraction.py -q -n0`
  passed: 11 passed.
- `uv run --no-sync ruff check scripts/run_professor_fact_backfill.py tests/scripts/test_run_professor_fact_backfill.py src/data_agents/professor/fact_backfill.py src/data_agents/professor/canonical_writer.py`
  passed.

## 2026-05-23 T6.4/T6.5 bounded real sample evidence

Candidate and before state:

- Selected `PROF-0012FFC9DEC2` (`毛润泽`) from `miroflow_real`.
- Before sample:
  - `profile_raw_text` length: 4991
  - `profile_summary` length: 0
  - active target facts: 0
  - quality status: `needs_enrichment`
- Quality distribution before:
  `{"needs_enrichment": 493, "ready": 2}`.

Dry-run smoke:

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_professor_fact_backfill.py --id PROF-0012FFC9DEC2 --limit 1 --dry-run --skip-re-eval`
  exited 0 after two Gemma4 HTTP 200 responses.
- Dry-run report:
  `{"run_id":"563ae459-9529-461a-b55d-3e7cdf700a8c","eligible":1,"processed":1,"skipped":242,"failed":0,"facts_written":16,"facts_updated":0,"facts_skipped":0,"summaries_written":1,"re_evaluated":0,"dry_run":true,"duration_seconds":15.96}`.

Real bounded sample:

- `DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real uv run --no-sync python scripts/run_professor_fact_backfill.py --id PROF-0012FFC9DEC2 --limit 1`
  exited 0 after two Gemma4 HTTP 200 responses.
- Real sample report:
  `{"run_id":"b4da92b2-5010-40e4-819f-b2d32b9d7065","eligible":1,"processed":1,"skipped":242,"failed":0,"facts_written":17,"facts_updated":0,"facts_skipped":0,"summaries_written":1,"re_evaluated":1,"dry_run":false,"duration_seconds":16.21}`.

After state:

- `PROF-0012FFC9DEC2` remained `needs_enrichment`, with
  `profile_summary` length 658 and professor `run_id =
  b4da92b2-5010-40e4-819f-b2d32b9d7065`.
- Active facts written by the sample run:
  `academic_position=1`, `award=10`, `education=3`,
  `work_experience=3`.
- Sample fact rows include non-null source pages, evidence spans, and
  confidence values.
- Quality distribution after:
  `{"needs_enrichment": 493, "ready": 2}`.
