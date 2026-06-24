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

## Research Overview Source Cleaning Follow-Up

### Scope

This follow-up closes the research-overview source-quality gap where official
Chinese source spans could include teaching, recruitment, contact, link,
publication-heading, award, and navigation noise. It also treats
teacher-maintained `.github.io` personal homepages as recursive same-host
supplementary sources.

### RED/GREEN Evidence

Command:

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  -u all_proxy -u ALL_PROXY -u no_proxy -u NO_PROXY \
  UV_CACHE_DIR=/tmp/mirothinker-uv-cache.codex \
  uv run pytest \
  tests/data_agents/professor/test_profile_sections.py::test_build_research_overview_section_cleans_noisy_chinese_source \
  -n0
```

Result: RED failed before the old profile-section path was guarded because the
Chinese noisy source was written as `official_extract` without calling the
cleaner; passed after the fix.

Command:

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  -u all_proxy -u ALL_PROXY -u no_proxy -u NO_PROXY \
  UV_CACHE_DIR=/tmp/mirothinker-uv-cache.codex \
  uv run pytest \
  tests/data_agents/professor/test_candidate_llm_provider.py::test_candidate_llm_provider_accepts_empty_research_overview_absence \
  -n0
```

Result: RED failed when DeepSeek-style empty research-overview JSON with
`quality_flags=["missing_research_overview_source=true"]` was retried as
malformed; passed after empty source-limitation output was accepted.

### Verification

Command:

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  -u all_proxy -u ALL_PROXY -u no_proxy -u NO_PROXY \
  UV_CACHE_DIR=/tmp/mirothinker-uv-cache.codex \
  uv run pytest \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_multi_source_crawler.py \
  tests/data_agents/professor/test_profile_sections.py \
  tests/scripts/test_run_professor_raw_text_re_scrape.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py \
  -n0
```

Result: passed, `82 passed in 7.62s`.

Command:

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  -u all_proxy -u ALL_PROXY -u no_proxy -u NO_PROXY \
  UV_CACHE_DIR=/tmp/mirothinker-uv-cache.codex \
  uv run ruff check \
  src/data_agents/professor/dataset_candidate_generation.py \
  src/data_agents/professor/candidate_llm_provider.py \
  src/data_agents/professor/multi_source_crawler.py \
  src/data_agents/professor/profile_sections.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_multi_source_crawler.py \
  tests/data_agents/professor/test_profile_sections.py
```

Result: passed, `All checks passed!`.

Command:

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  -u all_proxy -u ALL_PROXY -u no_proxy -u NO_PROXY \
  UV_CACHE_DIR=/tmp/mirothinker-uv-cache.codex \
  DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
  uv run python scripts/run_professor_dataset_quality_closure.py \
  --mode candidate-dry-run \
  --lane research_overview_backfill \
  --bucket-limit 5 \
  --provider-mode real \
  --provider-timeout-seconds 60 \
  --provider-retry-budget 1 \
  --provider-max-concurrency 1 \
  --provider-min-interval-seconds 0.2 \
  --candidate-output /tmp/professor-research-overview-cleaning-candidate-dry-run-v4.json
```

Result: passed. The artifact was copied to
`.agents/runs/professor-dataset-candidate-generation/research-overview-cleaning-candidate-dry-run-bucket5.json`.
It reports `input_count=5`, `candidate_count=3`, `skipped_count=2`,
`provider_failure_count=0`, and `validation_failure_count=0`. The three ready
candidates used `generation_method=llm_cleaning`; the two skipped rows were
classified as `source_missing_after_llm_cleaning` with source URL/hash and LLM
self-check evidence.

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

- Superseded by later real-provider, parallel cleaning, and write-mode evidence
  below. This section is retained as the historical checkpoint for the first
  candidate-generation slice.

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

- Superseded by the final current-data cleaning evidence below.

## Current data cleaning and write-mode evidence

### RED: Paper title-quality heuristic rejected real titles

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/data_agents/paper/test_title_quality.py::test_accepts_real_paper_titles -q
```

Result: failed as expected before the title-quality repair. The heuristic
treated title-case technical paper titles containing `and` as author-prefixed
citation records.

Regression cases:

- `Removing Interference and Recovering Content Imaginatively for Visible
  Watermark Removal`
- `Human Obedience and Social Norm Adherence in Small Groups with Virtual
  Agents`

### GREEN: Paper title-quality regression suite

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 tests/data_agents/paper/test_title_quality.py -q
```

Result: passed, `300 passed`.

The author-prefixed citation detector now requires an author-name signal before
rejecting the `X Y and Z W ...` pattern.

### Paper title-enrichment plan-only after title-quality repair

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run python scripts/run_paper_title_enrichment_backfill.py \
  --plan-only \
  > /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/paper-title-enrichment-plan-only-after-title-quality-fix.json
```

Result: passed as read-only evidence. Summary:

| Metric | Count |
| --- | ---: |
| `papers_total` | 33960 |
| `resolver_candidates` | 32546 |
| `implausible_titles` | 1342 |
| `missing_title_or_links` | 72 |
| `unsafe_links_filtered` | 81 |
| `unsafe_link_rows` | 81 |

