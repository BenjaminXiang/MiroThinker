# 200-Company Live Bounded Validation Summary - 2026-05-31

## Scope

- Change: `company-scaleout-enrichment-hardening`
- Batch: `66e8bcda-2030-42eb-84fb-5edefff97a43`
- Source XLSX: `/home/longxiang/MiroThinker/docs/企业总表.xlsx`
- Selected companies: 200 fixed IDs from `company-200-live-bounded-selected-company-ids.txt`
- Full population attempted: false
- Persistence: live business writes enabled for selected companies only
- Milvus: skipped in this run; touched-vector refresh remains a separate gate

## Final Result

- Runner artifact: `company-200-live-bounded-resume-provider8-subchunk1-20260531T0532Z.json`
- Stderr artifact: `company-200-live-bounded-resume-provider8-subchunk1-20260531T0532Z.stderr.txt`
- Runner status: succeeded
- DB batch status: succeeded
- Companies processed: 200
- Companies succeeded: 200
- Companies failed: 0
- Company states: 200 `batch_complete/succeeded`; 824 unselected imported companies remained queued
- Stderr bytes: 0

## Runtime Configuration

- Stage concurrency: 4
- LLM stage concurrency: 4
- Web stage concurrency: 4
- Stage subchunk size: 1 for the final successful resume
- Child LLM concurrency: 4
- Child web concurrency: 4
- DeepSeek provider max concurrency: 8
- Serper provider max concurrency: 4
- DeepSeek min interval: 0.05 seconds
- Serper min interval: 0.10 seconds

## Count Deltas

Baseline before live run:

- `company_product`: 336
- `company_product_evidence`: 1113
- `company_application_scenario`: 227
- `company_signal_event`: 617
- `company_news_item`: 461
- `company_enrichment_search_audit`: 4845

After live run:

- `company_product`: 668, delta +332
- `company_product_evidence`: 2167, delta +1054
- `company_application_scenario`: 402, delta +175
- `company_signal_event`: 694, delta +77
- `company_news_item`: 1063, delta +602
- `company_enrichment_search_audit`: 5892, delta +1047

## Batch Summary Metrics

- Queries: 138
- Fetches: 62
- Accepted sources: 92
- Rejected sources: 145
- LLM failures or rejected/empty outcomes counted by child summaries: 74
- Products produced or extracted in this final resume report: 113
- Scenarios produced or extracted in this final resume report: 61
- Products with target customers in this final resume report: 2
- Funding events extracted in this final resume report: 9
- Multi-source narratives generated in this final resume report: 49
- Rejected product/scenario candidates: 169
- Vector refresh count: 0, because `--skip-milvus` was intentionally set

## Observed Bottlenecks And Fixes

- Stage-level and child-level concurrency alone did not raise real LLM API concurrency because the DeepSeek provider limiter defaulted to 4. The runner now exposes provider limiter overrides through `--provider-llm-max-concurrency` and `--provider-serper-max-concurrency`.
- `stage_subchunk_size=8` still allowed one slow source row to block checkpointing for multiple companies. The successful resume used `--stage-subchunk-size 1`, giving company-level child processes and company-level checkpoints.
- `source_product_extract`, `generic_source_judgment`, and `multi_source_narrative` remain the runtime hotspots. Company-level subchunks made them resumable and observable, but future full-scale runs should add finer per-query/per-source timeout and progress reporting.
- Successful batch completion left a stale manual restart `last_error` on the batch row. The batch finalizer now clears `last_error` when status is `succeeded`, and the live batch row was cleaned to `last_error=NULL`.

## Residual Risks

- Milvus refresh and RAG smoke checks were not run in this command and remain task 8.7.
- 5180 search/detail inspection was not run in this command and remains tasks 6.5 and 8.8.
- Generic web source judgment has long-tail latency. For 1024 companies, company-level subchunks should be kept, and per-query/per-source timeouts should be considered.
- Target-customer coverage is still low in the final resume report and needs extractor/prompt follow-up after the current validation gates.
