# Verification

## Commands Run

### RED: Candidate model import gap

Command:

```bash
cd apps/miroflow-agent
uv run pytest tests/data_agents/professor/test_dataset_candidate_generation.py
```

Result: failed as expected before implementation with
`ModuleNotFoundError: No module named 'src.data_agents.professor.dataset_candidate_generation'`.

### Focused candidate model and generation tests

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/data_agents/professor/test_dataset_candidate_generation.py
```

Result: passed, `15 passed in 5.27s`.

### Candidate dry-run CLI test

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/scripts/test_run_professor_dataset_quality_closure.py::test_cli_candidate_dry_run_outputs_candidate_report
```

Result: passed, `1 passed in 5.30s`.

### Candidate write-mode handoff test

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/scripts/test_run_professor_dataset_quality_closure.py::test_cli_write_mode_accepts_candidate_dry_run_handoff
```

Result: passed, `1 passed in 5.51s`.

### Targeted regression suite

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/data_agents/professor/test_dataset_quality_closure.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `42 passed in 5.69s`.

### Ruff

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/professor/dataset_candidate_generation.py \
  scripts/run_professor_dataset_quality_closure.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `All checks passed!`.

### Real bounded candidate dry-run

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run python scripts/run_professor_dataset_quality_closure.py \
  --mode candidate-dry-run \
  --lane all \
  --bucket-limit 5 \
  --candidate-output /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-baseline-bucket5.json
```

Result: passed. Output artifact:
`.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-baseline-bucket5.json`.

Summary:

| Lane | Dataset Input | Input | Candidate | Validation Failures | Provider Failures | Skipped | Write Rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `profile_summary_repair` | 441 | 5 | 5 | 0 | 0 | 0 | 5 |
| `research_overview_backfill` | 2510 | 5 | 5 | 0 | 0 | 0 | 5 |
| `professor_paper_summary_generation` | 2200 | 5 | 2 | 0 | 0 | 3 | 2 |
| `duplicate_paper_merge` | 5186 | 5 | 2 | 3 | 0 | 0 | 2 |

Candidate report hashes:

- `selection_hash`: `038a3d51b7d297e69cd5de288d2d7a40b3e6f4d07cfb129bba307e64919803fa`
- `closure_selection_hash`: `89b3b4b83beb5cb2c45fdacbcf8ee185cc4b57614905dc146b7e01e1a7be682d`

### RED: Relaxed gate behavior still blocked weak candidates

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/data_agents/professor/test_dataset_candidate_generation.py -k "candidate_generation_report_counts or profile_and_research or paper_summary_candidate_requires or duplicate_merge_candidate_accepts or generate_professor_paper_summary_candidate_rejects or plan_duplicate_paper_merge_candidate_accepts_arxiv"
```

Result: failed as expected before the relaxed-gate implementation with 6
failures. Short Chinese profile summaries, unresolved duplicate paper-summary
candidates, and ambiguous duplicate merge groups were still rejected or counted
as validation failures.

### Focused relaxed gate tests

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/data_agents/professor/test_dataset_candidate_generation.py -k "candidate_generation_report_counts or profile_and_research or paper_summary_candidate_requires or duplicate_merge_candidate_accepts or generate_professor_paper_summary_candidate_rejects or plan_duplicate_paper_merge_candidate_accepts_arxiv"
```

Result: passed, `6 passed, 9 deselected in 5.53s`.

### Relaxed gate regression suite

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/data_agents/professor/test_dataset_quality_closure.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `42 passed in 5.63s`.

### Relaxed gate Ruff

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/professor/dataset_candidate_generation.py \
  scripts/run_professor_dataset_quality_closure.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `All checks passed!`.

### Relaxed gate real bounded candidate dry-run

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run python scripts/run_professor_dataset_quality_closure.py \
  --mode candidate-dry-run \
  --lane all \
  --bucket-limit 5 \
  --candidate-output /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-relaxed-bucket5.json
