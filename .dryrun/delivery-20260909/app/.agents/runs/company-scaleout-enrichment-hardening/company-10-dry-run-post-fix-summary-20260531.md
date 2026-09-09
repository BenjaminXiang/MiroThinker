# 10-Company Post-Fix Dry-Run Smoke

Date: 2026-05-31

Batch: `88cd2a26-bc87-401a-b4ed-2baa2a9a55ff`

Artifact:
- `.agents/runs/company-scaleout-enrichment-hardening/company-10-dry-run-post-fix-20260531T0030Z.json`
- `.agents/runs/company-scaleout-enrichment-hardening/company-10-dry-run-post-fix-20260531T0030Z.stderr.txt`

Command scope:
- 10 selected imported companies.
- `--dry-run --skip-persistence --skip-milvus`.
- `--child-llm-concurrency 2`.
- `--child-web-concurrency 2`.
- Stage concurrency remained 1 for the smoke run.

Result:
- Status: `succeeded`.
- Companies selected: 10.
- Companies processed: 10.
- Companies succeeded: 10.
- Companies failed: 0.
- Stderr: empty.

No-write check:
- `company_product`: remained 336.
- `company_product_evidence`: remained 1113.
- `company_application_scenario`: remained 227.
- `company_signal_event`: remained 617.
- `company_news_item`: remained 461.
- `company_enrichment_search_audit`: increased from 4793 to 4845, matching the dry-run `query_count=52`.

Observed metrics:
- Queries: 52.
- Fetches: 22.
- Accepted sources: 29.
- Rejected sources: 53.
- LLM failures: 21.
- Products extracted or synthesized: 3.
- Products with target customers: 1.
- Scenarios extracted or synthesized: 0.
- Funding events: 0.
- Multi-source narratives: 10.
- Rejected product/scenario candidates: 20.

Stage observations:
- `news_iyiou`, `news_pitchhub`, `generic_source_judgment`, `source_product_extract`, and `multi_source_narrative` all completed with zero company errors.
- `run_config.child_concurrency` recorded `llm=2` and `web=2`.
- Stage policy model routing remained correct: trusted XLSX/search-hint tasks used `deepseek-v4-lite`; source judgment, financing extraction, source-product admission, and multi-source synthesis used `deepseek-v4-pro`.
- The source-product stage reported `products_with_target_customers=0`; the batch-level target-customer count came from XLSX/team synthesis.

Conclusion:
- The post-dry-run fixes are E2E-smoke verified for command wiring, per-company completion, no-write behavior, and metric propagation.
- This smoke is not a substitute for the 200-company live bounded validation.
- Before a full 1024-company run, the slow `multi_source_narrative` stage still needs careful concurrency/rate-limit tuning and bounded live validation evidence.
