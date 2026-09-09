# Company Source Quality Gates Next Task Spec

## Scope

This spec defines the next implementation slice for the active OpenSpec change:
`company-scaleout-enrichment-hardening`.

The next slice is the external-source quality gate and diagnostics layer. It
prevents Yiou, PitchHub, official-site, and generic web materials from polluting
Company products, scenarios, financing facts, summaries, or vectors when a page
mentions competitors, related articles, investors, customers, similar projects,
platform recommendations, or generic industry content.

This slice is not the 200-company validation run or the 1024-company full
rerun. It is the quality boundary that must be correct before a larger live run
is trustworthy.

## Current Baseline

- The OpenSpec change is active and valid.
- Completed tasks: 22 of 51.
- The prior upload-batch hardening slice completed:
  - per-stage execution policy;
  - bounded LLM/web concurrency;
  - retry/backoff and structured-output failure classification;
  - stage checkpoint/resume metadata;
  - batch summary counters.
- Generic source judgment already rejects accepted-looking sources when:
  - target company identity is not confirmed;
  - fact attribution to the target company is not confirmed.
- Source product extraction already has two LLM gates:
  - a generic web source admission gate;
  - a product/scenario candidate attribution gate for generic web, Yiou, and
    PitchHub.
- The main confirmed gap is diagnostics and enforcement consistency:
  - source/candidate rejection reasons are counted but not preserved in the
    product extraction report;
  - rejected candidate details are not yet available to batch/company
    diagnostics;
  - source-to-product writes need a clear contract that only six business-facing
    fields are emitted;
  - generic web facts must remain review-gated unless strong source judgment is
    present.

## Primary Goal

Make every non-XLSX external fact pass explicit company-identity and
fact-attribution gates before it can become a Company product, scenario,
financing signal, narrative input, or vector input, and preserve accepted and
rejected reasons so operators can understand why each company was or was not
enriched.

## OpenSpec Tasks Covered By This Slice

Target these pending tasks first:

- `3.2` Update generic source judgment so accepted material requires
  target-company identity and fact attribution before any source feeds synthesis
  or vector text.
- `3.3` Add product-ownership and scenario-attribution gates to prevent related
  articles, investors, customers, competitors, similar projects, and platform
  recommendations from becoming target-company facts.
- `3.4` Ensure source-product extraction writes only the six business-facing
  product fields: product name, product description, product category,
  technical tags, target customers, and application scenarios.
- `3.5` Ensure generic-web-only facts remain review-gated unless source judgment
  confirms strong identity and attribution evidence.
- `3.6` Preserve rejected source and rejected candidate reasons in
  batch/company diagnostics.

Do not mark these tasks complete until tests prove the behavior and the
acceptance matrix records current-session evidence.

## Non-Goals

- Do not run the 200-company dry-run or live run in this slice.
- Do not run full XLSX-scale enrichment.
- Do not implement admin-console display changes in this slice unless a tiny
  API/report field is needed to expose the diagnostic contract.
- Do not replace the existing child scripts with a new monolithic agent.
- Do not solve semantic attribution with regex-only logic. Deterministic checks
  may normalize obvious syntax and remove obvious noise, but company identity,
  product ownership, scenario attribution, and source suitability must be decided
  by LLM gates or existing trusted evidence.
- Do not bypass CAPTCHA, bot challenges, robots restrictions, login walls,
  paywalls, HTTP 403, or HTTP 429.
- Do not store API keys, credential-bearing environment values, raw prompts with
  secrets, or raw sensitive model responses in diagnostics.

## Files To Inspect First

- `apps/miroflow-agent/scripts/run_company_source_product_extract.py`
  - generic web product source gate;
  - product/scenario candidate attribution gate;
  - report shape;
  - product/scenario persistence call sites.
- `apps/miroflow-agent/src/data_agents/company/source_product_extractor.py`
  - product quality status;
  - scenario quality status;
  - source-material tier handling;
  - six-field product contract.
- `apps/miroflow-agent/src/data_agents/company/generic_source_judgment.py`
  - final source judgment gate;
  - accepted/rejected result models.
