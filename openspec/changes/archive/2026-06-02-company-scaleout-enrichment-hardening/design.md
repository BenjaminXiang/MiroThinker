## Context

The current Company domain has an upload-scoped enrichment path that can import XLSX company data, treat XLSX as a trusted baseline, run named Yiou and 36Kr/PitchHub site-search connectors, run generic source judgment, capture bounded official-site material, synthesize products and application scenarios, generate long profiles, extract financing signals, persist batch state, expose processing status in the admin console, and refresh touched company vectors.

That pipeline has been validated on a 100-company sample. The next operating step is not a full XLSX-scale rollout. It is a hardened 200-company validation that proves the pipeline can scale while preserving source attribution, LLM quality gates, resumability, and operator diagnostics.

The key unresolved risks are official website acquisition quality, JavaScript-heavy sites, source-noise handling, LLM execution cost and latency, replay safety, and the difference between "no external data exists" and "the pipeline failed to find or parse it."

## Goals / Non-Goals

**Goals:**

- Move Company enrichment from a 100-company validation to a representative 200-company validation.
- Keep XLSX as the trusted baseline for identity, known profile facts, website, baseline financing, and team text.
- Improve official-site acquisition with layered discovery and JavaScript rendering fallback before declaring a site unhelpful.
- Preserve compliance boundaries: record blocking reasons rather than bypassing bot challenges, CAPTCHA, login walls, or paywalls.
- Route LLM calls by task risk, with `deepseek-v4-pro` for source judgment, product admission, financing extraction, and synthesis-quality decisions.
- Make LLM-heavy extraction concurrent, checkpointed, replay-safe, and rate-limited.
- Persist per-company source and decision audit so operators can explain missing enrichment, accepted facts, and rejected facts.
- Ensure company detail pages and pipeline pages expose products, scenarios, financing, profile summaries, source links, and processing status from the enriched data.
- Refresh only touched company vectors and verify RAG behavior for the 200-company validation set.

**Non-Goals:**

- Do not run a full 6512-row or full production-company live enrichment as part of this change.
- Do not add recruiting or job-trend extraction.
- Do not bypass CAPTCHA, bot protection, robots restrictions, login walls, or paywalls.
- Do not let generic web results overwrite XLSX identity or baseline fields directly.
- Do not introduce an opaque long-running agent loop that cannot be audited per company.

## Decisions

1. **Use the 200-company sample as the scaleout gate.**

   The implementation SHALL keep the validation target at 200 companies until official-site, source-judgment, LLM, persistence, front-end, and vector-refresh evidence is available. A full XLSX-scale run is a later operational decision.

   Alternative considered: run all imported companies immediately. That would make failures harder to diagnose, increase external API cost, and risk polluting product/scenario facts before source gates are proven at the next scale.

2. **Harden official-site capture with a layered acquisition strategy.**

   Official capture SHALL use normalized official URLs, same-host constraints, static fetch, sitemap discovery, navigation discovery, common product/solution/about path probing, and Playwright-based JavaScript rendering fallback when static HTML is too short or looks like a SPA shell. Capture attempts SHALL record acquisition method and failure reason.

   Alternative considered: keep static `requests` plus link hints only. That is simple but cannot distinguish unavailable websites from JS-rendered websites and would underfill product and scenario material.

3. **Treat source provenance as a first-class data product.**

   Every accepted source material SHALL carry source tier, URL, title, capture time, acquisition method, source-judgment status, confidence, evidence span, and trust reason when available. Every rejected or missed source SHALL carry a reason that is useful to an operator.

   Alternative considered: only store final products and scenarios. That would make front-end audit, reruns, and pollution cleanup difficult.

4. **Keep XLSX trusted, but do not treat it as sufficient for "recent state."**

   XLSX SHALL remain the identity and baseline reference. Crawled sources SHALL supplement products, scenarios, target customers, recent financing, recent dynamics, technology-route summaries, and long profiles. Newer financing evidence SHALL create source-backed signal events or latest-funding candidates without silently rewriting XLSX snapshots.

