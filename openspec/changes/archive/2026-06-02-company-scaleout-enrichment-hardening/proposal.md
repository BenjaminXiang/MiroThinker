## Why

The Company enrichment pipeline now works for a bounded 100-company validation, but the next operating target is larger and less forgiving: a 200-company sample that can prove the upload-scoped XLSX baseline plus official website, Yiou, 36Kr/PitchHub, and generic web-source enrichment can scale without creating unverifiable product, scenario, financing, or profile facts.

The remaining risk is not one missing parser. It is the scaleout contract around official-site acquisition quality, LLM quality gates, concurrency, checkpointing, source-level provenance, front-end diagnostics, and evidence-backed E2E validation.

## What Changes

- Add a scaleout hardening contract for Company enrichment batches moving from 100-company validation to 200-company validation.
- Harden official-site capture beyond static homepage link scraping:
  - URL normalization and same-company host checks.
  - sitemap, robots-aware discovery where available, navigation discovery, and common-path probing.
  - JavaScript-rendering fallback for pages that are empty, short, or obvious SPA shells.
  - explicit failure taxonomy for DNS, timeout, HTTP blocking, bot challenges, JS rendering failure, identity mismatch, low text, and no relevant pages.
- Keep XLSX as the trusted baseline for company identity, baseline profile, known financing fields, website, team text, and source-data evaluation.
- Use crawled sources mainly to supplement products, application scenarios, target customers, recent financing, recent dynamics, technology-route summaries, and longer company profiles.
- Add LLM model-routing requirements:
  - low-risk query and trusted-XLSX structuring may use `deepseek-v4-lite`;
  - source judgment, snippet triage, product admission, financing extraction, conflict/newer-round judgment, multi-source summaries, and quality audit must use `deepseek-v4-pro`.
- Make LLM extraction concurrent and resumable:
  - per-stage concurrency limits;
  - provider-level rate limits and retry budgets;
  - per-company checkpointing;
  - idempotent persistence for replays.
- Require per-company audit evidence for search queries, accepted/rejected sources, LLM decisions, official-site crawl failure reasons, synthesis inputs, persisted facts, rejected facts, and vector refresh state.
- Expand admin-console visibility so operators can inspect upload/enrichment progress, company-level enrichment status, source/failure diagnostics, products, scenarios, recent financing, recent dynamics, and evidence links.
- Validate with a fresh 200-company sample, not a full XLSX population run, and refresh only touched company vectors.
- Explicitly exclude recruiting/job-trend extraction, anti-bot bypass, CAPTCHA solving, login/paywall bypass, and unbounded crawling.

## Capabilities

### New Capabilities

- `company-scaleout-enrichment-hardening`: Upload-scoped Company enrichment scaleout from 100-company validation to a 200-company sample, covering official-site hardening, LLM model routing and concurrency, checkpoint/resume, source provenance, admin diagnostics, touched-vector refresh, and E2E validation evidence.

### Modified Capabilities

- `company-enrichment-source-closure`: Extends the existing Company source-closure requirements so official website capture is not limited to static product-page discovery, generic web and high-quality site sources retain explainable source judgment, and accepted facts remain source-grounded before they can feed products, scenarios, financing, profile summaries, or RAG text.

## Impact

- Affected code: company official-site capture, source-material model, generic source judgment, Yiou/PitchHub and Serper connectors, upload enrichment batch runner, LLM profile/model routing, source-product extraction, narrative enrichment, signal extraction, company vectorizer, admin-console upload/pipeline/detail APIs, and company detail UI.
- Affected storage: existing company enrichment batch/state audit fields, source-material persistence, company product and product evidence, application-scenario evidence, signal events, company profile fields, and Milvus company vectors. New columns or tables may be added only if existing audit fields cannot represent scaleout diagnostics and replay-safe source provenance.
- Affected validation: unit and script tests for official capture fallback, source judgment, model routing, concurrency/checkpoint behavior, idempotency, front-end diagnostics, OpenSpec validation, 200-company dry-run and live bounded validation, and RAG smoke checks on touched companies.
- Affected operations: no full 6512-row live upload or full 1024/6512 vector rebuild is part of this change. The rollout proves scaleout readiness on a representative 200-company sample first.
