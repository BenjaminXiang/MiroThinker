## 2026-05-30 - Pre-1024 Scaleout Gate

The in-progress 200-company dry-run showed that the current bottleneck is not
only stage-level orchestration. LLM-heavy child scripts still process companies
and source items mostly serially inside each shard. The first completed
25-company chunk took roughly tens of minutes, which is acceptable for
validation evidence but not acceptable as a basis for a 1024-company full run.

Decision:
- Continue the current 200-company dry-run to capture real bottlenecks and
  failure modes.
- Do not start the 1024-company full dry-run or live rerun immediately after
  the current dry-run unless the new pre-1024 optimization gate passes.
- Do not rely on simply increasing `stage_concurrency` or shard size as the
  scaleout fix, because that can amplify DeepSeek or Serper rate-limit pressure.
- Add a mandatory pre-1024 gate covering script-internal LLM/web concurrency,
  provider rate limiting, per-company child-script checkpoints, dry-run no-write
  regression coverage, and Company LLM model-routing verification across upload
  enrichment entry points.

Impacted tasks:
- Added tasks 9.2 through 9.4 before the full imported-company dry-run.
- Renumbered the full-run execution tasks to 9.5 through 9.9.

## 2026-05-30 - Scaleout Gate Implemented and Smoke-Verified

The 200-company dry-run timed out after 10,800 seconds with 175 selected
companies completed and 25 selected companies stale-running in
`generic_source_judgment`. That result is now the measured bottleneck evidence
for delaying any 1024-company run.

Implementation decision:
- Add provider rate-limit wrappers for DeepSeek chat-completion calls and
  Serper requests-session calls.
- Add child-script `--concurrency` controls and upload-runner
  `--child-llm-concurrency` / `--child-web-concurrency` pass-through.
- Route `run_company_xlsx_team_synthesis.py` through Company LLM task routing,
  so trusted XLSX structuring uses `deepseek-v4-lite` and multi-source
  synthesis uses `deepseek-v4-pro`.
- Add per-company child checkpoints for XLSX/team synthesis, Yiou/PitchHub
  news ingestion, generic source judgment, and multi-source narrative synthesis.
- Update the parent runner so a failed shard marks only companies that have not
  already been checkpointed by the child script.

Validation decision:
- A 10-company post-optimization dry-run smoke completed successfully with
  child LLM/web concurrency set to 2, zero business fact-table writes, and
  checkpoint evidence for the key web/LLM stages.
- The 10-company smoke is not a replacement for the 200-company dry-run gate;
  task 8.5 remains pending.

## 2026-05-31 - 200-Company Dry-Run Gate Passed With Remaining Scaleout Risks

The post-optimization 200-company dry-run completed successfully for batch
`fb7eeffb-ca23-45bd-8116-0029f8aa32ce`.

Decision:
- Mark task 8.5 complete because the representative 200-company dry-run passed
  and the report/evidence artifacts were stored.
- Keep the 200-company live bounded run, touched-vector refresh, RAG smoke
  checks, and 5180 inspection pending.
- Continue blocking any 1024-company full dry-run or live rerun until those
  gates pass.

Evidence:
- Runtime was about 4h25m for 200 selected companies.
- The dry-run produced zero business fact-table writes and only added
  `company_enrichment_search_audit` trace rows.
- The run recorded 1053 queries, 513 fetches, 832 accepted sources, 1095
  rejected sources, 122 source products extracted, 64 source scenarios
  extracted, 2 funding events extracted, and 192 multi-source narratives.

Residual risks:
- Runtime is still high enough that a direct 1024-company run is not justified.
- `source_product_extract` still has weaker per-company progress visibility
  because it is source-row driven.
- `news_ingest` still needs true internal per-company web-search concurrency.
- Target-customer and funding coverage remain low and require follow-up
  extractor/prompt improvements.

## 2026-05-31 - Post Dry-Run Bottleneck Fixes

The 200-company post-optimization dry-run passed, but exposed three follow-up
issues that should be fixed before live bounded validation.

Implementation decision:
- Make `run_company_news_ingest.py --concurrency` real at company-fetch level.
- Make `run_company_source_product_extract.py` checkpoint every requested
  company, including companies with no selected source rows.
- Report `products_with_target_customers` from XLSX/team synthesis and
  source-product extraction, because the dry-run zero was partly a reporting
  gap rather than a proven extraction gap.

Validation:
- Added RED/GREEN tests for all three issues.
- Ran the affected script suites plus upload-batch tests: 82 tests passed.
- Ran ruff and compileall on touched scripts and tests.

