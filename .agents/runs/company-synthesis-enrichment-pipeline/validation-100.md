## 100-Company Upload-Scoped Validation

Date: 2026-05-29 UTC

Change: `company-synthesis-enrichment-pipeline`

This validation used the uploaded XLSX path and a bounded 100-company sample.
It did not run a full 1024-company live refresh.

### Batch IDs

| Item | ID |
| --- | --- |
| Upload task | `48a4dba7-6421-40e0-a674-84fd0a6dde0d` |
| Source page | `c67aa33a-dfb4-489e-a417-042e8a355c56` |
| Import batch | `2c30b826-4aaa-48ca-8ce9-8bc5dc56c275` |
| No-live-web dry-run batch | `2f157839-aab2-469f-b09c-122e21c4f8b8` |
| Live validation batch | `b854d0e0-1bcc-4ea8-968c-b4b4dab1f45c` |

The live batch used deterministic sample seed
`company-enrichment-100-2026-05-28-upload-path-v1-source-product-gate`.

### Cleanup Before Replay

Historical 10% validation noise and interrupted replay output were removed by
batch, source, and timestamp markers only. Unrelated production/test company
data was not bulk-deleted.

The final replay started from the same live batch after resetting the 100
sample company states for the affected stages.

### Final Batch Status

| Batch | Status | Companies | Succeeded | Failed | Started | Finished |
| --- | --- | ---: | ---: | ---: | --- | --- |
| Dry-run `2f157839-aab2-469f-b09c-122e21c4f8b8` | `succeeded` | 100 | 100 | 0 | `2026-05-28 22:52:33+00` | `2026-05-28 23:09:07+00` |
| Live `b854d0e0-1bcc-4ea8-968c-b4b4dab1f45c` | `succeeded` | 100 | 100 | 0 | `2026-05-28 23:49:06+00` | `2026-05-29 03:05:35+00` |

### Aggregate Results

| Metric | Result |
| --- | ---: |
| Sample companies | 100 |
| Resolved companies | 100 |
| Company base records with `quality_status='ready'` | 100 |
| Companies with profile length >= 300 | 99 |
| Companies with profile length >= 500 | 99 |
| Companies with technology-route summary length >= 80 | 99 |
| Median profile length | 762 |
| Vectors refreshed | 100 |

### Source Discovery and Audit

| Adapter | Companies | Queries | Results | Accepted | Name-mismatch rejects | Queries with miss reason |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `generic_web` | 100 | 314 | 1566 | 415 | 0 | 36 |
| `iyiou` | 100 | 1084 | 1038 | 71 | 725 | 741 |
| `pitchhub_36kr` | 100 | 1090 | 3810 | 88 | 2660 | 637 |

News/source material rows in the sample:

| Source | Rows | Companies |
| --- | ---: | ---: |
| `generic_web`, unknown tier | 356 | 88 |
| `iyiou` | 42 | 30 |
| `pitchhub_36kr` | 31 | 30 |
| `generic_web`, official tier | 26 | 19 |
| `generic_web`, trusted tier | 6 | 6 |

Current miss reasons:

| Miss reason | Companies |
| --- | ---: |
| `synthesis_no_facts` | 72 |
| `llm_rejected` | 14 |
| `all_results_rejected` | 3 |
| `no_results` | 1 |

These miss reasons are not equivalent to "no public data exists"; they mean
the current bounded search, identity gate, fetch, extraction, or synthesis stage
did not produce publishable facts for that company.

### Products, Scenarios, Funding, and Team

| Area | Result |
| --- | ---: |
| Products total in sample | 336 |
| Products `ready` | 152 |
| Products `needs_review` | 184 |
| Companies with any product | 87 |
| Companies with ready product | 82 |
| Products with target customers | 10 |
| Products with product-level application scenarios | 112 |
| Application scenarios total | 227 |
| Application scenarios `ready` | 146 |
| Companies with any scenario | 55 |
| Companies with ready scenario | 50 |
| Scenarios with target customer | 158 |
| Signal events total | 97 |
| Funding events | 97 |
| Companies with funding event | 55 |
| Source-backed signal events | 42 |
| Team members | 423 |
| Structured team members | 290 |
| Companies with structured team | 86 |

Product evidence by source tier:

| Source tier | Evidence rows | Products | Companies |
| --- | ---: | ---: | ---: |
| `xlsx` | 498 | 152 | 82 |
| `generic_web` | 377 | 111 | 42 |
| `pitchhub_36kr` | 116 | 40 | 21 |
| `iyiou` | 72 | 20 | 14 |
| `official_site` | 50 | 44 | 18 |

Scenario evidence by source tier:

| Source tier | Evidence rows | Scenarios | Companies |
| --- | ---: | ---: | ---: |
| `xlsx` | 146 | 146 | 50 |
| `generic_web` | 50 | 49 | 17 |
| `pitchhub_36kr` | 36 | 36 | 13 |
| `iyiou` | 23 | 23 | 9 |

### Data Quality Regression Checks

Escaped pollution case: `COMP-10047ff88d61`.