5. **Use direct model routing, not `lite_then_pro`, for judgment-sensitive tasks.**

   `deepseek-v4-lite` MAY be used only for low-risk search hints, identity aliases, and short trusted-XLSX structuring. `deepseek-v4-pro` SHALL be used for snippet triage, source judgment, generic product admission, product ownership attribution, financing extraction, financing conflict/newer-round judgment, multi-source profile synthesis, technology-route synthesis, and quality audit.

   Alternative considered: run a lite model first and escalate uncertain cases to pro. The user rejected this baseline for snippet triage, generic product admission, and financing extraction, because false negatives and false positives directly affect data quality.

6. **Use bounded concurrency with per-company checkpoints.**

   LLM and web stages SHALL expose concurrency limits, retry budgets, timeout settings, and per-stage checkpoints. A rerun SHALL skip succeeded stages by default and SHALL NOT duplicate products, scenarios, signals, source rows, or vector updates.

7. **Expose operational diagnostics in admin-console surfaces.**

   Batch-level and company-level status SHALL be visible in the upload/pipeline detail path. Company detail pages SHALL show enriched profile text, products, application scenarios, recent financing/dynamics, source links, and update time while keeping review state and source confidence visible.

8. **Refresh only touched company vectors.**

   The validation SHALL refresh vector payloads only for the 200 companies touched by the enrichment batch. RAG smoke tests SHALL verify questions about products, scenarios, target customers, and financing for sampled companies.

## Risks / Trade-offs

- Official websites may block automated access -> record `http_403`, `http_429`, `captcha_or_bot_challenge`, or `robots_disallowed`; use XLSX, Yiou, PitchHub, and generic sources as fallback evidence.
- JavaScript rendering increases runtime and resource cost -> trigger Playwright only after static fetch indicates a SPA shell, low text, or missing material, and cap pages, time, and body size.
- LLM concurrency may hit provider limits -> use configured concurrency, timeout, retry, and backoff values per model and stage.
- Generic web may retrieve same-name or competitor pages -> require target-company identity and fact attribution before facts can feed synthesis or persistence.
- Longer company profiles may contain unsupported claims -> prompts and validators require source-grounded JSON, evidence spans, and sparse-material blockers.
- Replay cleanup may remove useful review candidates if too broad -> cleanup and rerun logic SHALL target batch/source markers and statuses, not unrelated production data.

## Migration Plan

1. Add regression tests for official-site acquisition fallback, failure taxonomy, model routing, concurrent stage checkpoints, idempotent persistence, admin diagnostics, and 200-company report shape.
2. Implement official-site acquisition hardening behind existing upload-batch flags and conservative defaults.
3. Add model-routing configuration and concurrency controls without changing the default model away from the current DeepSeek profile unless explicitly configured.
4. Extend source-material and batch-state audit payloads only where existing structures cannot represent acquisition method, failure reason, or judgment evidence.
5. Wire official capture, high-quality site sources, generic source judgment, synthesis, signals, and vector refresh into the resumable upload batch with per-company checkpoints.
6. Validate with unit/script tests, OpenSpec validation, a fresh 100-company rerun if needed, then a 200-company dry-run and live bounded validation.
7. Record validation evidence under the change and keep the full XLSX-scale rollout out of scope until the 200-company report is reviewed.

Rollback is feature-flag based: disable JS rendering, generic web, high-quality site search, official-site capture, or vector refresh independently; keep XLSX baseline records published and leave uncertain enrichment facts review-gated.

## Open Questions

- The exact default concurrency values should be selected after a short DeepSeek and Serper rate-limit probe in the implementation environment.
- If existing batch-state JSON becomes too large for useful operator diagnostics, implementation may need a dedicated source-audit table with a reversible migration.
- The 200-company selector should be deterministic and representative across industries, website availability, and source coverage; if the current selector is biased, implementation should add a stratified selector.
