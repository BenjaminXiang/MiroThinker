# Verification: prof-fact-extraction-expansion

Date: 2026-05-15

## TDD evidence

- RED:
  - `uv run pytest -n0 tests/data_agents/professor/test_fact_extraction.py -q`
    failed with `ModuleNotFoundError:
    src.data_agents.professor.fact_extraction`.
  - `uv run pytest -n0 tests/scripts/test_run_professor_fact_backfill.py -q`
    failed with `ModuleNotFoundError:
    scripts.run_professor_fact_backfill`.
  - A later proxy-safety regression test failed because `_open_llm_client`
    did not pass `http_client`.
- GREEN:
  - Added `src/data_agents/professor/fact_extraction.py`.
  - Added `scripts/run_professor_fact_backfill.py`.
  - Added `httpx.Client(trust_env=False)` for proxy-safe OpenAI client
    construction.

## Commands

- `UV_INDEX_URL=https://pypi.org/simple DATABASE_URL_TEST=postgresql://miroflow:miroflow@localhost:15432/miroflow_test_mock uv run pytest -n0 tests/data_agents/professor/test_fact_extraction.py -q`
  - Result: `5 passed`.
- `UV_INDEX_URL=https://pypi.org/simple uv run pytest -n0 tests/scripts/test_run_professor_fact_backfill.py -q`
  - Result: `3 passed`.
- `UV_INDEX_URL=https://pypi.org/simple uv run ruff check src/data_agents/professor/fact_extraction.py scripts/run_professor_fact_backfill.py tests/data_agents/professor/test_fact_extraction.py tests/scripts/test_run_professor_fact_backfill.py`
  - Result: passed.

## Real-data preflight

Command:

```bash
timeout 60s env UV_INDEX_URL=https://pypi.org/simple \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_professor_fact_backfill.py --preflight-only
```

Result:

```json
{
  "total_professors": 495,
  "eligible_count": 253,
  "skipped_missing_profile_raw_text": 242,
  "missing_profile_summary_count": 250,
  "missing_fact_counts": {
    "academic_position": 253,
    "award": 253,
    "education": 253,
    "work_experience": 253
  },
  "existing_active_fact_counts": {
    "academic_position": 0,
    "award": 0,
    "education": 0,
    "work_experience": 0
  }
}
```

## Bounded dry-run

Command:

```bash
timeout 180s env UV_INDEX_URL=https://pypi.org/simple \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_professor_fact_backfill.py --limit 1 --dry-run
```

Result:

- The script used the dry-run sentinel run id
  `00000000-0000-0000-0000-000000000000`.
- It performed no `pipeline_run` write after the dry-run fix.
- The configured local LLM profile reached the endpoint but returned
  `401 Unauthorized`, so no wet real sample or before/after real quality
  distribution was produced in this environment.
- The accidental dry-run `pipeline_run` row from the pre-fix attempt
  (`46723e38-354b-428b-b62d-e2b792edf569`) was deleted.