The two regression titles above no longer appear in the implausible-title
sample.

### Read-only bad-title cleanup after title-quality repair

Command:

```bash
cd apps/miroflow-agent
uv run python scripts/run_bad_title_cleanup.py \
  --database-url 'postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  --confirm-real-db \
  > /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/paper-bad-title-cleanup-after-title-quality-fix.txt
```

Result: passed in read-only mode. The command examined `49,814` rows and
rejected `1,542`, but no `--apply` was executed because the sample still
included plausible real titles such as `Ranked Items Auctions and Online
Advertisement`, `Intelligent Making and Robotic Structure`, and Chinese book or
design titles.

### Paper summary DOI enrichment dry-run

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run python scripts/run_paper_summary_zh_backfill.py \
  --limit 10 \
  --enrich-doi-metadata \
  --llm-profile deepseekv4pro \
  --dry-run
```

Result: passed. Output artifact:
`.agents/runs/professor-dataset-candidate-generation/paper-summary-zh-backfill-enrich-doi-dry-run-limit10.json`.

Summary: `papers_total=10`, `papers_processed=1`, `papers_skipped=9`,
`summaries_written=1`, `metadata_enrichment_attempted=10`,
`metadata_enriched=1`, `full_text_enrichment_attempted=2`,
`full_text_enriched=0`, `papers_with_errors=0`, `dry_run=true`.

### Parallel Paper summary DOI enrichment write run

Command pattern:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run python scripts/run_paper_summary_zh_backfill.py \
  --worker-count 4 \
  --worker-index <0..3> \
  --enrich-doi-metadata \
  --llm-profile deepseekv4pro \
  --log-level WARNING \
  > /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/paper-summary-zh-backfill-enrich-doi-worker<0..3>.json
```

Result: all four workers exited `0`. Combined artifact:
`.agents/runs/professor-dataset-candidate-generation/paper-summary-zh-backfill-enrich-doi-workers-summary.json`.

| Metric | Count |
| --- | ---: |
| `papers_total` | 3183 |
| `papers_processed` | 931 |
| `papers_skipped` | 2252 |
| `summaries_written` | 875 |
| `summaries_rejected` | 56 |
| `metadata_enrichment_attempted` | 3175 |
| `metadata_enriched` | 1242 |
| `full_text_enrichment_attempted` | 867 |
| `full_text_enriched` | 289 |
| `abstract_clean_backfilled_from_full_text` | 134 |
| `identifier_contradictions` | 0 |
| `pipeline_issues_inserted` | 0 |
| `papers_with_errors` | 0 |

External provider and publisher fetch noise included PDF `403/404/405/5xx`,
unsupported content type, oversized PDF, and OpenAlex `404` for dirty DOI
strings. These were row-level skip/error paths; no script-level row errors or
identifier contradictions were recorded.

The final implementation casts `hashtext(p.paper_id)` to `bigint` before
`abs(...)` in the worker-shard SQL expression so the rare int32 minimum-value
overflow case cannot break a parallel batch.

### Duplicate Paper merge write loop

Artifact:

```text
.agents/runs/professor-dataset-candidate-generation/duplicate-merge-write-loop-summary.jsonl
```

Result: the evidence-gated write loop kept reloading matching dry-run evidence
and writing only auto-write duplicate merge candidates until no auto-write rows
remained.

| Metric | Count |
| --- | ---: |
| Write records | 38 |
| Attempted writes | 7533 |
| Written merge aliases | 3998 |
| Failed writes | 0 |
| Last unresolved count | 295 |
| Stop reason | `no_ready_candidates` |
| Final ready auto-write candidates | 0 |

Individual write commands returned nonzero while dataset blockers remained, so
their post-write status is recorded as `failed` for completion gating. The
actual write failure count was `0`; the loop stopped only when remaining rows
were review-only or ambiguous.

### Final all-lane write-ready pass

Artifact:

```text
.agents/runs/professor-dataset-candidate-generation/final-all-lanes-write-ready-summary.json
```

Result: write mode consumed matching candidate dry-run evidence and wrote only
auto-write rows.

| Lane | Input | Attempted | Written | Skipped | Failed | Unresolved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `profile_summary_repair` | 11 | 2 | 2 | 9 | 0 | 9 |
| `research_overview_backfill` | 22 | 22 | 1 | 0 | 0 | 21 |
| `professor_paper_summary_generation` | 267 | 1 | 0 | 266 | 0 | 267 |
| `duplicate_paper_merge` | 295 | 0 | 0 | 295 | 0 | 295 |

Post-write verification recorded `status=success`, `completion_allowed=true`,
`changed_professors=3`, and no post-write issues. Review-only candidate
evidence remained unresolved instead of being written.