```

Result: passed. Output artifact:
`.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-relaxed-bucket5.json`.

Summary:

| Lane | Dataset Input | Input | Candidate | Validation Failures | Provider Failures | Skipped | Write Rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `profile_summary_repair` | 441 | 5 | 5 | 0 | 0 | 0 | 5 |
| `research_overview_backfill` | 2510 | 5 | 5 | 0 | 0 | 0 | 5 |
| `professor_paper_summary_generation` | 2200 | 5 | 3 | 0 | 0 | 2 | 3 |
| `duplicate_paper_merge` | 5186 | 5 | 5 | 0 | 0 | 0 | 5 |

Candidate report hashes:

- `selection_hash`: `96f490cbe3bff9cd93a563b0d42bd6ad6f7f0d287260d948b5b1328d1a0a8515`
- `closure_selection_hash`: `89b3b4b83beb5cb2c45fdacbcf8ee185cc4b57614905dc146b7e01e1a7be682d`

### Relaxed gate OpenSpec validation

Command:

```bash
openspec validate "professor-dataset-candidate-generation" --strict
```

Result: passed, `Change 'professor-dataset-candidate-generation' is valid`.

### RED: Real provider adapter missing

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py \
  -k "candidate_llm_provider or real_llm_provider or deterministic_mode or provider_mode"
```

Result: failed as expected before implementation with
`ModuleNotFoundError: No module named 'src.data_agents.professor.candidate_llm_provider'`.

### Focused real provider adapter and CLI tests

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py \
  -k "candidate_llm_provider or real_llm_provider or deterministic_mode or provider_mode"
```

Result: passed, `7 passed, 10 deselected in 5.59s`.

### Real provider integration regression suite

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/data_agents/professor/test_dataset_quality_closure.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `49 passed in 5.73s`.

### Real provider integration Ruff

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/professor/candidate_llm_provider.py \
  src/data_agents/professor/dataset_candidate_generation.py \
  scripts/run_professor_dataset_quality_closure.py \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `All checks passed!`.

### Default real-provider bounded dry-run

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run python scripts/run_professor_dataset_quality_closure.py \
  --mode candidate-dry-run \
  --lane profile_summary_repair \
  --bucket-limit 1 \
  --candidate-output /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-profile-bucket1.json \
  --provider-timeout-seconds 60 \
  --provider-retry-budget 0
```

Result: passed as a bounded dry-run command. The environment had no resolved
`DEEPSEEK_API_KEY`, so the sampled row recorded a provider failure instead of
falling back to deterministic synthesis.

Summary:

| Lane | Dataset Input | Input | Candidate | Validation Failures | Provider Failures | Skipped | Write Rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `profile_summary_repair` | 441 | 1 | 0 | 0 | 1 | 0 | 0 |

Provider failure evidence:

- `error_class`: `MissingLLMCredentials`
- `provider`: `deepseek-v4-pro`
- `provider_metadata`: `task_type=profile_summary_synthesis`, `llm_profile=deepseekv4pro`, `model=deepseek-v4-pro`, `timeout_seconds=60.0`, `retry_budget=0`

Candidate report hashes:

- `selection_hash`: `ed7921df54ec34e0110c5b2803e67f3ae599e7182c90f2bf6653012072f27e4b`
- `closure_selection_hash`: `cb2a6f6dcda2c0d9e083f0e8243419b7185e8c238cfdf0826f422356a56b7998`

## Observations

- The current `professor` table does not contain `institution`, `department`,
  or `title` columns. The profile-summary loader was adjusted to avoid
  assuming those fields exist.
- The deterministic profile-summary fallback can produce usable candidate
  shape, but some real rows contain noisy structured facts. First production
  batches should prefer an LLM provider with source-grounded prompts and manual
  sampling before write mode.
- Some duplicate merge candidates were rejected because source-page provenance
  was missing from the verified link rows even when identifier evidence was
  present.
- After the relaxed-gate amendment, missing duplicate-merge source-page
  provenance no longer blocks candidate reporting. It is recorded as
  `missing_source_page_provenance`, `source_confidence=weak`, and
  `write_recommendation=review_before_write`.

## Skipped Checks

- No broad write-mode remediation was executed.
- No external LLM provider was called in the real dry-run; provider paths and
  provider failure behavior were exercised with injectable fake providers in
  unit tests.
- Frontend/API detail route checks were not run because this slice did not
  write remediation data.

## Local dotenv loading and real provider success evidence

### RED: candidate dry-run CLI did not load app `.env`

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/scripts/test_run_professor_dataset_quality_closure.py -k loads_app_env
```

Result: failed as expected before implementation. The assertion showed no
`load_dotenv` call was made for `apps/miroflow-agent/.env`.

### GREEN: candidate dry-run CLI loads app `.env`

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/scripts/test_run_professor_dataset_quality_closure.py -k "loads_app_env or provider_mode or real_llm_provider or deterministic_mode"
```

