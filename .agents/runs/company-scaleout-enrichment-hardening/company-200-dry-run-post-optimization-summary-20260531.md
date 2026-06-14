# 200-Company Post-Optimization Dry-Run Summary

Change: `company-scaleout-enrichment-hardening`
Batch: `fb7eeffb-ca23-45bd-8116-0029f8aa32ce`
Run artifact: `.agents/runs/company-scaleout-enrichment-hardening/company-200-dry-run-post-optimization-20260530T1948Z.json`
Stderr artifact: `.agents/runs/company-scaleout-enrichment-hardening/company-200-dry-run-post-optimization-20260530T1948Z.stderr.txt`

## Command

```bash
DATABASE_URL=postgresql://miroflow:miroflow@localhost:15432/miroflow_real \
uv run --no-sync python apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py \
  --batch-id fb7eeffb-ca23-45bd-8116-0029f8aa32ce \
  --representative-sample-size 200 \
  --dry-run \
  --skip-persistence \
  --skip-milvus \
  --chunk-size 25 \
  --stage-concurrency 2 \
  --llm-stage-concurrency 2 \
  --web-stage-concurrency 2 \
  --stage-subchunk-size 10 \
  --stage-timeout-seconds 1800 \
  --stage-retry-budget 1 \
  --retry-backoff-seconds 1 \
  --sleep-seconds 0.05 \
  --official-product-max-pages 3 \
  --source-product-limit 4000 \
  --child-llm-concurrency 2 \
  --child-web-concurrency 2
```

## Result

- Status: succeeded.
- Runtime: 2026-05-30 19:47:17 UTC to 2026-05-31 00:12:45 UTC, about 4h25m.
- Selected companies processed: 200/200.
- Batch-level company result: 200 succeeded, 0 failed.
- Final company-state rows: 200 `batch_complete/succeeded`; 824 unselected imported companies remained `queued`.
- Stderr: empty.

## No-Write Dry-Run Evidence

The run used `--dry-run --skip-persistence --skip-milvus`. Business fact tables did not change:

| Table | Before | After | Delta |
|---|---:|---:|---:|
| `company_product` | 336 | 336 | 0 |
| `company_product_evidence` | 1113 | 1113 | 0 |
| `company_application_scenario` | 227 | 227 | 0 |
| `company_signal_event` | 617 | 617 | 0 |
| `company_news_item` | 461 | 461 | 0 |
| `company_enrichment_search_audit` | 3740 | 4793 | +1053 |

The audit-table delta matches `summary.query_count=1053` and is the expected dry-run trace evidence.

## Extraction And Quality Metrics

| Metric | Count |
|---|---:|
| Queries executed | 1053 |
| Pages/results fetched | 513 |
| Accepted sources | 832 |
| Rejected sources | 1095 |
| LLM failure/rejection count | 413 |
| XLSX-derived products synthesized | 59 |
| XLSX-derived scenarios synthesized | 4 |
| Source products extracted in dry-run | 122 |
| Source scenarios extracted in dry-run | 64 |
| Funding events extracted in dry-run | 2 |
| Multi-source narratives generated | 192 |
| Narrative rejections | 8 |
| Rejected product/scenario candidates | 213 |
| Vector refreshes | 0 |

Source-adapter detail:

| Source adapter | News processed | Events extracted | Products extracted | Scenarios extracted | Candidate gate rejected |
|---|---:|---:|---:|---:|---:|
| Yiou | 42 | 0 | 10 | 9 | 12 |
| PitchHub 36Kr | 28 | 2 | 27 | 21 | 9 |
| Generic web | 220 | - | 85 | 34 | 37 |

## Model Routing Evidence

The report recorded the expected model routing:

| Stage | Task type | Model |
|---|---|---|
| `xlsx_team_synthesis` | `trusted_xlsx_structuring` | `deepseek-v4-lite` |
| `news_iyiou` | `search_hint_generation` | `deepseek-v4-lite` |
| `news_pitchhub` | `search_hint_generation` | `deepseek-v4-lite` |
| `generic_source_judgment` | `source_judgment` | `deepseek-v4-pro` |
| `signal_extract` | `financing_extraction` | `deepseek-v4-pro` |
| `source_product_extract` | `generic_product_admission` | `deepseek-v4-pro` |
| `multi_source_narrative` | `multi_source_profile_synthesis` | `deepseek-v4-pro` |

## What The Run Proved

- The post-optimization runner can complete the 200-company dry-run after adding child concurrency, provider rate limiting, timeout handling, and child checkpoints.
- Dry-run isolation is now working for business fact tables; only audit evidence is written.
- Generic source judgment and multi-source narrative checkpoints land per company, so slow or failed companies no longer hide all shard progress.
- Company model routing is visible in the batch artifact and matches the current routing policy.

## Remaining Scaleout Risks

- Runtime is still too long for a direct 1024-company run. At the observed pace, a full dry-run would likely require roughly a day unless more internal web/LLM parallelism or stage pruning is added.
- `source_product_extract` had weaker per-company observability during this dry-run because it was source-row driven; this was fixed after the run by checkpointing every requested company, including companies with no source rows. A rerun is needed to observe the fixed state shape.
- `news_ingest` accepted `--concurrency` during this dry-run, but the core per-company web search loop was still mostly serial; this was fixed after the run by adding company-level concurrent fetch workers. A rerun is needed to measure the speed impact.
- Target-customer coverage appeared as `products_with_target_customers=0` in this dry-run because child scripts did not report the metric upward; this was fixed after the run for XLSX and source-product extraction reports. A rerun is needed to capture the corrected count.
- Funding event coverage remains low: the run extracted 2 dry-run events, and persistence/vector refresh were intentionally skipped.
- Eight selected companies did not get a multi-source narrative: seven `sparse_material`, one structured-output/length failure.
- The 200-company live bounded run, touched-vector refresh, RAG smoke checks, and 5180 manual inspection are still required before any 1024-company execution.

## Decision

Task 8.5 is satisfied by this run. Do not start the 1024-company dry-run or live rerun yet. The next gate is the 200-company live bounded run with selected-company-only persistence, followed by touched-vector refresh, RAG smoke checks, and 5180 inspection.