### Professor paper-summary candidate generation after Paper enrichment

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run python scripts/run_professor_dataset_quality_closure.py \
  --mode candidate-dry-run \
  --lane professor_paper_summary_generation \
  --bucket-limit 100000 \
  --candidate-output /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/professor-paper-summary-candidate-after-paper-enrichment.json \
  --llm-profile deepseekv4pro \
  --candidate-concurrency 4 \
  --provider-max-concurrency 2 \
  --provider-min-interval-seconds 0.2
```

Result: passed. Compact summary:

| Metric | Count |
| --- | ---: |
| Input rows | 267 |
| Candidates | 136 |
| Ready auto-write | 1 |
| Review before write | 135 |
| Skipped | 131 |
| Provider failures | 0 |
| Validation failures | 0 |
| `missing_source_page_provenance` quality flags | 135 |
| `duplicate_verified_paper_links` rejections | 131 |

### Professor paper-summary write after Paper enrichment

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
uv run python scripts/run_professor_dataset_quality_closure.py \
  --mode write \
  --lane professor_paper_summary_generation \
  --bucket-limit 100000 \
  --dry-run-evidence /home/longxiang/MiroThinker/.agents/runs/professor-dataset-candidate-generation/professor-paper-summary-candidate-after-paper-enrichment.json \
  --batch-size 10
```

Result: passed after regenerating matching dry-run evidence with the same
`bucket_limit`. Output artifact:
`.agents/runs/professor-dataset-candidate-generation/professor-paper-summary-write-after-paper-enrichment.json`.

Summary: `attempted_count=1`, `written_count=1`, `skipped_count=266`,
`failed_count=0`, `unresolved_issue_count=266`, changed Professor
`PROF-6C84F94A62A9`. Post-write verification recorded `status=success`,
`completion_allowed=true`, and no issues.

### Final closure audit after Paper enrichment

Artifact:

```text
.agents/runs/professor-dataset-candidate-generation/professor-dataset-closure-after-paper-enrichment-summary.json
```

Result: read-only closure summary after the Paper enrichment and Professor
paper-summary write:

| Lane | Dataset input | Eligible | Skipped | Proposed writes | Main remaining reason |
| --- | ---: | ---: | ---: | ---: | --- |
| `profile_summary_repair` | 9 | 9 | 0 | 9 | review-only length/source-quality gate |
| `research_overview_backfill` | 21 | 21 | 0 | 21 | source extraction still review/writer gated |
| `professor_paper_summary_generation` | 266 | 135 | 131 | 135 | `duplicate_verified_paper_links` and missing provenance |
| `duplicate_paper_merge` | 5191 | 239 of sampled 300 | 61 | 239 | `ambiguous_fuzzy_match` and review-only provenance |

### Current read-only database aggregate

Command:

```bash
cd apps/miroflow-agent
uv run python - <<'PY'
# read-only aggregate SQL against miroflow_real
PY
```

Result: passed. Current aggregate after the write batches:

| Metric | Count |
| --- | ---: |
| Total Paper rows | 49814 |
| Non-merged/rejected Paper rows | 47967 |
| Confirmed Paper rows | 11112 |
| Active Papers with `summary_zh` | 11350 |
| Active Papers missing `summary_zh` | 36617 |
| Active Papers missing `abstract_clean` | 36741 |
| Active Papers missing DOI | 34469 |
| Active DOI rows still missing `summary_zh` | 2318 |
| Verified Professor-Paper links | 49482 |
| Distinct verified active Papers | 47851 |
| Professor rows | 3387 |
| Resolved Professors missing `profile_summary` | 0 |
| Resolved Professors with short `profile_summary` | 1325 |
| Resolved Professors missing `paper_summary` | 1449 |

### Final targeted regression suite

Command:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/data_agents/professor/test_dataset_quality_closure.py \
  tests/data_agents/professor/test_core_profile_paper_quality_audit.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/data_agents/paper/test_abstract_translator.py \
  tests/data_agents/paper/test_abstract_translator_boilerplate_judge.py \
  tests/data_agents/paper/test_title_quality.py \
  tests/scripts/test_run_paper_title_enrichment_backfill.py \
  -q
```

Result: passed, `457 passed in 10.13s`.

### Final Ruff

Command:

```bash
cd apps/miroflow-agent
uv run ruff check \
  src/data_agents/professor/candidate_llm_provider.py \
  src/data_agents/professor/dataset_candidate_generation.py \
  src/data_agents/professor/dataset_quality_closure.py \
  src/data_agents/professor/core_profile_paper_quality_audit.py \
  scripts/run_professor_dataset_quality_closure.py \
  scripts/run_paper_summary_zh_backfill.py \
  src/data_agents/paper/title_quality.py \
  tests/data_agents/professor/test_candidate_llm_provider.py \
  tests/data_agents/professor/test_dataset_candidate_generation.py \
  tests/data_agents/professor/test_dataset_quality_closure.py \
  tests/data_agents/professor/test_core_profile_paper_quality_audit.py \
  tests/scripts/test_run_professor_dataset_quality_closure.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/data_agents/paper/test_title_quality.py \
  tests/scripts/test_run_paper_title_enrichment_backfill.py
