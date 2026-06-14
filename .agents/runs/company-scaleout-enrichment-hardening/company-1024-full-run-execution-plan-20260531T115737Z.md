# Full 1024-Company Live Rerun Execution Plan - 2026-05-31

## Preconditions

- Review and accept the full dry-run report: `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-report-20260531T115737Z.md`.
- Confirm no business fact table writes occurred in dry-run: `True`.
- Review `llm_failure_count=56` and rejected candidate samples before live writes.
- Do not run live if DeepSeek/Serper provider limits have changed or if the current database count differs from 1024 without updating the scope artifact.

## Scope

- Company scope: 1024 imported XLSX-backed canonical companies from `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-company-ids-20260531T081827Z.txt`.
- Batch used for dry-run: `84fd0f38-1430-4532-9787-098f2663a3ce`. Use a new live batch for task 9.7; do not reuse this dry-run batch for live writes.
- External sources: official sites, Yiou site search, PitchHub/36Kr site search, generic web search, DeepSeek LLM judgment/synthesis.

## Enabled Stages

- `baseline_readiness`
- `xlsx_team_synthesis`
- `official_product_capture`
- `news_iyiou`
- `news_pitchhub`
- `generic_source_judgment`
- `signal_extract`
- `source_product_extract`
- `multi_source_narrative`

## Skipped Stages In Dry-Run

- Persistence: `dry_run_or_skip_persistence`
- Milvus refresh: `skip_milvus`

For live task 9.7, persistence should be enabled and Milvus should still be skipped until task 9.8 touched-company vector refresh.

## Concurrency And Rate Limits

| Stage | Family | Effective concurrency | Timeout | Retry budget | Provider/model |
|---|---|---:|---:|---:|---|
| `baseline_readiness` | baseline | 1 | 2400.0 | 2 |  |
| `xlsx_team_synthesis` | llm | 40 | 2400.0 | 2 | deepseek-v4-lite |
| `official_product_capture` | web | 6 | 2400.0 | 2 | official_site |
| `news_iyiou` | web | 10 | 2400.0 | 2 | deepseek-v4-lite |
| `news_pitchhub` | web | 10 | 2400.0 | 2 | deepseek-v4-lite |
| `generic_source_judgment` | llm | 40 | 2400.0 | 2 | deepseek-v4-pro |
| `signal_extract` | llm | 40 | 2400.0 | 2 | deepseek-v4-pro |
| `source_product_extract` | llm | 40 | 2400.0 | 2 | deepseek-v4-pro |
| `multi_source_narrative` | llm | 40 | 2400.0 | 2 | deepseek-v4-pro |

- Child concurrency: `{"llm": 2, "web": 3}`
- Child LLM policy: `{"timeout_seconds": 90.0, "retry_budget": 2}`
- Provider rate limits: `{"deepseek_max_concurrency": 40, "serper_max_concurrency": 10, "deepseek_min_interval_seconds": 0.05, "serper_min_interval_seconds": 0.1}`

## Checkpoint And Resume Policy

- Create a new live batch with the same selected company-id artifact.
- Use per-company stage checkpoints and default skip-succeeded behavior.
- Use `--include-failed` only after a failed/partial live attempt has been inspected.
- Retain `company_enrichment_search_audit`, company-state rows, stdout JSON, stderr, and DB count snapshots as acceptance evidence.
- If interrupted, close stale running states with the existing stale cleanup helper before resume.

## Estimated Runtime

- Final fixed dry-run resume runtime: 28m 6s.
- Live runtime estimate: 35-60 minutes, because persistence writes are enabled but most expensive external/LLM stages should have similar concurrency.
- Use the dry-run provider caps first: DeepSeek 40, Serper 10, official-site 6. Reduce DeepSeek to 20 if rate-limit/connection errors appear.

## Cleanup Plan

- Before live: snapshot business fact counts for `company_news_item`, `company_signal_event`, `company_product`, `company_product_evidence`, and `company_application_scenario`.
- During live: do not manually delete rows; rely on idempotent writers and batch markers.
- After live: if source pollution appears, clean by batch/source marker plus evidence relationships, not by broad company deletes.

## Rollback Plan

- If live writes are unacceptable, rollback by the live batch/source markers and evidence links only.
- Do not delete XLSX baseline company rows.
- Do not refresh Milvus until task 9.8 after live row validation passes; this keeps vector rollback separate.

## Go / No-Go

Go only if the reviewer accepts:

- dry-run 1024/1024 success;
- no business fact writes in dry-run;
- provider limiter regression fix and tests;
- retained checkpoint/search audit evidence;
- `llm_failure_count=56` is acceptable or reviewed.