| Check | Result |
| --- | ---: |
| Bad Arabica/coffee news rows | 0 |
| Bad Arabica/coffee products | 0 |
| Ready products for the company | 1 |

The systemic fixes applied before the final replay were:

- Site-specific Yiou/PitchHub identity acceptance no longer treats broad
  LLM aliases or product phrases as target-company identity proof.
- Source-product extraction now uses an LLM candidate-level gate for
  generic, Yiou, and PitchHub material, so related articles, similar projects,
  investors, customers, platform recommendations, and other-company products
  are rejected before persistence.
- PDF and non-HTML generic fetches are skipped safely instead of failing the
  source-judgment stage.

### 5180 Manual Inspection

Server inspected: `http://127.0.0.1:5180`, connected to the real validation DB.

| Company | Observation |
| --- | --- |
| `COMP-37013bba3132` | Section order is Basic Information, Products, Application Scenarios, Recent Events, Summary, Sources. Product, scenarios, funding history, long profile, technology route, and source links are visible. |
| `COMP-54fd4dd036ff` | Product fields show only product name, category, description, technical tags, target customers, and scenarios. Application scenarios and recent funding events are visible. |
| `COMP-10047ff88d61` | Pollution regression is not visible on the page. Product and recent funding are visible; application scenario remains empty because no publishable scenario was extracted for the product. |
| `COMP-7a89e82e6329` | The base company record is ready and the detail page falls back to the XLSX description and business fields. No product, scenario, recent dynamics, or external source is currently available. |

The company detail uses the localized Company Profile label, not the localized
Personal Profile label. The primary page order matches the required display
contract.

### DeepSeek Runtime

The local ignored `.env` is aligned to `deepseek-v4-pro` for this rollout.
Fresh smoke check:

```json
{
  "model": "deepseek-v4-pro",
  "finish_reason": "stop",
  "has_reasoning_content": false,
  "content_excerpt": "{\"ok\":true,\"mode\":\"non-thinking\"}"
}
```

The raw SDK smoke strips inherited proxy variables before client creation. The
project runtime client itself uses `trust_env=false`, so the app path does not
depend on the shell proxy state.

### LLM Usage Inventory for Next Model-Tier Discussion

Current rollout decision: all LLM-backed company tasks use
`deepseek-v4-pro` in non-thinking mode.

| Usage point | Current model | Suggested next-tier discussion |
| --- | --- | --- |
| Generic source snippet sufficiency and identity judgment | `deepseek-v4-pro` | Consider `deepseek-v4-lite` for obvious snippet triage and keep `pro` for fetched full pages or ambiguous identity. |
| Yiou/PitchHub search hint extraction | `deepseek-v4-pro` | Candidate for `deepseek-v4-lite` because it extracts aliases, founders, and keywords from XLSX text. |
| Yiou/PitchHub identity and detail acceptance | `deepseek-v4-pro` | Keep `pro` for ambiguous company identity and source attribution. |
| Source product/scenario candidate gate | `deepseek-v4-pro` | Candidate hybrid: `lite` for simple reject/accept, `pro` for high-value or ambiguous product ownership. |
| XLSX product/scenario synthesis | `deepseek-v4-pro` | Candidate for `deepseek-v4-lite` when material is short and structured; keep `pro` when official/generic materials are long. |
| Team raw structuring | `deepseek-v4-pro` | Candidate for `lite` on short XLSX-only team text; keep `pro` for long mixed-source team material. |
| Multi-source profile and technology-route synthesis | `deepseek-v4-pro` | Keep `pro`; this is the highest-value summarization task and affects retrieval text. |
| Funding signal extraction and conflict handling | `deepseek-v4-pro` | Candidate hybrid: `lite` for explicit table rows, `pro` for conflict/newer-round judgment. |
| Admin chat synthesis/classification touched by this rollout | `deepseek-v4-pro` | Classification/routing can later move to a lighter model; final synthesis should remain `pro` until quality is benchmarked. |

Parallel LLM extraction is intentionally not implemented in this round. The next
optimization should add bounded concurrency with per-stage checkpointing,
provider rate-limit handling, retry budgets, and per-company recoverability.

### Residual Risks Before Expanding Beyond 100 Companies

- One sampled company (`COMP-7a89e82e6329`) has sparse XLSX material and no
  accepted external material; its detail page is usable through XLSX fallback,
  but synthesized profile/product/scenario enrichment is empty.
- Product coverage is much better after XLSX synthesis, but target-customer
  coverage is still low at 10 product rows. More official-site or LLM extraction
  work is needed before claiming strong target-customer completeness.
- Official-site capture is limited by reachability and page structure; only 19
  sampled companies produced official-tier source rows and 18 produced
  official-site product evidence.
- Most site-specific searches still end in `synthesis_no_facts` or
  `llm_rejected`; this is now auditable but should be reviewed before full
  rollout so operators can distinguish true absence from recall/extraction gaps.
- Multi-source narrative generation still produced split-fallback logs during
  validation. The final 100-company result is acceptable, but the next change
  should improve JSON/schema repair and prompt output stability.