```

Result: passed, `All checks passed!`.

### Final OpenSpec validation

Command:

```bash
openspec validate "professor-dataset-candidate-generation" --strict
```

Result: passed, `Change 'professor-dataset-candidate-generation' is valid`.

## Final skipped checks and residual risk

- No broad bad-title cleanup apply was executed. The title guard improved, but
  the cleanup sample still includes plausible real titles, so broad deletion or
  rejection would be unsafe without a stronger resolver-backed replacement
  policy.
- No review-only candidate evidence was written. Remaining Professor profile,
  research overview, paper-summary, and duplicate-merge rows need stronger
  provenance, manual review, or new source acquisition before they should be
  persisted.
- No full-dataset Professor LLM candidate regeneration was rerun after the
  Paper DOI enrichment pass. The latest write consumed matching dry-run
  evidence for the single auto-write Professor paper-summary candidate only.
- Browser/frontend checks were not run because this slice changed data
  cleaning and backend pipeline behavior, not detail-route rendering. The
  post-write verification callbacks sampled changed Professor ids where write
  batches executed.

## 2026-06-15 Cache-Only Paper Source-Gap Remediation

### Cache-hit Paper id generation

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python - <<'PY'
# read current prof_page_only missing-summary rows, compute the same normalized
# title SHA1 used by title_resolver, and write a scoped paper-id file
PY
```

Artifacts:

```text
.agents/runs/professor-dataset-candidate-generation/paper-title-cache-hit-missing-summary-20260615-paper-ids.txt
.agents/runs/professor-dataset-candidate-generation/paper-title-cache-hit-missing-summary-20260615-summary.json
```

Result: passed. The generator found `6,726` source-backed fresh cache hits from
`33,825` missing-summary `prof_page_only` rows. Cache source distribution:
OpenAlex `5,642`, Crossref `1,042`, DBLP `40`, arXiv `1`, Semantic Scholar
`1`.

### Cache-only title enrichment dry-run

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/run_paper_title_enrichment_backfill.py \
  --paper-id-file ../../.agents/runs/professor-dataset-candidate-generation/paper-title-cache-hit-missing-summary-20260615-paper-ids.txt \
  --cache-only --dry-run --log-level WARNING \
  > ../../.agents/runs/professor-dataset-candidate-generation/paper-title-cache-only-dry-run-20260615-summary.json
```

Result: passed. Dry-run selected `6,725` rows, processed `6,725`, resolved
`6,008`, left `717` unresolved, recorded `0` row errors, and wrote `0` Paper
rows, link migrations, merge aliases, old-link rejections, or full-text rows.

### Cache-only title enrichment write

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/run_paper_title_enrichment_backfill.py \
  --paper-id-file ../../.agents/runs/professor-dataset-candidate-generation/paper-title-cache-hit-missing-summary-20260615-paper-ids.txt \
  --cache-only --log-level WARNING \
  > ../../.agents/runs/professor-dataset-candidate-generation/paper-title-cache-only-write-20260615-summary.json
```

Result: partial then repaired. The main write selected `6,725` rows, resolved
`6,008`, wrote `6,008` Paper upserts, migrated `6,037` verified links, wrote
`6,007` merge aliases, rejected `6,037` old links, marked `6,007` page-only
Paper rows as merged, wrote `39` full-text PDF metadata rows, and had one row
error: `paper_full_text.source` exceeded `varchar(32)` for
`title_resolution:semantic_scholar`.

Follow-up fix: added regression coverage and shortened full-text source labels
to `title_res:<source>`. Retry command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/run_paper_title_enrichment_backfill.py \
  --paper-id PAPER-87697D4895B3 --cache-only --log-level WARNING \
  > ../../.agents/runs/professor-dataset-candidate-generation/paper-title-cache-only-write-retry-20260615-summary.json
```

Result: passed. The retry resolved `1`, wrote `1` Paper upsert, migrated `1`
link, wrote `1` merge alias, marked `1` page-only Paper row as merged, wrote
`1` full-text PDF metadata row, and recorded `0` row errors.

### Parallel Paper summary backfill after cache-title remediation

Commands:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python scripts/run_paper_summary_zh_backfill.py \
  --worker-count 4 --worker-index <0..3> --enrich-doi-metadata \
  --llm-profile deepseekv4pro --log-level WARNING \
  > ../../.agents/runs/professor-dataset-candidate-generation/paper-summary-after-cache-title-20260615-worker<0..3>-summary.json
```

Combined artifact:

```text
.agents/runs/professor-dataset-candidate-generation/paper-summary-after-cache-title-20260615-workers-summary.json
```

Result: passed. Four workers selected `2,295` rows, processed `42`, skipped
`2,253`, wrote `21` summaries, rejected `21`, attempted `2,274` metadata
enrichments, enriched `7` metadata rows, attempted `578` full-text fetches,
enriched `0` full-text rows, backfilled `0` abstracts from full text, recorded
`0` identifier contradictions, `0` pipeline issues, and `0` script-level row
errors. The long-tail blockers were external source failures such as
`pdf_content_type_disallowed`, `http_403`, `http_404`, `http_405`, `http_5xx`,
timeouts, network failures, oversize PDFs, and polluted DOI strings.