Remaining decision:
- Rerun a bounded validation before live bounded execution to measure runtime
  and corrected target-customer coverage with the post-dry-run fixes.

## 2026-05-31 - Post-Fix 10-Company Smoke

The post-dry-run bottleneck fixes were verified with a new 10-company dry-run
smoke batch `88cd2a26-bc87-401a-b4ed-2baa2a9a55ff`.

Decision:
- Treat the smoke as evidence that the new child-concurrency wiring, no-write
  behavior, batch completion, and target-customer metric propagation work in an
  end-to-end command.
- Do not treat the smoke as a substitute for the 200-company live bounded
  validation.
- Keep the full 1024-company execution blocked until live bounded validation,
  touched-vector refresh, RAG smoke checks, and 5180 inspection pass.

Evidence:
- The dry-run completed `succeeded` for 10 selected companies with 0 failures
  and empty stderr.
- Business fact tables were unchanged; only `company_enrichment_search_audit`
  increased by 52 rows, matching the report query count.
- The report recorded 52 queries, 22 fetches, 29 accepted sources, 53 rejected
  sources, 3 products extracted or synthesized, 1 product with target
  customers, 10 multi-source narratives, and 20 rejected candidates.

Residual risks:
- Target-customer coverage is still low; the smoke target-customer count came
  from XLSX/team synthesis rather than source-product extraction.
- `multi_source_narrative` remains a runtime hotspot and needs bounded live
  validation before any full-population run.

## 2026-05-31 - Provider-Limiter Concurrency and Live Bounded Validation

The initial live bounded resume revealed that increasing stage and child
concurrency did not raise real DeepSeek request concurrency because the
cross-process provider limiter still defaulted to four slots.

Implementation decision:
- Expose provider limiter controls on the upload enrichment runner through
  `--provider-llm-max-concurrency` and
  `--provider-serper-max-concurrency`.
- Record the effective provider limits in the plan/live run report.
- Freeze the live validation sample through `--company-id-file`, because
  representative sampling can drift after source coverage changes.
- Use company-level `--stage-subchunk-size 1` for the successful live resume,
  because larger subchunks let one slow company block checkpoint visibility for
  multiple companies.
- Clear batch-level `last_error` when `mark_batch_finished(...,
  status="succeeded")` finalizes successfully.

Validation:
- The final 200-company live bounded run for batch
  `66e8bcda-2030-42eb-84fb-5edefff97a43` completed `succeeded` with 200
  selected companies processed, 200 succeeded, 0 failed, empty stderr, and
  824 unselected companies still queued.
- Live row-count deltas were: product +332, product evidence +1054,
  application scenario +175, signal event +77, news/source item +602, and
  enrichment search audit +1047.
- Focused upload-runner and enrichment-batch tests passed after the concurrency
  and stale-error fixes.

Residual risks:
- Milvus refresh and RAG smoke checks were intentionally skipped and remain the
  next validation gate.
- 5180 live search/detail inspection still needs to be recorded.
- Generic source judgment and multi-source narrative remain long-tail stages;
  full-population execution should keep company-level subchunks and add finer
  per-query/per-source timeout reporting.

## 2026-05-31 - Generic-Web Identity Cleanup and Final 200-Company Verification

5180 inspection found a real escaped defect in the live sample: the OneGu
company page contained near-name generic-web materials for `股一科技（深圳）有限责任公司`
and `深圳市的一科技有限公司`.

Implementation decision:
- Strengthen generic-web source acceptance so an accepted LLM judgment still
  requires trusted identity evidence from the XLSX/canonical company identity.
- Generate trusted short brand variants from canonical/legal names, including
  parenthetical-location removal and common business-descriptor trimming, so
  legitimate source text such as `中农美蔬` and `偲百创` is not rejected merely
  because public articles use short names.
- Keep the legal-entity conflict guard: if a source names a different legal
  entity and does not overlap a trusted legal/canonical identity, it is
  rejected even when a short alias overlaps.
- Replay the guard over the fixed 200-company validation sample instead of
  deleting only the reported OneGu rows.

Validation decision:
- The alias-aware audit checked 725 accepted generic-web rows and identified
  90 invalid rows across 56 companies.
- Cleanup removed those 90 source rows plus derived evidence: 187 product
  evidence rows, 48 products that had no remaining evidence, and 32 application
  scenarios. No signal events were removed.
- The post-cleanup audit checked 635 remaining accepted generic-web rows and
  found 0 invalid rows.
