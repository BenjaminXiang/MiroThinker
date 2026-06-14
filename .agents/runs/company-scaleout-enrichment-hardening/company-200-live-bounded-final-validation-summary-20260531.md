# 200-Company Live Bounded Final Validation Summary

Generated: 2026-05-31

## Scope

- Batch: `66e8bcda-2030-42eb-84fb-5edefff97a43`
- Sample: 200 fixed company IDs from `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-selected-company-ids.txt`
- Database: `miroflow_real`
- Full 1024-company execution: not run in this gate

## Live Bounded Run

- Report: `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-resume-provider8-subchunk1-20260531T0532Z.json`
- Summary: `.agents/runs/company-scaleout-enrichment-hardening/company-200-live-bounded-summary-20260531.md`
- Result: succeeded
- Companies processed: 200
- Companies succeeded: 200
- Companies failed: 0
- Stderr: empty
- Provider limits: DeepSeek max concurrency 8, Serper max concurrency 4
- Stage subchunk size: 1 company

Post-run row-count deltas from the live bounded run:

| Table | Delta |
|---|---:|
| `company_product` | +332 |
| `company_product_evidence` | +1054 |
| `company_application_scenario` | +175 |
| `company_signal_event` | +77 |
| `company_news_item` | +602 |
| `company_enrichment_search_audit` | +1047 |

## Generic Web Identity Cleanup

After 5180 inspection found near-name contamination on `COMP-17d68ddf7fd6`,
generic web identity gating was hardened and replayed against the 200-company
accepted generic-web rows.

Artifacts:

- Initial audit: `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-guard-audit-20260531T071057Z.json`
- Alias-aware audit: `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-guard-audit-after-3char-alias-20260531T071721Z.json`
- Cleanup: `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-cleanup-20260531T071848Z.json`
- Post-cleanup audit: `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-guard-post-cleanup-audit-20260531T071910Z.json`

Cleanup result:

| Item | Count |
|---|---:|
| Accepted generic-web rows checked before cleanup | 725 |
| Invalid rows after alias-aware guard | 90 |
| Affected companies | 56 |
| Deleted `company_news_item` rows | 90 |
| Deleted `company_product_evidence` rows | 187 |
| Deleted `company_product` rows | 48 |
| Deleted `company_application_scenario` rows | 32 |
| Deleted `company_signal_event` rows | 0 |
| Accepted generic-web rows checked after cleanup | 635 |
| Invalid rows after cleanup | 0 |

## Narrative and Vector Refresh

- Affected-company list: `.agents/runs/company-scaleout-enrichment-hardening/company-generic-source-identity-cleanup-affected-company-ids.txt`
- Narrative refresh partial run: `.agents/runs/company-scaleout-enrichment-hardening/company-post-cleanup-narrative-refresh-20260531T071937Z.json`
- Narrative refresh remaining run: `.agents/runs/company-scaleout-enrichment-hardening/company-post-cleanup-narrative-refresh-remaining12-20260531T074059Z.json`
- Vector refresh: `.agents/runs/company-scaleout-enrichment-hardening/company-post-cleanup-milvus-refresh-affected56-20260531T074642Z.json`

Result:

- 56 affected companies had `profile_summary` / `technology_route_summary`
  refreshed after cleanup.
- The first narrative refresh was terminated after a long-tail LLM wait; 44
  companies had already committed. The remaining 12 were rerun and succeeded.
- The affected 56 company vectors were refreshed successfully: 56 processed, 0
  errors.

## RAG Smoke

- Initial post-cleanup RAG smoke: `.agents/runs/company-scaleout-enrichment-hardening/company-post-cleanup-rag-smoke-20260531T074750Z.json`
- Final passing RAG smoke: `.agents/runs/company-scaleout-enrichment-hardening/company-post-cleanup-rag-smoke-pass5-20260531T074843Z.json`

Final result: 5/5 passed.

Covered queries:

- `product_metalenx`: product / target customer query for `COMP-54fd4dd036ff`
- `profile_onegu`: profile-summary query for `COMP-17d68ddf7fd6`
- `scenario_boyun`: application-scenario query for `COMP-37013bba3132`
- `recent_financing_botinkit`: financing query for `COMP-8ed85d2c2d59`
- `cleaned_identity_yibu`: cleaned identity query for `COMP-79167faf0c77`

## 5180 Inspection

Artifacts:

- Metalens detail screenshot: `.agents/runs/company-scaleout-enrichment-hardening/screenshots/5180-company-metalenx-detail-20260531.png`
- OneGu post-cleanup screenshot: `.agents/runs/company-scaleout-enrichment-hardening/screenshots/5180-company-onegu-post-cleanup-20260531.png`
- OneGu post-cleanup inspection: `.agents/runs/company-scaleout-enrichment-hardening/5180-company-onegu-post-cleanup-inspection-20260531.json`

Checks:

- Search and detail navigation worked for `深圳迈塔兰斯科技`.
- `COMP-54fd4dd036ff` displayed products, target customers, application
  scenarios, recent financing, source links, and ready status.
- `COMP-17d68ddf7fd6` no longer displayed the near-name contaminants
  `股一科技` or `深圳市的一科技`.
- `COMP-17d68ddf7fd6` no longer displayed the company profile under a
  `个人简介` label.
- `COMP-17d68ddf7fd6` retained the trusted XLSX-backed `友心` / `积分商城`
  company profile narrative.

## Residual Risks

- The 1024-company full dry-run and live rerun remain blocked until task 9.5
  starts.
- The post-cleanup narrative refresh exposed a long-tail LLM runtime issue;
  future full-scale runs need per-call timeout, retry, and per-company
  checkpoint evidence inside LLM-heavy scripts.
- Product target-customer coverage is still low and needs extractor/prompt
  improvement, but it no longer blocks this 200-company validation gate.
- Official-site coverage remains constrained by site availability, JS rendering,
  robots/compliance limits, and anti-bot behavior.