### Post-run current aggregate

Command:

```bash
cd apps/miroflow-agent
DATABASE_URL='postgresql://miroflow:miroflow@localhost:15432/miroflow_real' \
  uv run python - <<'PY'
# read-only aggregate SQL plus residual bucket queries
PY
```

Artifact:

```text
.agents/runs/professor-dataset-candidate-generation/paper-gap-after-cache-title-summary-backfill-20260615-summary.json
```

Result: passed.

| Metric | Count |
| --- | ---: |
| Active Paper rows | 41876 |
| Active Papers with `summary_zh` | 11372 |
| Active Papers missing `summary_zh` | 30504 |
| Active Papers with `abstract_clean` | 11159 |
| Active Papers missing `abstract_clean` | 30717 |
| Active DOI rows missing `summary_zh` | 2231 |
| Current summary-backfill selectable rows without DOI enrichment | 45 |
| Current summary-backfill selectable rows with DOI enrichment | 2274 |

Residual by canonical source:

| Source | Missing summary | Missing abstract | DOI missing summary |
| --- | ---: | ---: | ---: |
| `prof_page_only` | 27925 | 27961 | 18 |
| `openalex` | 1840 | 1990 | 1799 |
| `crossref` | 409 | 435 | 409 |
| `manual` | 287 | 287 | 1 |
| `dblp` | 41 | 42 | 4 |
| `semantic_scholar` | 2 | 2 | 0 |
| `arxiv` | 0 | 0 | 0 |

Strict DOI-pollution residual count: `4`, including combined/truncated DOI
values such as `10.1021/10.1002/poc.4450`, `10.1038/s415`,
`10.1021/acs.analchem`, and
`10.1038/s42005-018-0029-0|www.nature.com/commsphys9`.

### Regression and validation

Commands:

```bash
cd apps/miroflow-agent
uv run pytest -n0 \
  tests/scripts/test_run_paper_title_enrichment_backfill.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/data_agents/paper/test_title_quality.py \
  -q

uv run ruff check \
  scripts/run_paper_title_enrichment_backfill.py \
  tests/scripts/test_run_paper_title_enrichment_backfill.py

cd /home/longxiang/MiroThinker
openspec validate "professor-dataset-candidate-generation" --strict
```

Results:

- Targeted pytest passed, `372 passed in 8.81s`.
- Ruff passed, `All checks passed!`.
- OpenSpec strict validation passed, `Change 'professor-dataset-candidate-generation' is valid`.

### Residual risk

- The largest remaining gap is no longer safe cache-only migration. It is
  unresolved source acquisition: `27,925` active `prof_page_only` rows still
  miss summaries and `27,961` miss abstracts.
- DOI-backed residual rows are mostly blocked by provider/full-text failures or
  missing abstracts in upstream metadata. Only `45` rows are currently directly
  selectable without DOI enrichment.
- The observed DOI pollution class needs a separate DOI normalization and
  re-resolution slice before those rows can be safely summarized.

## Live Resolver Provider Preflight

### RED provider/contact tests

Command:

```bash
uv run pytest -n0 \
  apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py::test_crossref_title_search_uses_configured_contact \
  apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py::test_resolve_can_defer_semantic_scholar_title_search_until_api_key_available \
  apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_forwards_semantic_scholar_disable_flag_to_title_resolver \
  apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_empty_report_records_semantic_scholar_title_search_switch \
  apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_cli_help_lists_safe_scoping_flags \
  apps/miroflow-agent/tests/data_agents/paper/test_crossref.py::test_request_json_uses_configured_crossref_contact \
  apps/miroflow-agent/tests/data_agents/paper/test_semantic_scholar.py::test_request_json_uses_configured_semantic_scholar_api_key
```

Result before implementation: expected RED, `7 failed`. Failures showed
Crossref still used the placeholder mailto, the resolver and CLI lacked
Semantic Scholar title-search disable wiring, and Crossref/Semantic Scholar
request helpers did not send the expected headers.

### GREEN provider/contact regression

Command:

```bash
uv run pytest -n0 \
  apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py \
  apps/miroflow-agent/tests/data_agents/paper/test_crossref.py \
  apps/miroflow-agent/tests/data_agents/paper/test_semantic_scholar.py \
  apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py
```

Result: passed, `125 passed in 49.65s`.

Command:

```bash
uv run ruff check \
  apps/miroflow-agent/src/data_agents/providers/crossref.py \
  apps/miroflow-agent/src/data_agents/providers/semantic_scholar.py \
  apps/miroflow-agent/src/data_agents/paper/title_resolver.py \
  apps/miroflow-agent/src/data_agents/paper/crossref.py \
  apps/miroflow-agent/src/data_agents/paper/semantic_scholar.py \
  apps/miroflow-agent/scripts/run_paper_title_enrichment_backfill.py \
  apps/miroflow-agent/tests/data_agents/paper/test_title_resolver.py \
  apps/miroflow-agent/tests/data_agents/paper/test_crossref.py \
  apps/miroflow-agent/tests/data_agents/paper/test_semantic_scholar.py \
  apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py
```

