# 1024-Company Full Live Rerun Effect Report

Change: `company-scaleout-enrichment-hardening`

Date: 2026-05-31

## Scope

- Batch: `a1a72d01-e054-48e9-8124-f62e920ab3f7`
- Company scope: 1024 XLSX-backed canonical companies
- Runtime scope: real official-site, Yiou, PitchHub/36Kr, generic web, Serper, and DeepSeek access
- Persistence scope: live business-fact writes enabled for the selected 1024 companies
- Milvus scope: refreshed only the touched 1024 company vectors in the 5180 backend Milvus Lite store

The full live rerun followed the completed full dry-run gate:
`84fd0f38-1430-4532-9787-098f2663a3ce`.

## Batch Result

| Metric | Value |
|---|---:|
| Selected companies | 1024 |
| Processed companies | 1024 |
| Succeeded companies | 1024 |
| Failed companies | 0 |
| Batch status | `succeeded` |
| Batch current stage | `succeeded` |
| Started at | 2026-05-31T12:06:40Z |
| Finished at | 2026-05-31T13:25:16Z |

All 8193 reported stage executions succeeded:

| Stage | Succeeded |
|---|---:|
| `baseline_readiness` | 1 |
| `xlsx_team_synthesis` | 1024 |
| `official_product_capture` | 1024 |
| `news_iyiou` | 1024 |
| `news_pitchhub` | 1024 |
| `generic_source_judgment` | 1024 |
| `signal_extract` | 1024 |
| `source_product_extract` | 1024 |
| `multi_source_narrative` | 1024 |

## Row-Count Delta

| Table | Before | After | Delta |
|---|---:|---:|---:|
| `company_product` | 620 | 2346 | +1726 |
| `company_product_evidence` | 1980 | 6929 | +4949 |
| `company_application_scenario` | 370 | 1136 | +766 |
| `company_signal_event` | 694 | 846 | +152 |
| `company_news_item` | 973 | 4702 | +3729 |
| `company_enrichment_search_audit` | 11450 | 17008 | +5558 |

## Coverage After Live Rerun

| Coverage item | Companies / rows |
|---|---:|
| Companies with products | 666 / 1024 |
| Product rows | 2346 |
| Companies with product target customers | 83 / 1024 |
| Product rows with target customers | 102 |
| Companies with technical tags | 490 / 1024 |
| Product rows with technical tags | 1258 |
| Companies with application scenarios | 341 / 1024 |
| Application scenario rows | 1136 |
| Companies with signal events | 579 / 1024 |
| Funding or financing signal events | 843 |
| Funding or financing signal events with primary news | 268 |
| Companies with news/source items | 928 / 1024 |
| News/source item rows | 4702 |
| Companies with `profile_summary` | 1014 / 1024 |
| Companies with `technology_route_summary` | 1014 / 1024 |

Funding is represented as `event_type='funding'` in the current schema. The
effect metrics keep the older `financing` check visible, but this report treats
`funding` and `financing` as the business-facing financing category.

## Source Search Audit

| Source adapter | Queries | Results | Accepted | Rejected | Rejected by name mismatch | Rejected by irrelevant path |
|---|---:|---:|---:|---:|---:|---:|
| `generic_web` | 3166 | 15500 | 3995 | 0 | 0 | 0 |
| `iyiou` | 1196 | 2176 | 361 | 1745 | 1698 | 47 |
| `pitchhub_36kr` | 1196 | 6988 | 407 | 6413 | 5915 | 498 |

The generic-web rejection counters are zero because generic source judgment
records accepted material after LLM/company-identity gating instead of using
the site-filter rejection columns that Yiou and PitchHub use.

## Quality And Manual Review

| Fact type | Status | Rows | Avg confidence |
|---|---|---:|---:|
| Product | `needs_review` | 1842 | 0.858 |
| Product | `ready` | 504 | 0.736 |
| Application scenario | `needs_review` | 967 | 0.891 |
| Application scenario | `ready` | 169 | 0.869 |

Manual-review exposure:

| Review item | Count |
|---|---:|
| Companies with review-gated products | 666 |
| Companies with review-gated scenarios | 341 |
| Companies with any review-gated product/scenario fact | 671 |

The company base records are not blocked by these review states. Review gating
applies to extracted products and scenarios so operators can accept or reject
facts while the enriched company profile remains visible.

