# Company LLM Concurrency and Timeout Hardening

## Scope

This slice hardens the Company upload enrichment runtime before the 1024-company
dry-run. It addresses the post-cleanup long-tail narrative refresh, where 44
company summaries committed but the child process kept waiting on remaining LLM
work.

## Changes

- Upload runner child defaults:
  - `child_llm_concurrency`: 4
  - `child_web_concurrency`: 3
- Upload runner now accepts and propagates:
  - `--child-llm-timeout-seconds`
  - `--child-llm-retry-budget`
- LLM child scripts now accept:
  - `--llm-timeout-seconds`
  - `--llm-retry-budget`
- OpenAI SDK clients now receive explicit `max_retries` from Company task
  routing.
- Signal extraction now runs LLM extraction with per-news-row worker
  concurrency, then serializes DB writes.

## Touched Runtime Paths

- `run_company_xlsx_team_synthesis.py`
- `run_company_generic_source_judgment.py`
- `run_company_source_product_extract.py`
- `run_company_signal_extract.py`
- `run_company_news_ingest.py`
- `run_company_upload_enrichment_batch.py`

## Verification

- RED subset failed before implementation for missing timeout/retry flags,
  missing runner propagation, missing `max_retries`, and missing signal worker
  concurrency.
- GREEN subset passed after implementation: 9 tests.
- Signal concurrency RED/GREEN passed: 1 test.
- Focused script suite passed: 117 tests.
- Python compilation passed for touched scripts.
- `openspec validate company-scaleout-enrichment-hardening --strict` passed.

## 1024 Dry-Run Recommendation

Use company-level subchunks and keep provider caps explicit:

```bash
uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py \
  --batch-id <batch-id> \
  --dry-run --skip-persistence --skip-milvus \
  --chunk-size 25 \
  --stage-concurrency 4 \
  --llm-stage-concurrency 4 \
  --web-stage-concurrency 4 \
  --stage-subchunk-size 1 \
  --stage-timeout-seconds 1800 \
  --stage-retry-budget 1 \
  --retry-backoff-seconds 1 \
  --sleep-seconds 0.05 \
  --official-product-max-pages 3 \
  --source-product-limit 4000 \
  --child-llm-concurrency 4 \
  --child-web-concurrency 3 \
  --child-llm-timeout-seconds 75 \
  --child-llm-retry-budget 1 \
  --provider-llm-max-concurrency 8 \
  --provider-serper-max-concurrency 4
```