Result: passed, `All checks passed!`.

### Scope note

No live resolver shard or Paper summary rerun was executed in this preflight
slice. Remaining live source-acquisition tasks 15.1-15.5 stay open.

### OpenSpec validation

Command:

```bash
openspec validate "professor-dataset-candidate-generation" --strict
```

Result: passed, `Change 'professor-dataset-candidate-generation' is valid`.

## DOI Pollution Admission Gate

### RED bad-DOI tests

Command:

```bash
uv run pytest -n0 \
  apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py::test_polluted_doi_does_not_call_doi_lookup_providers \
  apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py::test_cli_skips_doi_enrichment_for_polluted_doi_only_row
```

Result before implementation: expected RED, `2 failed`. Failures showed that
`10.1021/10.1002/poc.4450` was sent to DOI lookup providers and the summary
backfill called enrichment instead of reporting a bad DOI bucket.

### GREEN bad-DOI regression

Command:

```bash
uv run pytest -n0 \
  apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py \
  apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py
```

Result: passed, `65 passed in 10.71s`.

Command:

```bash
uv run ruff check \
  apps/miroflow-agent/src/data_agents/paper/doi_quality.py \
  apps/miroflow-agent/src/data_agents/paper/enrichment.py \
  apps/miroflow-agent/scripts/run_paper_summary_zh_backfill.py \
  apps/miroflow-agent/tests/data_agents/paper/test_enrichment.py \
  apps/miroflow-agent/tests/scripts/test_run_paper_summary_zh_backfill.py
```

Result: passed, `All checks passed!`.

### Scope note

No live database mutation was executed for this admission-gate slice. The next
live summary/resolver backfill should now report bad DOI-only rows as
`metadata_enrichment_skipped_bad_doi` instead of provider attempts.

## Title Enrichment DOI Shortcut Gate

### RED title-enrichment shortcut regression

Command:

```bash
uv run pytest -n0 \
  apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_does_not_trust_polluted_existing_doi_identifier
```

Result before implementation: expected RED. The test failed because a polluted
existing DOI was trusted by `_resolved_from_existing_identifier`, so
`resolve_title` was not called and no bad DOI report evidence existed.

### GREEN title-enrichment shortcut regression

Command:

```bash
uv run pytest -n0 \
  apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py::test_process_rows_does_not_trust_polluted_existing_doi_identifier
```

Result: passed, `1 passed in 9.16s`.

Command:

```bash
uv run pytest -n0 \
  apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py
```

Result: passed, `32 passed in 9.66s`.

Command:

```bash
uv run ruff check \
  apps/miroflow-agent/scripts/run_paper_title_enrichment_backfill.py \
  apps/miroflow-agent/tests/scripts/test_run_paper_title_enrichment_backfill.py
```

Result: passed, `All checks passed!`.

Command:

```bash
openspec validate "professor-dataset-candidate-generation" --strict
```

Result: passed, `Change 'professor-dataset-candidate-generation' is valid`.

### Scope note

No live database mutation was executed for this shortcut-gate slice. The next
live title resolver backfill should now report `bad_doi_identifiers` and
bounded `bad_doi_samples` for polluted existing DOI values instead of promoting
them directly as trusted `doi_lookup` resolutions.

## Live Paper Title Resolver Source Acquisition

### Remaining source-gap shard generation

Artifacts:

- `.agents/runs/professor-dataset-candidate-generation/paper-live-title-resolver-remaining-prof-page-only-no-arxiv-dblp-20260615-summary.json`
- `.agents/runs/professor-dataset-candidate-generation/paper-live-title-resolver-remaining-prof-page-only-no-arxiv-dblp-20260615-shard0.txt`
- `.agents/runs/professor-dataset-candidate-generation/paper-live-title-resolver-remaining-prof-page-only-no-arxiv-dblp-20260615-shard1.txt`
- `.agents/runs/professor-dataset-candidate-generation/paper-live-title-resolver-remaining-prof-page-only-no-arxiv-dblp-20260615-shard2.txt`
- `.agents/runs/professor-dataset-candidate-generation/paper-live-title-resolver-remaining-prof-page-only-no-arxiv-dblp-20260615-shard3.txt`

Result: generated four remaining `prof_page_only` missing-summary shards after
cache-only remediation. The shard summary recorded `27,643` scoped rows:
`6,896`, `6,993`, `6,908`, and `6,846`. The next run disabled arXiv and DBLP
to keep OpenAlex/Crossref-primary source acquisition focused.

### Live resolver write run

Artifact:

- `.agents/runs/professor-dataset-candidate-generation/paper-live-title-resolver-no-arxiv-dblp-write-20260615-workers-summary.json`