## Vector Refresh And RAG Smoke

The 5180 frontend is backed by `apps/admin-console` and no explicit
`CHAT_MILVUS_URI` or `MILVUS_URI` was present in the backend process
environment. Therefore the touched-company refresh used:
`apps/admin-console/milvus.db`.

Vector refresh result:

| Metric | Value |
|---|---:|
| Companies total | 1024 |
| Companies processed | 1024 |
| Companies skipped | 0 |
| Companies with errors | 0 |
| Duration | 48.8 seconds |

The first refresh invocation failed before execution because zsh scalar
expansion passed the company-id list as one argument. The retry used a bash
array, processed all 1024 companies, and returned zero company errors.

RAG smoke checks passed 5/5 using the refreshed admin-console Milvus store:

| Category | Query target | Expected company | Hit rank |
|---|---|---|---:|
| Product | Lung percutaneous intervention surgery robot | `COMP-2640a0f609b5` | 1 |
| Target customer | MetalenX flat metalens / AR / VR / consumer electronics / security | `COMP-54fd4dd036ff` | 1 |
| Scenario | Unmanned offline operations / factory / smart brain | `COMP-37013bba3132` | 1 |
| Recent financing | B++ round / nearly USD 50m / Long-Z / CCV | `COMP-8ed85d2c2d59` | 1 |
| Profile summary | OneGu / Youxin / points mall / CRM / supply chain | `COMP-17d68ddf7fd6` | 1 |

## 5180 Inspection

Representative page:
`http://127.0.0.1:5180/company/COMP-54fd4dd036ff`.

Evidence:

- Text snapshot:
  `.agents/runs/company-scaleout-enrichment-hardening/5180-company-metalenx-full-live-text-20260531.txt`
- DOM snapshot:
  `.agents/runs/company-scaleout-enrichment-hardening/5180-company-metalenx-full-live-snapshot-20260531.txt`
- Screenshot:
  `.agents/runs/company-scaleout-enrichment-hardening/screenshots/5180-company-metalenx-full-live-20260531.png`

Observed checks:

| UI check | Result |
|---|---|
| Company summary label is `公司简介`, not `个人简介` | Passed |
| `个人简介` absent | Passed |
| Product section present | Passed |
| Application scenario section present | Passed |
| Technology route section present | Passed |
| Target customer text present | Passed |
| MetalenX product text present | Passed |
| Financing round text present | Passed |
| Recent dynamics section present as `最近动态` | Passed with label note |

The page label is `最近动态`, not the exact wording `最新动态`. This is a UI
copy difference, not a missing-data issue.

## Residual Risks

- Product target-customer coverage remains low: 83/1024 companies and 102/2346
  product rows. This is a quality-improvement item for source prompts and
  official-site extraction, not a rerun blocker.
- 671 companies have at least one review-gated product or scenario fact. This
  is expected under the LLM quality gate, but operator review tooling remains
  important before treating every product/scenario as verified.
- Official-site coverage is still bounded by site availability, anti-bot
  behavior, and JavaScript rendering quality. This run used the hardened
  acquisition path and records diagnostics, but it does not bypass CAPTCHA,
  login, paywalls, or robots restrictions.
- Generic-web accepted counts rely on LLM identity/fact-attribution gating and
  do not populate the Yiou/PitchHub rejection columns. Search-audit semantics
  should stay source-adapter-specific in downstream reporting.
- The 5180 backend uses the admin-console default Milvus Lite path unless an
  explicit Milvus URI is configured. Future deployments should set the Milvus
  URI explicitly to avoid ambiguity.

## Evidence Artifacts

- Live batch creation:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-batch-20260531T120621Z.json`
- Live command output:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-20260531T120639Z.json`
- Live command stderr:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-20260531T120639Z.stderr.txt`
- Before counts:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-before-counts-20260531T120621Z.json`
- After counts:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-after-counts-20260531T132516Z.json`
- Machine summary:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-summary-20260531T132516Z.json`
- Effect metrics:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-effect-metrics-20260531T134500Z.json`
- Vector refresh:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-admin-milvus-refresh-20260531T133200Z.json`
- RAG smoke:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-live-rerun-rag-smoke-20260531T133320Z.json`