Result: passed, `4 passed, 10 deselected in 5.29s`.

### Successful real-provider profile summary dry-run

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_professor_dataset_quality_closure.py \
  --database-url 'postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  --mode candidate-dry-run \
  --lane profile_summary_repair \
  --bucket-limit 1 \
  --candidate-output /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-profile-bucket1-dotenv.json \
  --provider-timeout-seconds 60 \
  --provider-retry-budget 0
```

Result: passed. Summary:

| Lane | Dataset Input | Input | Candidate | Validation Failures | Provider Failures | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `profile_summary_repair` | 441 | 1 | 1 | 0 | 0 | 0 |

The emitted candidate recorded self-check evidence, provider metadata,
`task_type=profile_summary_synthesis`, `model=deepseek-v4-pro`, prompt hash,
and response hash.

### Successful real-provider research translation dry-run

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_professor_dataset_quality_closure.py \
  --database-url 'postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  --mode candidate-dry-run \
  --lane research_overview_backfill \
  --bucket-limit 12 \
  --candidate-output /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-research-bucket12-translation-dotenv.json \
  --provider-timeout-seconds 90 \
  --provider-retry-budget 0
```

Result: passed. Summary:

| Lane | Dataset Input | Input | Candidate | Validation Failures | Provider Failures | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `research_overview_backfill` | 2510 | 12 | 12 | 0 | 0 | 0 |

Full `write_evidence_rows` included 11 `official_extract` candidates and one
`llm_translation` candidate. The translation candidate recorded self-check
evidence, provider metadata, `task_type=research_overview_translation`,
`model=deepseek-v4-pro`, prompt hash, and response hash.

### Successful real-provider Professor paper summary dry-run

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_professor_dataset_quality_closure.py \
  --database-url 'postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  --mode candidate-dry-run \
  --lane professor_paper_summary_generation \
  --bucket-limit 1 \
  --candidate-output /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-paper-summary-bucket1-dotenv.json \
  --provider-timeout-seconds 90 \
  --provider-retry-budget 0
```

Result: passed. Summary:

| Lane | Dataset Input | Input | Candidate | Validation Failures | Provider Failures | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `professor_paper_summary_generation` | 2200 | 1 | 1 | 0 | 0 | 0 |

The emitted candidate recorded self-check evidence, provider metadata,
`task_type=paper_summary_synthesis`, `model=deepseek-v4-pro`, prompt hash, and
response hash.

### Duplicate Paper merge lane coverage

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_professor_dataset_quality_closure.py \
  --database-url 'postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  --mode candidate-dry-run \
  --lane duplicate_paper_merge \
  --bucket-limit 1 \
  --candidate-output /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-duplicate-merge-bucket1-dotenv.json \
  --provider-timeout-seconds 60 \
  --provider-retry-budget 0
```

Result: passed. Summary:

| Lane | Dataset Input | Input | Candidate | Validation Failures | Provider Failures | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `duplicate_paper_merge` | 5186 | 1 | 1 | 0 | 0 | 0 |

The sampled candidate was `needs_review` with
`write_recommendation=review_before_write` and
`missing_source_page_provenance`.

### Post-dotenv regression suite

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/data_agents/professor/test_dataset_quality_closure.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `50 passed in 6.31s`.

### Post-dotenv Ruff

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/professor/candidate_llm_provider.py \
  src/data_agents/professor/dataset_candidate_generation.py \
  scripts/run_professor_dataset_quality_closure.py \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `All checks passed!`.

### RED: Parallel candidate dry-run gaps

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/scripts/test_run_professor_dataset_quality_closure.py -k "parallel_candidate or provider_limiter"
uv run pytest -n0 tests/data_agents/professor/test_dataset_candidate_generation.py -k "parallel_candidate_generation"
```

Result: failed as expected before implementation. CLI parsing rejected
`--candidate-concurrency`, `--provider-max-concurrency`, and
`--provider-min-interval-seconds`; `run()` rejected the new parallel kwargs;
and `dataset_candidate_generation` did not expose
`build_candidate_generation_report_for_buckets_parallel`.

### Parallel candidate dry-run focused tests

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/scripts/test_run_professor_dataset_quality_closure.py -k "parallel_candidate or provider_limiter"
uv run pytest -n0 tests/data_agents/professor/test_dataset_candidate_generation.py -k "parallel_candidate_generation"
uv run pytest -n0 tests/data_agents/professor/test_candidate_llm_provider.py -k "wraps_openai_client"
```