- `apps/miroflow-agent/scripts/run_company_generic_source_judgment.py`
  - accepted source persistence;
  - rejected source report shape;
  - per-company diagnostics.
- `apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py`
  - aggregation of child-script rejected source/candidate counters;
  - company stage status payload.
- `apps/miroflow-agent/tests/scripts/test_run_company_source_product_extract.py`
  - current RED tests for candidate rejection details.
- `apps/miroflow-agent/tests/data_agents/company/test_generic_source_judgment.py`
  - existing source identity and attribution regression tests.
- `apps/miroflow-agent/tests/scripts/test_run_company_generic_source_judgment.py`
  - script-level source judgment diagnostics tests.

## Required Behavior

### 1. Source Identity And Attribution Invariant

For every non-XLSX external source, accepted material must prove both:

- target company identity: the page is about the intended company or its trusted
  alias, not merely the same industry or a similarly named company;
- fact attribution: the page attributes the extracted fact to the target
  company, not to an investor, customer, partner, competitor, related article,
  similar project, or page recommendation.

If either condition is missing, the source or candidate must be rejected and the
reason must be preserved.

### 2. Generic Web Source Admission

Before generic web source text can be used for product or scenario extraction:

- the LLM source gate must decide that the page contains concrete products,
  services, named platforms, devices, solutions, or application scenarios
  provided by the target company;
- business registration pages, operating-scope pages, legal/credit pages,
  recruitment pages, generic company profiles, financing-only pages, patent-only
  pages, government lists, and broad technical capability pages must be rejected
  for product extraction unless they explicitly contain target-company product
  facts;
- the rejection reason from the LLM must be kept.

Minimum report detail for a rejected generic source:

```json
{
  "gate": "generic_product_source_gate",
  "reason": "工商注册经营范围，不是具体产品或解决方案材料",
  "rejected_count": 1,
  "company_id": "COMP-...",
  "source_adapter": "generic_web",
  "source_url": "https://..."
}
```

### 3. Product And Scenario Candidate Attribution

For generic web, Yiou, and PitchHub source materials:

- extracted product candidates must be kept only if the source text explicitly
  attributes the concrete product, named platform, device, service, solution,
  or productized offering to the target company;
- extracted scenarios must be kept only if the source explicitly ties the
  scenario to a kept product or to a concrete offering provided by the target
  company;
- candidates from related articles, investor profiles, customer stories,
  competitors, similar projects, navigation blocks, SEO titles, page
  recommendations, and unrelated project cards must be rejected;
- the LLM rejection reason must be preserved.

Minimum report detail for rejected candidates:

```json
{
  "gate": "product_candidate_attribution_gate",
  "reason": "candidate belongs to another company, not 奇朵智能设备",
  "rejected_count": 1,
  "company_id": "COMP-...",
  "source_adapter": "pitchhub_36kr",
  "source_url": "https://pitchhub.36kr.com/project/..."
}
```

### 4. Rejection Diagnostics Contract

`run_company_source_product_extract.py` must include these fields in its JSON
report:

```json
{
  "rejected_candidate_reasons": {
    "candidate belongs to another company, not 奇朵智能设备": 1
  },
  "rejected_candidates": [
    {
      "news_id": "11111111-1111-1111-1111-111111111111",
      "company_id": "COMP-QIDUO",
      "source_adapter": "pitchhub_36kr",
      "source_url": "https://pitchhub.36kr.com/project/1958568104891398",
      "gate": "product_candidate_attribution_gate",
      "reason": "candidate belongs to another company, not 奇朵智能设备",
      "rejected_count": 1
    }
  ]
}
```

The batch runner must preserve or aggregate these fields into company/stage
diagnostics when the source-product stage is executed.

### 5. Product Output Contract

The user-facing product object must expose only these business fields:

- product name;
- product description;
- product category;
- technical tags;
- target customers;
- application scenarios.

Internal fields such as source tier, quality status, confidence, extractor
version, evidence URL, evidence span, and timestamps may remain in storage or
diagnostics, but the business-facing product contract must not depend on them as
visible product fields.

### 6. Generic Web Review Gating