- All 56 affected company summaries were refreshed after cleanup. The first
  narrative refresh was terminated after an LLM long tail with 44 companies
  already committed; the remaining 12 were rerun successfully.
- The affected 56 company vectors were refreshed, and the final company RAG
  smoke passed 5/5 checks.
- 5180 inspection confirmed that OneGu no longer shows the near-name
  contaminants or the old `个人简介` label, while retaining the trusted
  `友心` / `积分商城` profile narrative.

Residual risks:
- The 1024-company full dry-run/live rerun remains pending.
- The terminated narrative refresh shows that full-scale execution needs
  LLM-call timeout, retry, and per-company checkpoint reporting inside
  LLM-heavy scripts before increasing volume further.
- Product target-customer coverage remains a quality-improvement item after
  this validation gate.

## 2026-05-31 - Child LLM Concurrency, Timeout, and Retry Hardening

The post-cleanup narrative refresh exposed a scaleout hazard: a single slow LLM
request could keep an LLM-heavy child process alive after many companies had
already committed their per-company checkpoints.

Implementation decision:
- Raise upload-runner child defaults to `--child-llm-concurrency 4` and
  `--child-web-concurrency 3`, while preserving provider-level limiter controls.
- Add `--child-llm-timeout-seconds` and `--child-llm-retry-budget` to the
  upload runner and propagate them to all LLM-using child scripts:
  XLSX/team synthesis, generic source judgment, signal extraction, source
  product extraction, multi-source narrative synthesis, and Yiou/PitchHub
  search-hint generation.
- Add matching `--llm-timeout-seconds` and `--llm-retry-budget` options to the
  child scripts and pass `max_retries=settings.retry_budget` to OpenAI SDK
  clients, so the task routing retry budget is actually enforced.
- Convert `run_company_signal_extract.py` from serial LLM extraction to
  per-news-row worker concurrency; writes remain serialized after extraction to
  avoid sharing a DB connection across worker threads.

Validation:
- RED tests first failed on the missing child timeout/retry flags, missing
  upload-runner command propagation, missing OpenAI `max_retries`, and missing
  signal-extraction worker concurrency.
- Focused script tests then passed: 117 tests across Company news ingest,
  generic source judgment, signal extraction, source-product extraction,
  XLSX/team synthesis, upload enrichment batch, and Company LLM routing.
- Python compilation passed for the touched child scripts and upload runner.
- `openspec validate company-scaleout-enrichment-hardening --strict` passed.

Full-run implication:
- The 1024-company dry-run should use company-level stage subchunks, provider
  caps, and the new child LLM timeout/retry controls before any live rerun is
  attempted.

## 2026-05-31 - Full 1024-Company Dry-Run, Provider-Limiter Fix, and Live-Run Plan

Implementation and runtime decision:
- Created a fresh full imported-company dry-run batch
  `84fd0f38-1430-4532-9787-098f2663a3ce` for 1024 XLSX-backed canonical
  companies.
- Allowed real external-source and LLM access in dry-run while preserving
  `--dry-run --skip-persistence --skip-milvus`.
- Preserved checkpoint and `company_enrichment_search_audit` evidence while
  keeping business fact tables unchanged.
- Initial 20/40-way resumes showed that `generic_source_judgment` was still
  nearly serialized. Root cause: `ProviderRateLimiter` held the interval lock
  until the provider call returned, which serialized DeepSeek requests despite
  multiple slot locks.
- Fixed the shared provider rate limiter so the interval lock only protects
  request-start spacing and is released before the API call body; the slot lock
  still covers the call to enforce maximum concurrency.
- Resumed the full dry-run with DeepSeek max concurrency 40, Serper max
  concurrency 10, official-site max concurrency 6, child LLM concurrency 2,
  and child web concurrency 3.

Validation:
- RED regression first failed:
  `test_provider_rate_limiter_does_not_serialize_call_body` observed
  `max_active == 1`.
- GREEN verification passed:
  `uv run --no-sync pytest apps/miroflow-agent/tests/data_agents/company/test_provider_rate_limit.py`
  -> 4 passed.
- `uv run --no-sync python -m py_compile apps/miroflow-agent/src/data_agents/company/provider_rate_limit.py`
  -> passed.
- Final fixed full dry-run exited 0. Database batch status: `succeeded`;
  companies processed: 1024; companies failed: 0.
- Stage checkpoints reached 1024/1024 for baseline readiness, XLSX/team
  synthesis, official product capture, Yiou, PitchHub, generic source
  judgment, signal extraction, source product extraction, multi-source
  narrative, and batch completion.