Result: passed. The CLI accepts parallel candidate and provider limiter
options, parallel generation uses worker connection factories and closes worker
connections, and the Professor DeepSeek-backed provider client is wrapped by
the shared provider rate limiter.

### Parallel candidate dry-run regression suite

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/data_agents/professor/test_dataset_quality_closure.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `54 passed in 7.09s`.

### Parallel candidate dry-run Ruff

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/professor/candidate_llm_provider.py \
  src/data_agents/professor/dataset_candidate_generation.py \
  scripts/run_professor_dataset_quality_closure.py \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py
```

Result: passed, `All checks passed!`.

### Parallel candidate dry-run OpenSpec validation

Command:

```bash
openspec validate "professor-dataset-candidate-generation" --strict
```

Result: passed, `Change 'professor-dataset-candidate-generation' is valid`.

### Bounded parallel real-provider dry-run

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_professor_dataset_quality_closure.py \
  --database-url 'postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  --mode candidate-dry-run \
  --lane profile_summary_repair \
  --lane research_overview_backfill \
  --lane professor_paper_summary_generation \
  --lane duplicate_paper_merge \
  --bucket-limit 20 \
  --candidate-concurrency 4 \
  --provider-max-concurrency 4 \
  --provider-min-interval-seconds 0.05 \
  --candidate-output /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-parallel-llm-bucket20.json \
  --provider-timeout-seconds 90 \
  --provider-retry-budget 0
```

Result: passed. Output artifact:
`.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-parallel-llm-bucket20.json`.

Summary:

| Lane | Input | Candidate | Validation Failures | Provider Failures | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| `profile_summary_repair` | 20 | 20 | 0 | 0 | 0 |
| `research_overview_backfill` | 20 | 20 | 0 | 0 | 0 |
| `professor_paper_summary_generation` | 20 | 11 | 0 | 0 | 9 |
| `duplicate_paper_merge` | 20 | 20 | 0 | 0 | 0 |

The `professor_paper_summary_generation` skipped rows were all
`duplicate_verified_paper_links`, confirming duplicate Paper cleanup must
precede broad Professor paper-summary writes for those rows.

### Read-only full closure audit

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_professor_core_profile_paper_quality_audit.py \
  --database-url 'postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  --include-buckets \
  --bucket-limit 100000 \
  > /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/core-profile-paper-quality-audit-full-buckets.json
```

Result: exited `1` as expected because readiness is `blocked`; the command was
read-only and wrote the local full row-level audit artifact. The committed
summary artifact is
`.agents/runs/professor-dataset-candidate-generation/core-profile-paper-quality-audit-full-summary.json`;
the full row-level artifact is kept local and untracked to avoid committing a
production-data dump. Summary:

| Blocker | Total rows |
| --- | ---: |
| `ready_summary_lt_200` | 441 |
| `missing_research_overview_zh` | 2510 |
| `missing_professor_paper_summary` | 2200 |
| `duplicate_verified_paper_title_year_groups` | 5186 |

The artifact expanded all `10,337` current closure bucket rows with no
truncation.

### Read-only full Paper title guard scan

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_bad_title_cleanup.py \
  --database-url 'postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  --confirm-real-db \
  > /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/paper-bad-title-cleanup-readonly-full.txt
```

Result: passed. The script examined `49,814` existing `paper.title_clean` rows,
rejected `1,597` as implausible title pollution, and did not execute
`--apply`.

### Read-only full Paper field coverage

Command:

```bash
cd apps/miroflow-agent
uv run python - <<'PY' > /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/paper-table-field-coverage.json
# one-off read-only aggregate SQL query
PY
```

Result: passed. Summary:

| Metric | Count |
| --- | ---: |
| Total Paper rows | 49814 |
| Orphan Paper rows | 0 |
| Missing `abstract_clean` | 39358 |
| Missing `summary_zh` | 39433 |
| Missing DOI | 36311 |
| Missing venue | 4328 |
| Present OpenAlex id | 11123 |
| Present Semantic Scholar id | 0 |

## Updated skipped checks

- No broad write-mode remediation was executed.
- No full-dataset real-provider candidate generation was executed;
  real-provider evidence is bounded to lane samples before broad write-mode
  remediation.
- Frontend/API detail route checks were not run because this slice did not
  write remediation data.