Result: four parallel live resolver write shards processed `27,507` scoped
rows, resolved `16,114`, left `11,393` unresolved, wrote `16,114` Paper
upserts, migrated `16,310` verified Professor-Paper links, wrote `16,098`
merge aliases, marked `16,098` page-only rows merged, and recorded `0`
script-level row errors. Resolver enablement was OpenAlex, Crossref, and
Semantic Scholar; arXiv and DBLP were disabled for this slice.

### Post-resolver pre-summary audit

Artifact:

- `.agents/runs/professor-dataset-candidate-generation/paper-gap-after-live-title-resolver-before-summary-backfill-20260615-summary.json`

Result: after live resolver source acquisition and before the final summary
rerun, the current active Paper aggregate was `40,401` active rows, `11,371`
with `summary_zh`, `29,030` missing `summary_zh`, `18,357` with
`abstract_clean`, and `22,044` missing `abstract_clean`. Source buckets showed
`11,619` remaining `prof_page_only` missing summaries.

### Mixed DOI/full-text summary rerun and partial stop

Artifact:

- `.agents/runs/professor-dataset-candidate-generation/paper-summary-mixed-interrupted-after-live-title-20260615-workers-summary.json`

Result: existing mixed DOI/full-text workers and a follow-up rerun together
wrote `5,261` summaries, skipped `3,135` rows with no abstract, rejected `99`
boilerplate summaries, and rejected `67` other invalid summaries. These workers
were terminated and closed as `partial` because PDF/full-text acquisition was
the dominant bottleneck and made the summary lane slow and unstable.

### Existing-abstract fast-path summary rerun

Artifact:

- `.agents/runs/professor-dataset-candidate-generation/paper-summary-existing-abstract-after-live-title-20260615-workers-summary.json`

Result: eight DeepSeek workers ran without DOI/PDF enrichment against rows that
already had `abstract_clean`, `paper_full_text.abstract`, or
`paper_full_text.intro`. The run selected `5,184` rows, processed `5,133`,
skipped `51`, wrote `4,937` summaries, rejected `196`, and recorded `0`
script-level row errors. All worker `run_paper_summary_zh_backfill.py`
processes were stopped or completed before the final audit.

### Final aggregate audit

Artifact:

- `.agents/runs/professor-dataset-candidate-generation/paper-gap-after-live-title-existing-abstract-summary-20260615-final-summary.json`

Result: final stable aggregate after live resolver source acquisition and
existing-abstract summary backfill:

- active Papers: `40,401`
- active Papers with `summary_zh`: `20,601`
- active Papers missing `summary_zh`: `19,800`
- active Papers with `abstract_clean`: `20,517`
- active Papers missing `abstract_clean`: `19,884`
- active DOI rows still missing summary: `7,782`
- active `prof_page_only` rows still missing summary: `11,619`
- active rows with existing abstract/full-text input but missing summary: `262`

Residual source buckets:

| Source | Active rows | Missing summary | Missing abstract |
| --- | ---: | ---: | ---: |
| `prof_page_only` | 11,861 | 11,619 | 11,658 |
| `crossref` | 10,725 | 4,592 | 4,605 |
| `openalex` | 17,420 | 3,259 | 3,290 |
| `manual` | 306 | 287 | 287 |
| `dblp` | 83 | 41 | 42 |
| `semantic_scholar` | 4 | 2 | 2 |
| `arxiv` | 2 | 0 | 0 |

### Residual risk

- The remaining `19,800` active Papers missing Chinese summaries are dominated
  by rows without usable abstracts. Direct LLM fabrication is not safe for
  those rows.
- The largest remaining source bucket is `prof_page_only`: `11,619` missing
  summaries and `11,658` missing abstracts. These rows require homepage parser
  cleanup, stronger title/source resolver batches, or manual review.
- The mixed DOI/full-text path is too slow as a single summary lane. Future
  work should split source acquisition from summary generation explicitly:
  translate existing abstracts first, then run DOI/PDF/full-text enrichment as
  a slower source-acquisition lane.

## Follow-up Paper Summary Slow Source Acquisition

### Fast existing-abstract residual rerun

Artifact:

- `.agents/runs/professor-dataset-candidate-generation/paper-summary-fast-existing-abstract-20260615-workers-summary.json`

Result: four DeepSeek workers reprocessed the residual existing-abstract fast
lane without DOI/PDF/full-text enrichment. The run selected `262` rows,
processed `211`, skipped `51`, wrote `83` additional summaries, rejected
`128`, and recorded `0` script-level row errors. Remaining rows in this lane
are quality rejections or skips, not missing provider execution.

### One-pass identifier/no-abstract slow source batches

Artifacts:

- `.agents/runs/professor-dataset-candidate-generation/paper-summary-slow-enrich-20260615-batch1-manifest.json`
- `.agents/runs/professor-dataset-candidate-generation/paper-summary-slow-enrich-20260615-batch1-workers-summary.json`
- `.agents/runs/professor-dataset-candidate-generation/paper-summary-slow-enrich-20260615-batch2-manifest.json`
- `.agents/runs/professor-dataset-candidate-generation/paper-summary-slow-enrich-20260615-batch2-workers-summary.json`
- `.agents/runs/professor-dataset-candidate-generation/paper-summary-slow-enrich-20260615-batch3-manifest.json`
- `.agents/runs/professor-dataset-candidate-generation/paper-summary-slow-enrich-20260615-batch3-workers-summary.json`
- `.agents/runs/professor-dataset-candidate-generation/paper-summary-slow-enrich-processed-ids-20260615.txt`

Result: the three slow batches selected `1,600`, `3,200`, and `2,794`
identifier-backed active Papers with missing summary and no usable
`abstract_for_summary`. The processed-history file contains `7,594` ids, which
matches the three manifests, so this slow lane was covered once instead of
hammering the same provider failures repeatedly.

Combined slow-lane totals:

- selected rows: `7,594`
- processed rows: `3,022`
- skipped rows: `4,572`
- summaries written: `2,929`
- summaries rejected: `93`
- metadata enrichment attempted: `7,503`
- bad DOI metadata lookups skipped: `92`
- metadata records enriched: `4,244`
- full-text enrichment attempted: `1,382`
- full-text records enriched: `354`
- abstracts backfilled from full text: `152`
- identifier contradictions: `0`
- pipeline issues inserted: `0`
- script-level row errors: `0`

### Latest final aggregate audit

Artifact:

- `.agents/runs/professor-dataset-candidate-generation/paper-gap-after-live-title-summary-backfill-20260615-summary.json`

Result: latest active Paper aggregate after live title resolver source
acquisition, existing-abstract fast processing, and one-pass identifier
slow-source cleanup:

- active Papers: `40,401`
- active Papers with `summary_zh`: `23,613`
- active Papers missing `summary_zh`: `16,788`
- active Papers with `abstract_clean`: `23,884`
- active Papers missing `abstract_clean`: `16,517`
- active DOI rows still missing summary: `4,772`

Residual classes:

- `prof_page_only_without_identifier_or_abstract`: `11,619`
- `identifier_but_no_abstract_after_one_attempt`: `4,572`
- `existing_abstract_but_summary_rejected_or_skipped`: `272`
- `other_missing_summary`: `325`

Residual source buckets:

| Source | Active rows | Missing summary | Missing abstract |
| --- | ---: | ---: | ---: |
| `prof_page_only` | 11,861 | 11,619 | 11,619 |
| `openalex` | 17,420 | 2,781 | 2,636 |
| `crossref` | 10,725 | 2,059 | 1,933 |
| `manual` | 306 | 287 | 287 |
| `dblp` | 83 | 40 | 40 |
| `semantic_scholar` | 4 | 2 | 2 |
| `arxiv` | 2 | 0 | 0 |

### Residual risk

- The remaining `prof_page_only` rows lack usable identifiers or abstracts in
  the current active canonical Paper rows. They require homepage parser/source
  acquisition work, not direct LLM summary fabrication.
- The remaining identifier-backed slow-lane rows were attempted once through
  metadata/full-text enrichment and still lacked usable abstract source. The
  next improvement should add stronger resolver/source providers or targeted
  PDF acquisition, with retry tracking to avoid repeated provider pressure.
- The remaining existing-abstract fast-lane rows need prompt/validator review
  or manual adjudication because the provider returned rejected/skipped summary
  output for the available source text.

### Verification after latest follow-up cleanup evidence

Command:

```bash
uv run pytest -n0 \
  tests/scripts/test_run_paper_title_enrichment_backfill.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/data_agents/paper/test_title_quality.py \
  tests/data_agents/paper/test_enrichment.py \
  tests/data_agents/paper/test_title_resolver.py \
  tests/data_agents/paper/test_crossref.py \
  tests/data_agents/paper/test_semantic_scholar.py \
  -q
```

Result: passed, `491 passed in 63.38s`.

Command:

```bash
uv run ruff check \
  scripts/run_paper_title_enrichment_backfill.py \
  scripts/run_paper_summary_zh_backfill.py \
  src/data_agents/paper/doi_quality.py \
  src/data_agents/paper/enrichment.py \
  src/data_agents/paper/title_quality.py \
  src/data_agents/paper/title_resolver.py \
  src/data_agents/paper/crossref.py \
  src/data_agents/paper/semantic_scholar.py \
  src/data_agents/providers/crossref.py \
  src/data_agents/providers/semantic_scholar.py \
  tests/scripts/test_run_paper_title_enrichment_backfill.py \
  tests/scripts/test_run_paper_summary_zh_backfill.py \
  tests/data_agents/paper/test_title_quality.py \
  tests/data_agents/paper/test_enrichment.py \
  tests/data_agents/paper/test_title_resolver.py \
  tests/data_agents/paper/test_crossref.py \
  tests/data_agents/paper/test_semantic_scholar.py
```

Result: passed, `All checks passed!`.

Command:

```bash
openspec validate "professor-dataset-candidate-generation" --strict
```

Result: passed, `Change 'professor-dataset-candidate-generation' is valid`.