Generic web products and scenarios may become `ready` only when:

- product/scenario business fields are sufficiently complete;
- source judgment status is accepted;
- source judgment confidence is strong enough;
- source judgment confirms identity and fact attribution.

Otherwise they must remain `needs_review` or be rejected. `needs_review` must
not be treated as verified for later publication/RAG claims.

### 7. No Fabricated Facts

If an external page gives only weak, generic, or ambiguous evidence, the system
must prefer a rejected or needs-review diagnostic over fabricating a product,
scenario, financing round, target customer, or summary detail.

XLSX is the trusted baseline for existing company facts. External sources are
primarily for newer financing, product, scenario, and richer descriptive
supplementation.

## Current RED Tests To Make Green

The following tests already encode the first diagnostic gap and should fail
until implementation is complete:

```bash
cd apps/miroflow-agent
uv run pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py -q
```

Expected current failures:

- `test_cli_rejects_third_party_candidate_when_product_belongs_to_other_company`
  expects `report["rejected_candidate_reasons"]` and
  `report["rejected_candidates"]`.
- `test_cli_llm_gates_generic_registry_scope_before_product_extraction`
  expects the generic product source gate rejection reason to be preserved.

## Implementation Steps

### Step 1: Preserve Generic Source Gate Reason

Modify `run_company_source_product_extract.py` so the generic web admission gate
returns both:

- `allowed: bool`
- `reason: str`

Keep the existing boolean helper as a wrapper if needed for compatibility, but
the extraction flow must use the reason-aware function.

Use stable fallback reasons:

- `empty_source_text`
- `llm_source_gate_failed`
- `llm_source_gate_parse_failed`
- `llm_source_gate_rejected`

### Step 2: Preserve Candidate Attribution Gate Reason

Modify the product/scenario candidate LLM gate so it returns:

- filtered products;
- filtered scenarios;
- rejected count;
- rejection reason when rejected count is non-zero.

Use stable fallback reasons:

- `llm_candidate_gate_failed`
- `llm_candidate_gate_parse_failed`
- `candidate_gate_rejected`

### Step 3: Add Rejection Detail Helpers

Add small helpers in `run_company_source_product_extract.py`:

- build one rejection detail from a source row, gate, reason, and rejected count;
- append rejection details to the report;
- aggregate `rejected_candidate_reasons` by reason and count.

The helper must not log prompts, API keys, or raw credential-bearing payloads.

### Step 4: Wire Rejection Details Through Extraction

Change `_extract_products_and_scenarios` so it returns rejection details in
addition to the existing product/scenario/counter tuple.

The extraction loop must:

- keep existing counters;
- append detailed rejected candidates;
- preserve report shape in dry-run and live modes;
- keep empty `rejected_candidates` and empty `rejected_candidate_reasons` when
  nothing is rejected.

### Step 5: Verify Six-Field Product Contract

Add or extend tests proving source-product extraction emits business-facing
product payloads with the six required fields and does not surface internal
audit fields as product fields.

If the API/frontend already enforces this, reference the existing tests and do
not duplicate broad UI tests in this slice.

### Step 6: Verify Generic Web Review Gating

Add or extend tests proving generic web product/scenario rows remain
`needs_review` unless strong source judgment is attached.

If the current storage helper already satisfies this invariant, use a focused
test around `_product_quality_status` and `_scenario_quality_status` rather than
rewriting persistence.

### Step 7: Batch Diagnostic Aggregation

If `run_company_upload_enrichment_batch.py` already preserves child report
payloads sufficiently, add a test proving source-product rejection reasons are
visible in stage details or summary.

If not, extend the batch report summary with:

- `rejected_candidate_reasons`;
- `rejected_candidates_count`;
- per-stage or per-company rejected detail snippets.

Do not store unbounded rejected text in batch summaries.

## Verification Commands

Run the narrow RED/GREEN command first:

```bash
cd apps/miroflow-agent
uv run pytest -n0 --no-cov tests/scripts/test_run_company_source_product_extract.py -q
```

Then run the focused source-quality set:

```bash
cd apps/miroflow-agent
uv run pytest -n0 --no-cov \
  tests/scripts/test_run_company_source_product_extract.py \
  tests/data_agents/company/test_source_product_extractor.py \
  tests/data_agents/company/test_generic_source_judgment.py \
  tests/scripts/test_run_company_generic_source_judgment.py \
  -q
```

Then run the broader Company enrichment focused set:

```bash
cd apps/miroflow-agent
uv run pytest -n0 --no-cov \
  tests/data_agents/company/test_llm_routing.py \
  tests/data_agents/company/test_generic_source_judgment.py \
  tests/data_agents/company/test_source_product_extractor.py \
  tests/scripts/test_run_company_generic_source_judgment.py \
  tests/scripts/test_run_company_source_product_extract.py \
  tests/scripts/test_run_company_signal_extract.py \
  tests/scripts/test_run_company_xlsx_team_synthesis.py \
  tests/scripts/test_run_company_upload_enrichment_batch.py \
  tests/data_agents/company/test_enrichment_batch.py \
  -q
```

Compile touched Python files:

```bash
python -m compileall -q \
  apps/miroflow-agent/scripts/run_company_source_product_extract.py \
  apps/miroflow-agent/src/data_agents/company/source_product_extractor.py \
  apps/miroflow-agent/src/data_agents/company/generic_source_judgment.py \
  apps/miroflow-agent/scripts/run_company_upload_enrichment_batch.py
```

Validate OpenSpec after updating task evidence:

```bash
openspec validate company-scaleout-enrichment-hardening --strict
```

## Documentation Updates

After implementation and verification:

- update `openspec/changes/company-scaleout-enrichment-hardening/tasks.md`;
- update `openspec/changes/company-scaleout-enrichment-hardening/acceptance.md`;
- append current-session commands and outcomes to
  `.agents/runs/company-scaleout-enrichment-hardening/verification.md`.

Only mark tasks complete when current-session tests prove them.

## Done Criteria

This slice is done only when:

- the two existing RED tests in `test_run_company_source_product_extract.py`
  pass;
- third-party product/scenario candidates can be rejected with preserved reasons;
- generic web source admission rejections preserve reasons;
- product report JSON contains `rejected_candidate_reasons` and
  `rejected_candidates`;
- generic web facts remain review-gated unless strong identity and attribution
  evidence exists;
- the six product business fields are verified;
- batch/company diagnostics can expose rejection counts and reasons;
- focused source-quality tests pass;
- OpenSpec strict validation passes;
- OpenSpec tasks and acceptance evidence are updated.

## Remaining Work After This Slice

After source-quality gates are complete, the next slices should be:

1. Admin API and 5180 UI diagnostics:
   - batch progress;
   - per-company failure reason;
   - accepted/rejected source counts;
   - product/scenario/recent-dynamics/source-link display;
   - search/detail navigation.
2. Table-level idempotency:
   - official-source writes;
   - product writes;
   - scenario writes;
   - financing event writes;
   - profile summary writes;
   - vector refresh markers.
3. 200-company dry-run and live bounded validation:
   - deterministic sample selection;
   - cleanup of validation noise;
   - dry-run report;
   - live run only after dry-run prerequisites pass;
   - touched-company vector refresh;
   - RAG smoke checks;
   - 5180 manual inspection.
4. 1024-company full rerun after all current-goal validation passes:
   - run only after source-quality gates, admin diagnostics, idempotency, 200-company
     dry-run, 200-company live run, touched-vector refresh, RAG smoke checks, and
     5180 manual inspection all pass;
   - perform a full dry-run first and record expected writes, skipped stages,
     rate-limit settings, estimated runtime, and rollback/cleanup plan;
   - run the full imported XLSX company set, currently 1024 canonical companies
     unless the database count changes before execution;
   - preserve checkpoint/resume semantics and do not replay succeeded stages
     unnecessarily;
   - refresh vectors only for touched companies;
   - produce a full-run effect report covering coverage uplift, rejected-source
     reasons, products, scenarios, target customers, financing events, summaries,
     vector refresh, RAG smoke results, representative 5180 inspections, failures,
     and companies that still need manual review.
