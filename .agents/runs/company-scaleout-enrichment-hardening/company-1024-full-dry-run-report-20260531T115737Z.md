# 1024 Imported Company Full Dry-Run Report - 2026-05-31

## Result

- Batch: `84fd0f38-1430-4532-9787-098f2663a3ce`
- Status: `succeeded`; database batch status: `succeeded`
- Scope: 1024/1024 selected imported companies processed
- Mode: dry-run with `--skip-persistence --skip-milvus`
- Final fixed resume runtime: 28m 6s
- Total batch wall clock including aborted tuning resumes: 3h 38m 0s
- Stderr artifact size: 0 bytes
- Output artifact: `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-resume-llm40-fixed-20260531T112931Z.json`
- Selected company IDs: `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-company-ids-20260531T081827Z.txt`

## No-Write Guard

Business fact tables stayed unchanged. `company_enrichment_search_audit` increased because search-audit/checkpoint evidence is allowed in this dry-run.

| Table | Before | After | Delta |
|---|---:|---:|---:|
| `company_product` | 620 | 620 | 0 |
| `company_product_evidence` | 1980 | 1980 | 0 |
| `company_application_scenario` | 370 | 370 | 0 |
| `company_signal_event` | 694 | 694 | 0 |
| `company_news_item` | 973 | 973 | 0 |
| `company_enrichment_search_audit` | 5892 | 11450 | 5558 |

No business fact writes: `True`

## Stage Checkpoints

| Stage | Succeeded | Failed | Running | Partial |
|---|---:|---:|---:|---:|
| `baseline_readiness` | 1024 | 0 | 0 | 0 |
| `batch_complete` | 1024 | 0 | 0 | 0 |
| `generic_source_judgment` | 1024 | 0 | 0 | 0 |
| `multi_source_narrative` | 1024 | 0 | 0 | 0 |
| `news_iyiou` | 1024 | 0 | 0 | 0 |
| `news_pitchhub` | 1024 | 0 | 0 | 0 |
| `official_product_capture` | 1024 | 0 | 0 | 0 |
| `signal_extract` | 1024 | 0 | 0 | 0 |
| `source_product_extract` | 1024 | 0 | 0 | 0 |
| `xlsx_team_synthesis` | 1024 | 0 | 0 | 0 |

## Search Audit Evidence

| Source adapter | Audit rows | Results | Accepted |
|---|---:|---:|---:|
| `generic_web` | 3166 | 15697 | 4058 |
| `iyiou` | 1196 | 2184 | 363 |
| `pitchhub_36kr` | 1196 | 7002 | 408 |

## Runner Summary

- Stage reports succeeded: 4045
- Stage reports failed: 0
- Stage reports total: 4045
- Skipped by checkpoint: 5171
- Query count: 3012
- Fetch count: 331
- Accepted source count: 3855
- Rejected source count: 4796
- LLM failure count: 56
- Rejected product/scenario candidate count: 739
- Products with target customers found during dry-run synthesis: 17
- Narratives generated in dry-run: 1004
- Vector refresh count: 0

## Runtime Finding Fixed During 9.5

During the first 20/40-way resumes, `generic_source_judgment` remained nearly serialized. The root cause was the shared provider rate limiter holding the interval file lock for the entire API call. The limiter now releases the interval lock immediately after spacing the request start while keeping the slot lock over the API call. Regression coverage: `test_provider_rate_limiter_does_not_serialize_call_body`.

## Effective Execution Policy

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

Provider limits: `{"deepseek_max_concurrency": 40, "serper_max_concurrency": 10, "deepseek_min_interval_seconds": 0.05, "serper_min_interval_seconds": 0.1}`

## Residual Risks

- This is a full dry-run, not the live rerun.
- Business facts were intentionally not persisted, so post-run coverage uplift must be measured in task 9.9 after task 9.7 live rerun.
- `llm_failure_count=56` needs review before live rerun, although no stage failed and all 1024 companies reached `batch_complete`.
- Generic/search audit volume is high and should be retained as evidence for acceptance review.
