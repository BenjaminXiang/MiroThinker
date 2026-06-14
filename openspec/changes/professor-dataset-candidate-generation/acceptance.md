# Acceptance Evidence

Status: implementation evidence recorded.

This file records acceptance evidence for Professor dataset candidate
generation. Evidence MUST be filled only after real commands, tests, dry-run
artifacts, or documented skipped-check rationale exist.

## Acceptance Targets

| Target | Expected Evidence | Status |
| --- | --- | --- |
| Candidate report shape | Typed dry-run report includes lane counts, candidates, skipped rows, validation failures, provider failures, affected ids, samples, selection hash, candidate status, quality flags, source confidence, write recommendation, and LLM self-check evidence. | Verified by `test_dataset_candidate_generation.py` and relaxed candidate dry-run artifact. |
| Profile summaries | Chinese `candidate_profile_summary` values target 200-300 characters and remain reviewable candidates when usable but short. | Verified by unit tests; real relaxed dry-run produced 5 bounded deterministic candidates. |
| Research overviews | Chinese overview extraction and English-to-Chinese translation preserve source traceability; weak hashes become review flags on usable Chinese content. | Verified by unit tests; real relaxed dry-run produced 5 Chinese official extracts. |
| Professor paper summaries | `candidate_paper_summary` values use verified Professor-seeded Paper links only; unresolved duplicates downgrade to `needs_review` instead of blocking candidate reporting. | Verified by unit tests; real relaxed dry-run produced 3 candidates and skipped 2 rows without usable verified paper inputs. |
| Duplicate Paper merge plans | Canonical merge candidates use DOI/arXiv or stronger author/venue/source evidence for auto-write; weak provenance or title/year-only evidence becomes `needs_review`. | Verified by unit tests; real relaxed dry-run produced 5 candidates and 0 validation failures, including 3 review-before-write candidates for missing source provenance. |
| Provider failure visibility | LLM/provider failures appear in dry-run evidence and do not promote or write rows. | Verified by unit tests with injectable fake providers and the earlier real bounded `MissingLLMCredentials` artifact. |
| Real LLM provider default | `candidate-dry-run` defaults to real OpenAI-compatible Professor candidate providers; deterministic mode requires explicit selection. | Verified by provider/CLI tests and bounded real-provider dry-run artifacts for profile synthesis, research translation, and paper summary synthesis. |
| Local LLM credentials | The candidate dry-run CLI loads app-local `.env` before resolving Professor LLM credentials. | Verified by `test_cli_import_loads_app_env`; `DEEPSEEK_API_KEY` is documented in `.env.example` and `.deepseek_api_key` is ignored as a local fallback. |
| Boundary preservation | Provider-only author-name paper discovery and hidden company/startup roles remain outside Professor core candidate generation. | Verified by unit tests. |
| Real dry-run handoff | Bounded `miroflow_real` dry-run evidence exists for all four lanes and is consumable by existing write mode. | Verified by script handoff test, `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-baseline-bucket5.json`, and `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-relaxed-bucket5.json`. |

## Required Verification Commands

Commands will be recorded during implementation in
`.agents/runs/professor-dataset-candidate-generation/verification.md`.

Minimum expected command classes:

- Targeted candidate model and validation tests.
- Targeted CLI/script tests.
- Real `miroflow_real` bounded dry-run for each lane.
- Existing dataset-quality closure write-gate compatibility check using the
  generated dry-run evidence.
- Regression checks for Professor/Paper detail routes and frontend paper links
  if candidate writes are executed in a later slice.
- OpenSpec validation.

## Relaxed Gate Evidence

| Command / Artifact | Evidence |
| --- | --- |
| `uv run pytest -n0 tests/data_agents/professor/test_dataset_candidate_generation.py tests/data_agents/professor/test_dataset_quality_closure.py tests/scripts/test_run_professor_dataset_quality_closure.py` | Passed, `42 passed in 5.63s`. |
| `uv run pytest -n0 tests/data_agents/professor/test_candidate_llm_provider.py tests/data_agents/professor/test_dataset_candidate_generation.py tests/data_agents/professor/test_dataset_quality_closure.py tests/scripts/test_run_professor_dataset_quality_closure.py` | Passed, `49 passed in 5.73s`. |
| `uv run pytest -n0 tests/data_agents/professor/test_candidate_llm_provider.py tests/data_agents/professor/test_dataset_candidate_generation.py tests/data_agents/professor/test_dataset_quality_closure.py tests/scripts/test_run_professor_dataset_quality_closure.py` | Passed after local dotenv loading update, `50 passed in 6.31s`. |
| `uv run ruff check src/data_agents/professor/candidate_llm_provider.py src/data_agents/professor/dataset_candidate_generation.py scripts/run_professor_dataset_quality_closure.py tests/data_agents/professor/test_candidate_llm_provider.py tests/data_agents/professor/test_dataset_candidate_generation.py tests/scripts/test_run_professor_dataset_quality_closure.py` | Passed, `All checks passed!`. |
| `openspec validate "professor-dataset-candidate-generation" --strict` | Passed, change is valid. |
| `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-relaxed-bucket5.json` | Real bounded `miroflow_real` dry-run passed with lane counts: profile `5/5`, research `5/5`, paper summary `3/5`, duplicate merge `5/5`; validation failures `0` for all lanes. |
| `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-profile-bucket1.json` | Default real-provider dry-run reached provider mode and recorded `MissingLLMCredentials` as a provider failure with profile/model metadata; it did not fall back to deterministic synthesis. |
| `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-profile-bucket1-dotenv.json` | Real-provider profile summary synthesis succeeded with `candidate_count=1`, `provider_failure_count=0`, self-check evidence, provider metadata, prompt hash, and response hash. |
| `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-research-bucket12-translation-dotenv.json` | Real-provider English research overview translation succeeded with `candidate_count=12`, `provider_failure_count=0`, one `llm_translation` candidate carrying self-check evidence, provider metadata, prompt hash, and response hash. |
| `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-real-provider-paper-summary-bucket1-dotenv.json` | Real-provider Professor paper summary synthesis succeeded with `candidate_count=1`, `provider_failure_count=0`, self-check evidence, provider metadata, prompt hash, and response hash. |
| `.agents/runs/professor-dataset-candidate-generation/candidate-dry-run-duplicate-merge-bucket1-dotenv.json` | Duplicate Paper merge candidate lane remained covered with `candidate_count=1`, `provider_failure_count=0`, `candidate_status=needs_review`, and `write_recommendation=review_before_write`. |

## Skipped Checks

- No broad write-mode remediation was executed.
- Broad full-dataset real-provider generation was not executed; verification is
  intentionally bounded to small lane samples before any write-mode remediation.
- Frontend/API detail route checks were not run because this slice did not
  write remediation data.