- Business fact row-count deltas were zero for `company_product`,
  `company_product_evidence`, `company_application_scenario`,
  `company_signal_event`, and `company_news_item`.
- `company_enrichment_search_audit` increased from 5892 to 11450 rows as
  permitted evidence.

Artifacts:
- Dry-run report:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-report-20260531T115737Z.md`.
- Machine summary:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-summary-20260531T115737Z.json`.
- After counts:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-dry-run-after-counts-20260531T115737Z.json`.
- Execution plan:
  `.agents/runs/company-scaleout-enrichment-hardening/company-1024-full-run-execution-plan-20260531T115737Z.md`.

Remaining:
- The live 1024-company rerun remains gated under task 9.7.
- Touched-vector refresh, RAG smoke, 5180 inspection, and full-run effect
  reporting remain pending under tasks 9.8-9.9.

## 2026-05-31 - Full 1024-Company Live Rerun Closed

Implementation and runtime decision:
- Executed a fresh full live batch
  `a1a72d01-e054-48e9-8124-f62e920ab3f7` for 1024 XLSX-backed canonical
  companies after the full dry-run and execution plan passed.
- Kept company-level stage subchunks, provider caps, and child LLM timeout /
  retry controls from the scaleout gate.
- Wrote live business-fact updates for the selected 1024 companies and retained
  checkpoint plus search-audit evidence.
- Refreshed vectors only for the touched 1024 companies in the admin-console
  Milvus Lite store used by the 5180 backend.
- Produced a full-run effect report covering counts, coverage, source
  acceptance/rejection, quality status, manual-review exposure, vector refresh,
  RAG smoke, 5180 inspection, failures, and residual risks.

Validation:
- Full live rerun exited 0 with empty stderr. Database batch status:
  `succeeded`; companies processed/succeeded/failed: 1024/1024/0.
- All 8193 reported stage executions succeeded.
- Live row-count deltas were: product +1726, product evidence +4949,
  application scenario +766, signal event +152, news/source item +3729, and
  enrichment search audit +5558.
- Touched-vector refresh processed 1024/1024 companies with 0 skipped and 0
  errors.
- Company RAG smoke passed 5/5 checks for product, target customer, application
  scenario, recent financing, and profile-summary queries.
- 5180 inspection confirmed the representative MetalenX detail page renders
  company summary, products, application scenarios, recent dynamics, target
  customers, and financing text, and does not use the old `个人简介` label.

Residual risks:
- Product target-customer coverage remains low and should be improved in a
  later extractor/prompt quality iteration.
- Product and scenario facts remain review-gated unless accepted by an
  operator.
- Official-site acquisition remains bounded by website availability, anti-bot
  behavior, JavaScript rendering quality, robots, CAPTCHA, login, and paywall
  constraints.

## 2026-05-31 - OneGu XLSX-Only Product Extraction Escape

Escaped defect:
- The full live rerun showed that OneGu (`COMP-17d68ddf7fd6`) had a long
  `profile_summary` synthesized from the trusted XLSX baseline, but no
  `company_product` or `company_application_scenario` rows.
- The XLSX baseline clearly contains the product/service facts: `友心`, points
  mall service, high-end goods customization, red-envelope system, online
  payment, CRM information management, data mining, procurement supply chain,
  collaboration management, and physical shelf display.

Root-cause decision:
- Product/scenario extraction ran too early and too source-row centric. If
  official, Yiou, PitchHub, and generic web all produced no accepted source
  rows, `source_product_extract` had no input.
- `xlsx_team_synthesis` had XLSX text available, but deterministic extraction
  was biased toward prior medical/robotics/industrial examples and missed the
  e-commerce service pattern.
- The XLSX fallback LLM shared the `trusted_xlsx_structuring` lite route. The
  current DeepSeek endpoint rejects `deepseek-v4-lite`, and the fallback path
  swallowed provider/parse failures as empty extraction results.

Repair decision:
- Treat this as a systemic post-collection extraction gap, not a OneGu-only
  patch.
- Keep XLSX as the trusted baseline and run XLSX product/scenario synthesis
  again in the final post-collection multi-source narrative stage.
- Use the judgment-grade product extraction route (`generic_product_admission`,
  `deepseek-v4-pro`) for product/scenario LLM fallback.
- Preserve fallback diagnostics in company-level reports/checkpoints so future
  empty extraction can be distinguished from "no facts in source material".
